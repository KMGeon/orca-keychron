"""Bounded product-integration fixture for the installed GJC 0.16.4 runtime.

The provider is loopback-only and logs metadata, never message or tool content.
The receiver is the product GjcStatusSource with a read-only parse observer that
records only fields already allowed by the production wire schema.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
REPO = BASE.parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from orca_keychron.rendering import ORANGE, render_zone
from orca_keychron_gjc import gjc_install
from orca_keychron_gjc.gjc_source import request_control
from orca_keychron_gjc.gjc_tracker import GjcIndicator, GjcTracker

DEFAULT_RUNTIME = Path("/tmp/gjc-product-qa")
SELECTOR = "product-qa/fixture"
MODEL = "fixture"
PROVIDER_LOCK = threading.Lock()
SCENARIOS = ("success", "failed", "slow", "mass", "decisions_two", "duplicate")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    with PROVIDER_LOCK:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def content_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return ""


def calls_and_results(body: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    calls: list[dict[str, Any]] = []
    results: dict[str, str] = {}
    for message in body.get("messages", []):
        if message.get("role") == "assistant":
            for raw in message.get("tool_calls", []):
                function = raw.get("function", {})
                try:
                    arguments = json.loads(function.get("arguments", "{}"))
                except json.JSONDecodeError:
                    arguments = {}
                calls.append({"id": raw.get("id"), "name": function.get("name"), "args": arguments})
        elif message.get("role") == "tool":
            results[str(message.get("tool_call_id", ""))] = content_text(message)
    return calls, results


def objects(text: str):
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


def returned_child_ids(text: str) -> list[str]:
    return list(
        dict.fromkeys(re.findall(r"^- `([^`]+)` \(job `[^`]+`\)", text, re.MULTILINE))
    )


def decision(request_id: str) -> dict[str, Any]:
    return {
        "status": "needs_user_decision",
        "request_id": request_id,
        "question": f"[{request_id}] Choose how the synthetic child should continue.",
        "options": ["Continue with A", "Continue with B"],
        "checkpoint": f"checkpoint-{request_id}",
    }


def valid_decision(value: dict[str, Any], request_id: str) -> bool:
    expected = decision(request_id)
    return all(value.get(key) == expected[key] for key in expected)


def child_decision_plan(
    body: dict[str, Any], request_id: str, record: Any
) -> tuple[list[tuple[str, dict[str, Any]]], str | None]:
    _calls, _ = calls_and_results(body)
    resumes = []
    for message in body.get("messages", []):
        if message.get("role") != "user":
            continue
        resumes.extend(
            value for value in objects(content_text(message))
            if {"request_id", "selected_answer", "checkpoint"} <= set(value)
        )
    if not resumes:
        record("child_decision_yielded", request_id=request_id, valid=True)
        return [("yield", {"result": {"data": decision(request_id)}})], None
    resume = resumes[-1]
    correlation = resume.get("request_id") == request_id
    answer = resume.get("selected_answer") in decision(request_id)["options"]
    checkpoint = resume.get("checkpoint") == f"checkpoint-{request_id}"
    consumed = correlation and answer and checkpoint
    record(
        "child_answer_consumed",
        request_id=request_id,
        correlation_valid=correlation,
        answer_valid=answer,
        checkpoint_valid=checkpoint,
    )
    return [(
        "yield",
        {"result": {"data": {
            "status": "completed" if consumed else "correlation_error",
            "request_id": request_id,
            "answer_consumed": consumed,
        }}},
    )], None


def parent_decisions_plan(
    body: dict[str, Any], record: Any
) -> tuple[list[tuple[str, dict[str, Any]]], str | None]:
    calls, results = calls_and_results(body)
    request_ids = ["req_1", "req_2"]
    tasks = [call for call in calls if call["name"] == "task"]
    if not tasks:
        return [("task", {"agent": "decision-child", "tasks": [
            {
                "id": f"decision_{index}",
                "description": f"Synthetic decision {request_id}",
                "assignment": f"[DECISION_CHILD:{request_id}]",
                "inheritContext": "none",
            }
            for index, request_id in enumerate(request_ids, 1)
        ]})], None
    child_ids = returned_child_ids(results.get(tasks[0]["id"], ""))
    if len(child_ids) != 2:
        record("parent_fixture_failed", actual_child_ids_complete=False)
        return [], "PRODUCT_QA_FIXTURE_FAILED: missing actual child IDs"
    initial_await = [
        call for call in calls
        if call["name"] == "subagent" and call["args"].get("action") == "await"
    ]
    if not initial_await:
        return [("subagent", {
            "action": "await", "ids": child_ids, "timeout_ms": 10000, "verbosity": "full"
        })], None
    reads = [call for call in calls if call["name"] == "read"]
    for child_id in child_ids:
        if not any(call["args"].get("path") == "agent://" + child_id for call in reads):
            return [("read", {"path": "agent://" + child_id})], None
    complete = 0
    for request_id, child_id in zip(request_ids, child_ids):
        matching_reads = [
            call for call in reads if call["args"].get("path") == "agent://" + child_id
        ]
        values = [
            value for call in matching_reads
            for value in objects(results.get(call["id"], ""))
        ]
        pending = next((value for value in values if valid_decision(value, request_id)), None)
        if pending is None:
            record("parent_fixture_failed", request_id=request_id, decision_valid=False)
            return [], "PRODUCT_QA_FIXTURE_FAILED: invalid child decision"
        asks = [
            call for call in calls if call["name"] == "ask"
            and any(q.get("id") == request_id for q in call["args"].get("questions", []))
        ]
        if not asks:
            record(
                "parent_question_requested",
                request_id=request_id,
                decision_valid=True,
                actual_child_id_used=child_id in child_ids,
            )
            return [("ask", {"questions": [{
                "id": request_id,
                "question": pending["question"],
                "options": [{"label": option} for option in pending["options"]],
            }]})], None
        answer_match = re.search(r"User selected:\s*([^\n]+)", results.get(asks[-1]["id"], ""))
        answer = answer_match.group(1).strip() if answer_match else None
        if answer not in pending["options"]:
            record("parent_answer_rejected", request_id=request_id, answer_valid=False)
            return [], "PRODUCT_QA_DECISION_NOT_RESUMED"
        resumes = [
            call for call in calls if call["name"] == "subagent"
            and call["args"].get("action") == "resume" and call["args"].get("id") == child_id
        ]
        if not resumes:
            payload = {
                "request_id": request_id,
                "selected_answer": answer,
                "checkpoint": pending["checkpoint"],
            }
            record(
                "parent_child_resume_requested",
                request_id=request_id,
                answer_valid=True,
                actual_child_id_used=child_id in child_ids,
            )
            return [("subagent", {
                "action": "resume", "id": child_id,
                "message": "[DECISION_RESUME] " + json.dumps(payload),
            })], None
        resume_index = calls.index(resumes[-1])
        after_resume = calls[resume_index + 1 :]
        if not any(
            call["name"] == "subagent" and call["args"].get("action") == "await"
            for call in after_resume
        ):
            return [("subagent", {
                "action": "await", "ids": [child_id], "timeout_ms": 10000,
                "verbosity": "full",
            })], None
        if not any(
            call["name"] == "read" and call["args"].get("path") == "agent://" + child_id
            for call in after_resume
        ):
            return [("read", {"path": "agent://" + child_id})], None
        final_values = list(objects(results.get(matching_reads[-1]["id"], "")))
        consumed = any(
            value.get("status") == "completed"
            and value.get("request_id") == request_id
            and value.get("answer_consumed") is True
            for value in final_values
        )
        record("parent_completion_checked", request_id=request_id, answer_consumed=consumed)
        if not consumed:
            return [], "PRODUCT_QA_FIXTURE_FAILED: child did not consume answer"
        complete += 1
    record("experiment_complete", all_decisions_consumed=complete == 2)
    return [], "PRODUCT_QA_DECISIONS_COMPLETE"


def mass_parent_plan(body: dict[str, Any], record: Any):
    calls, results = calls_and_results(body)
    tasks = [call for call in calls if call["name"] == "task"]
    if not tasks:
        children = [
            {
                "id": f"slow_{index}",
                "description": f"Synthetic working child {index}",
                "assignment": f"[PRODUCT_CHILD:MASS_SLOW_{index}]",
                "inheritContext": "none",
            }
            for index in range(4)
        ]
        children.append({
            "id": "fanout",
            "description": "Synthetic five-child fanout",
            "assignment": "[PRODUCT_CHILD:MASS_FANOUT]",
            "inheritContext": "none",
        })
        children.append({
            "id": "pending_human",
            "description": "Synthetic pending-human child",
            "assignment": "[PRODUCT_CHILD:MASS_DECISION]",
            "inheritContext": "none",
        })
        return [("task", {
            "agent": "product-child",
            "tasks": children,
            "spawnPlan": {
                "whyParallel": "Exercise one bounded aggregate snapshot with eleven simultaneous synthetic children.",
                "whyNotLocal": "Only real GJC child sessions emit the product hook lifecycle being verified.",
                "independence": "Each child uses the isolated loopback fixture and has no shared mutable output.",
                "expectedReceiptShape": "Six actual child IDs from the task receipt.",
                "maxInlineTokens": 512,
            },
        })], None
    child_ids = returned_child_ids(results.get(tasks[0]["id"], ""))
    record("mass_child_ids_observed", count=len(child_ids), actual_ids=len(child_ids) == 6)
    if len(child_ids) != 6:
        return [], "PRODUCT_QA_FIXTURE_FAILED: missing mass child IDs"
    if not any(call["name"] == "subagent" for call in calls):
        return [("subagent", {
            "action": "await", "ids": child_ids, "timeout_ms": 60000, "verbosity": "full"
        })], None
    return [], "PRODUCT_QA_MASS_COMPLETE"


def mass_fanout_plan(body: dict[str, Any], record: Any):
    calls, results = calls_and_results(body)
    tasks = [call for call in calls if call["name"] == "task"]
    if not tasks:
        children = [{
            "id": f"nested_slow_{index}",
            "description": f"Nested synthetic working child {index}",
            "assignment": f"[PRODUCT_CHILD:MASS_SLOW_NESTED_{index}]",
            "inheritContext": "none",
        } for index in range(5)]
        return [("task", {
            "agent": "product-child",
            "tasks": children,
            "spawnPlan": {
                "whyParallel": "Exercise five simultaneous nested synthetic child lifecycles.",
                "whyNotLocal": "Real nested GJC sessions are the protocol subject under test.",
                "independence": "Each child has an independent loopback-only slow stream.",
                "expectedReceiptShape": "Five actual nested child IDs from the task receipt.",
                "maxInlineTokens": 256,
            },
        })], None
    child_ids = returned_child_ids(results.get(tasks[0]["id"], ""))
    record("mass_nested_ids_observed", count=len(child_ids), actual_ids=len(child_ids) == 5)
    if len(child_ids) != 5:
        return [], "PRODUCT_QA_FIXTURE_FAILED: missing nested child IDs"
    return [], "PRODUCT_QA_MASS_FANOUT_COMPLETE"


class ProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: Any) -> None:
        pass

    def record(self, event: str, **fields: Any) -> None:
        append_jsonl(self.server.metadata_path, {"time": time.time(), "event": event, **fields})

    def send_json(self, code: int, value: Any) -> None:
        payload = json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        self.send_json(200, {"ok": True, "scope": "loopback synthetic product QA"})

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", 0))
        if self.path != "/v1/chat/completions" or size > 4_000_000:
            self.send_json(400, {"error": {"message": "bounded local fixture rejection"}})
            return
        body = json.loads(self.rfile.read(size))
        users = [content_text(message) for message in body.get("messages", []) if message.get("role") == "user"]
        joined = "\n".join(users)
        decision_ids = re.findall(r"\[DECISION_CHILD:(req_[12])\]", joined)
        mass_slow = bool(re.findall(r"\[PRODUCT_CHILD:MASS_SLOW_\d+\]", joined))
        mass_decision = "[PRODUCT_CHILD:MASS_DECISION]" in joined
        mass_fanout = "[PRODUCT_CHILD:MASS_FANOUT]" in joined
        roots = re.findall(r"\[PRODUCT_QA:([a-z_]+)\]", joined)
        scenario = roots[-1] if roots else "child"
        side = "child" if decision_ids or mass_slow or mass_decision or mass_fanout else "parent"
        calls, _ = calls_and_results(body)
        self.record(
            "request", side=side, scenario=scenario, prior_tool_call_count=len(calls),
            model_is_fixture=body.get("model") == MODEL,
        )
        if scenario == "failed" and side == "parent":
            self.send_json(400, {"error": {
                "message": "LOCAL_PRODUCT_QA_FAILURE", "type": "invalid_request_error"
            }})
            self.record("http_failure_sent", side=side, scenario=scenario, status=400)
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            response_id = uuid.uuid4().hex

            def emit(delta: dict[str, Any], finish: str | None = None) -> None:
                chunk = {
                    "id": "chatcmpl-" + response_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": MODEL,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                }
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.flush()

            emit({"role": "assistant", "content": ""})
            if scenario == "slow" or mass_slow:
                self.record("slow_stream_started", side=side, scenario=scenario)
                for _ in range(120):
                    emit({"content": "LOCAL_PROGRESS "})
                    time.sleep(0.5)
                actions: list[tuple[str, dict[str, Any]]] = []
                message = "LOCAL_SLOW_COMPLETE"
            elif decision_ids:
                actions, message = child_decision_plan(body, decision_ids[-1], self.record)
            elif mass_decision:
                self.record("mass_decision_yielded", request_id="req_mass", valid=True)
                actions = [("yield", {"result": {"data": decision("req_mass")}})]
                message = None
            elif mass_fanout:
                actions, message = mass_fanout_plan(body, self.record)
            elif scenario == "decisions_two":
                actions, message = parent_decisions_plan(body, self.record)
            elif scenario == "mass":
                actions, message = mass_parent_plan(body, self.record)
            else:
                actions, message = [], "LOCAL_PRODUCT_QA_SUCCESS"
            for index, (name, arguments) in enumerate(actions):
                emit({"tool_calls": [{
                    "index": index,
                    "id": f"call_{response_id}_{index}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }]})
            if message:
                emit({"content": message})
            emit({}, "tool_calls" if actions else "stop")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.record(
                "response_sent", side=side, scenario=scenario,
                tool_names=[name for name, _ in actions], terminal_text=bool(message),
            )
        except (BrokenPipeError, ConnectionResetError):
            self.record("client_disconnected", side=side, scenario=scenario)


def provider(runtime: Path, port: int) -> None:
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    runtime.chmod(0o700)
    server = ThreadingHTTPServer(("127.0.0.1", port), ProviderHandler)
    server.daemon_threads = True
    server.metadata_path = runtime / "provider-metadata.jsonl"
    info = {
        "pid": os.getpid(), "port": server.server_port,
        "url": f"http://127.0.0.1:{server.server_port}/v1",
        "metadata": str(server.metadata_path),
    }
    write_json(runtime / "provider.json", info)
    print(json.dumps(info), flush=True)
    server.serve_forever()


def models(url: str) -> dict[str, Any]:
    return {
        "providers": {"product-qa": {
            "baseUrl": url,
            "api": "openai-completions",
            "auth": "none",
            "models": [{
                "id": MODEL,
                "name": "Synthetic product integration QA",
                "contextWindow": 128000,
                "maxTokens": 4096,
            }],
        }},
        "modelBindings": {"modelRoles": {"default": SELECTOR}},
    }


def prepare(runtime: Path, name: str, scenario: str) -> None:
    if scenario not in SCENARIOS:
        raise SystemExit(f"Unsupported scenario: {scenario}")
    provider_info = json.loads((runtime / "provider.json").read_text(encoding="utf-8"))
    case = runtime / "cases" / name
    if case.exists():
        raise SystemExit("Case already exists; use a fresh name to preserve evidence")
    workspace, agent, sessions = case / "workspace", case / "agent", case / "sessions"
    for path in (workspace, agent, sessions, workspace / ".gjc" / "agents"):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    write_json(agent / "models.yml", models(provider_info["url"]))
    write_json(agent / "config.yml", {
        "retry": {"enabled": False, "maxRetries": 0, "requestMaxRetries": 0},
        "task": {"enableLsp": False},
        "notifications": {"enabled": False},
        "telemetry": {"enabled": False},
        "marketplace": {"autoUpdate": False},
    })
    write_json(agent / "credential-auto-import-state.json", {
        "lastImportVersion": "0.16.4", "initialImportResolution": "declined"
    })
    (workspace / "AGENTS.md").write_text(
        "Isolated synthetic product integration QA. Use only the loopback fixture model.\n",
        encoding="utf-8",
    )
    (workspace / ".gjc" / "agents" / "decision-child.md").write_text(
        "---\nname: decision-child\ndescription: Synthetic correlated decision child\n"
        "tools: [read, yield]\nmodel: product-qa/fixture\n---\n"
        "Yield the fixture decision and only consume an exactly correlated resume.\n",
        encoding="utf-8",
    )
    (workspace / ".gjc" / "agents" / "product-child.md").write_text(
        "---\nname: product-child\ndescription: Synthetic product status child\n"
        "tools: [yield, task, subagent]\nmodel: product-qa/fixture\n---\n"
        "Perform only the deterministic loopback fixture action.\n",
        encoding="utf-8",
    )
    socket_path = runtime / "bridge.sock"
    install = gjc_install.install(scope="user", agent_dir=agent, socket_path=socket_path)
    installs: dict[str, Any] = {"user": install}
    if scenario == "duplicate":
        installs["project"] = gjc_install.install(
            scope="project", project_path=workspace, socket_path=socket_path
        )
    write_json(case / "install-results.json", installs)
    environment = {
        "GJC_CODING_AGENT_DIR": str(agent),
        "GJC_AGENT_DIR": str(agent),
        "GJC_AUTOMATION": "1",
        "GJC_DISABLE_TELEMETRY": "1",
        "GJC_MODEL_PRESET_REGISTRY_DISABLED": "1",
        "GJC_UI_LANGUAGE": "en",
        "GJC_NO_PTY": "1",
    }
    executable = shutil.which("gjc")
    if not executable:
        raise SystemExit("gjc executable not found")
    command = [
        executable, "--model", SELECTOR, "--no-title", "--no-lsp", "--no-mcp",
        "--no-rules", "--no-pty", "--thinking", "off", "--session-dir", str(sessions),
        "--tools", "read,ask,task,subagent", f"[PRODUCT_QA:{scenario}]",
    ]
    write_json(case / "environment.json", environment)
    write_json(case / "command.json", command)
    direct = "cd " + shlex.quote(str(workspace)) + " && env " + " ".join(
        f"{key}={shlex.quote(value)}" for key, value in environment.items()
    ) + " " + shlex.join(command)
    (case / "direct-launch-command.txt").write_text(direct + "\n", encoding="utf-8")
    print(json.dumps({
        "case": str(case), "scenario": scenario, "directLaunch": direct,
        "socket": str(socket_path), "registry": str(runtime / "registry.json"),
    }, ensure_ascii=False), flush=True)


def receiver(runtime: Path, generation: int) -> None:
    import orca_keychron_gjc.gjc_source as source_module

    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    original = source_module.parse_snapshot
    wire = runtime / "wire-metadata.jsonl"

    def observed(payload: Any):
        snapshot = original(payload)
        append_jsonl(wire, {
            "receiverGeneration": generation,
            "observedAt": time.time(),
            "version": snapshot.version,
            "type": "snapshot",
            "producerId": snapshot.producer_id,
            "launchId": snapshot.launch_id,
            "sequence": snapshot.sequence,
            "pid": snapshot.pid,
            "startedAt": snapshot.started_at,
            "complete": snapshot.complete,
            "closed": snapshot.closed,
            "root": {
                "sessionId": snapshot.root.session_id,
                "terminalHandle": snapshot.root.terminal_handle,
                "paneKey": snapshot.root.pane_key,
                "worktreeId": snapshot.root.worktree_id,
            },
            "sessions": [{
                "sessionId": row.session_id,
                "role": row.role,
                "state": row.state,
                "pendingAsks": row.pending_asks,
                "pendingDecisions": row.pending_decisions,
            } for row in snapshot.sessions],
        })
        return snapshot

    source_module.parse_snapshot = observed
    status_source = source_module.GjcStatusSource(
        runtime / "bridge.sock", ["orca"], max_slots=12,
        registry_path=runtime / "registry.json",
    )
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_args: stop.set())
    status_source.start()
    info = {
        "pid": os.getpid(), "generation": generation,
        "socket": str(runtime / "bridge.sock"), "registry": str(runtime / "registry.json"),
        "wire": str(wire),
    }
    write_json(runtime / f"receiver-{generation}.json", info)
    print(json.dumps(info), flush=True)
    try:
        while not stop.wait(0.25):
            status_source.indicators()
    finally:
        status_source.stop()


def status(runtime: Path) -> dict[str, Any]:
    socket_path, registry = runtime / "bridge.sock", runtime / "registry.json"
    try:
        response = request_control(socket_path, "status")
        result = {"source": "live", "status": response["status"]}
    except (OSError, ValueError, RuntimeError):
        result = {
            "source": "registry",
            "status": GjcTracker(12, registry).status() if registry.exists()
            else {"version": 1, "maxSlots": 12, "launches": [], "overflow": []},
        }
    return result


def colors(runtime: Path) -> dict[str, Any]:
    result = status(runtime)
    indicators = [GjcIndicator(
        row["launchId"], row["state"], row["slot"], tuple(row["targetPaneKeys"]),
        row["agentCount"], row["pendingRequests"], row["connected"],
    ) for row in result["status"]["launches"] if row["slot"] is not None]
    zone = tuple(range(12))
    rendered = render_zone(indicators, zone)
    return {
        **result,
        "colors": [{"launchId": item.launch_id, "slot": item.slot,
                    "color": list(rendered[zone[item.slot]]),
                    "isOrange": rendered[zone[item.slot]] == ORANGE}
                   for item in indicators],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="operation", required=True)
    for name in ("provider", "receiver", "status", "colors"):
        item = sub.add_parser(name)
        item.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
        if name == "provider":
            item.add_argument("--port", type=int, default=0)
        if name == "receiver":
            item.add_argument("--generation", type=int, required=True)
    item = sub.add_parser("prepare")
    item.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    item.add_argument("--name", required=True)
    item.add_argument("--scenario", required=True, choices=SCENARIOS)
    args = parser.parse_args()
    if args.operation == "provider":
        provider(args.runtime, args.port)
    elif args.operation == "receiver":
        receiver(args.runtime, args.generation)
    elif args.operation == "prepare":
        prepare(args.runtime, args.name, args.scenario)
    elif args.operation == "status":
        print(json.dumps(status(args.runtime), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(colors(args.runtime), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
