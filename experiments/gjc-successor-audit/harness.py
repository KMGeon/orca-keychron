"""Restart/successor audit for unmodified GJC 0.16.4.

The loopback provider is deterministic and has no model account.  Only synthetic
IDs, correlation booleans, lifecycle metadata, and hashes are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from collections.abc import Iterable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

BASE = Path(__file__).resolve().parent
REPO = BASE.parent.parent
DEFAULT_RUNTIME = Path("/private/tmp/gjc-successor-audit")
SELECTOR = "successor-audit/fixture"
MODEL = "fixture"
LOCK = threading.Lock()
EventRecorder = Callable[[dict[str, Any]], None]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with LOCK, path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_text(message: dict[str, Any]) -> str:
    value = message.get("content", "")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            part.get("text", "") for part in value if isinstance(part, dict)
        )
    return ""


def objects(text: str) -> Iterable[dict[str, Any]]:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


def calls_and_results(
    body: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
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
                calls.append({
                    "id": raw.get("id"),
                    "name": function.get("name"),
                    "args": arguments,
                })
        elif message.get("role") == "tool":
            results[str(message.get("tool_call_id", ""))] = content_text(message)
    return calls, results


def returned_child_ids(text: str) -> list[str]:
    return list(
        dict.fromkeys(re.findall(r"^- `([^`]+)` \(job `[^`]+`\)", text, re.MULTILINE))
    )


def pending_envelope(fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "needs_user_decision",
        "request_id": fixture["requestId"],
        "question": fixture["question"],
        "options": fixture["options"],
        "checkpoint": fixture["checkpoint"],
    }


def successor_payload(fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": fixture["requestId"],
        "selected_answer": fixture["actualAnswer"],
        "checkpoint": fixture["checkpoint"],
        "predecessor_child_id": fixture.get("predecessorChildId"),
        "continuation": "successor",
    }


def resume_message(fixture: dict[str, Any], purpose: str) -> str:
    return "[DECISION_RESUME:{}] {}".format(
        purpose,
        json.dumps(successor_payload(fixture), separators=(",", ":")),
    )


def valid_pending(value: dict[str, Any], fixture: dict[str, Any]) -> bool:
    return value == pending_envelope(fixture)


def predecessor_child_plan(
    _body: dict[str, Any], fixture: dict[str, Any], record: EventRecorder
) -> tuple[list[tuple[str, dict[str, Any]]], str | None]:
    record({"event": "predecessor_decision_yielded", "requestId": fixture["requestId"]})
    return [("yield", {"result": {"data": pending_envelope(fixture)}})], None


def successor_child_plan(
    body: dict[str, Any], fixture: dict[str, Any], record: EventRecorder
) -> tuple[list[tuple[str, dict[str, Any]]], str | None]:
    payloads = [
        value
        for message in body.get("messages", [])
        if message.get("role") == "user" and "[SUCCESSOR_CHILD]" in content_text(message)
        for value in objects(content_text(message))
        if {"request_id", "selected_answer", "checkpoint", "continuation"} <= set(value)
    ]
    payload = payloads[-1] if payloads else {}
    request_valid = payload.get("request_id") == fixture["requestId"]
    checkpoint_valid = payload.get("checkpoint") == fixture["checkpoint"]
    answer_valid = payload.get("selected_answer") == fixture["actualAnswer"]
    continuation_valid = payload.get("continuation") == "successor"
    consumed = request_valid and checkpoint_valid and answer_valid and continuation_valid
    record({
        "event": "successor_fields_checked",
        "requestValid": request_valid,
        "checkpointValid": checkpoint_valid,
        "answerValid": answer_valid,
        "continuationValid": continuation_valid,
    })
    data = {
        "status": "completed" if consumed else "correlation_error",
        "request_id": fixture["requestId"],
        "answer_consumed": consumed,
        "outcome": "successor" if consumed else "rejected",
    }
    return [("yield", {"result": {"data": data}})], None


def launch_a_plan(
    body: dict[str, Any], fixture: dict[str, Any], record: EventRecorder
) -> tuple[list[tuple[str, dict[str, Any]]], str | None]:
    calls, results = calls_and_results(body)
    tasks = [call for call in calls if call["name"] == "task"]
    if not tasks:
        return [("task", {
            "agent": "restart-child",
            "tasks": [{
                "id": "predecessor",
                "description": "Yield the restart audit decision",
                "assignment": "[PREDECESSOR_CHILD]",
                "inheritContext": "none",
            }],
        })], None
    child_ids = returned_child_ids(results.get(tasks[0]["id"], ""))
    if len(child_ids) != 1:
        record({"event": "contract_gap", "reason": "predecessor-child-id-missing"})
        return [], "SUCCESSOR_CONTRACT_GAP: actual predecessor child ID was not returned"
    child_id = child_ids[0]
    fixture["predecessorChildId"] = child_id
    awaits = [
        call for call in calls
        if call["name"] == "subagent" and call["args"].get("action") == "await"
        and child_id in call["args"].get("ids", [])
    ]
    if not awaits:
        return [("subagent", {
            "action": "await", "ids": [child_id], "timeout_ms": 10000,
            "verbosity": "full",
        })], None
    reads = [
        call for call in calls
        if call["name"] == "read" and call["args"].get("path") == "agent://" + child_id
    ]
    if not reads:
        return [("read", {"path": "agent://" + child_id})], None
    values = [value for call in reads for value in objects(results.get(call["id"], ""))]
    if not any(valid_pending(value, fixture) for value in values):
        record({"event": "contract_gap", "reason": "predecessor-envelope-invalid"})
        return [], "SUCCESSOR_CONTRACT_GAP: predecessor decision envelope was invalid"
    asks = [
        call for call in calls
        if call["name"] == "ask"
        and any(
            question.get("id") == fixture["requestId"]
            for question in call["args"].get("questions", [])
        )
    ]
    if not asks:
        record({
            "event": "launch_a_question_requested",
            "requestId": fixture["requestId"],
            "actualChildId": child_id,
            "decisionValid": True,
        })
        return [("ask", {"questions": [{
            "id": fixture["requestId"],
            "question": fixture["question"],
            "options": [{"label": option} for option in fixture["options"]],
            "multi": False,
        }]})], None
    answer_match = re.search(r"User selected:\s*([^\n]+)", results.get(asks[-1]["id"], ""))
    answer = answer_match.group(1).strip() if answer_match else None
    if answer != fixture["actualAnswer"]:
        record({"event": "contract_gap", "reason": "actual-answer-mismatch"})
        return [], "SUCCESSOR_CONTRACT_GAP: actual answer did not match fixture data"
    record({
        "event": "launch_a_answer_captured",
        "requestId": fixture["requestId"],
        "actualChildId": child_id,
        "answerValid": True,
        "checkpointPreserved": True,
        "originalResumed": False,
    })
    return [], "SUCCESSOR_LAUNCH_A_CAPTURED: answer preserved; predecessor not resumed"


def old_resume_failed(text: str) -> bool:
    lowered = text.lower()
    indicators = (
        "not found", "not_found", "not registered", "unknown agent", "no agent", "not running",
        "cannot resume", "can't resume", "failed", "error",
    )
    return bool(text.strip()) and any(value in lowered for value in indicators)


def launch_b_plan(
    body: dict[str, Any], fixture: dict[str, Any], record: EventRecorder
) -> tuple[list[tuple[str, dict[str, Any]]], str | None]:
    predecessor = fixture.get("predecessorChildId")
    if not predecessor:
        record({"event": "contract_gap", "reason": "predecessor-id-not-persisted"})
        return [], "SUCCESSOR_CONTRACT_GAP: predecessor ID was not persisted"
    calls, results = calls_and_results(body)
    old_resumes = [
        call for call in calls
        if call["name"] == "subagent" and call["args"].get("action") == "resume"
        and call["args"].get("id") == predecessor
    ]
    if not old_resumes:
        return [("subagent", {
            "action": "resume",
            "id": predecessor,
            "message": resume_message(fixture, "restart-successor-probe"),
        })], None
    old_result = results.get(old_resumes[-1]["id"], "")
    if not old_resume_failed(old_result):
        record({"event": "contract_gap", "reason": "predecessor-resume-not-rejected"})
        return [], "SUCCESSOR_CONTRACT_GAP: old in-memory child resume was not rejected"
    record({
        "event": "old_resume_rejected",
        "actualChildId": predecessor,
        "reproducibleFailure": True,
        "resultSha256": hashlib.sha256(old_result.encode()).hexdigest(),
    })
    tasks = [call for call in calls if call["name"] == "task"]
    if not tasks:
        assignment = "[SUCCESSOR_CHILD] " + json.dumps(
            successor_payload(fixture), separators=(",", ":")
        )
        return [("task", {
            "agent": "restart-child",
            "tasks": [{
                "id": "successor",
                "description": "Continue from the preserved synthetic decision",
                "assignment": assignment,
                "inheritContext": "none",
            }],
        })], None
    child_ids = returned_child_ids(results.get(tasks[-1]["id"], ""))
    if len(child_ids) != 1:
        record({"event": "contract_gap", "reason": "successor-child-id-missing"})
        return [], "SUCCESSOR_CONTRACT_GAP: actual successor child ID was not returned"
    successor = child_ids[0]
    if successor == predecessor:
        record({"event": "contract_gap", "reason": "successor-id-collision"})
        return [], "SUCCESSOR_ID_COLLISION: successor reused predecessor identity"
    awaits = [
        call for call in calls
        if call["name"] == "subagent" and call["args"].get("action") == "await"
        and successor in call["args"].get("ids", [])
    ]
    if not awaits:
        return [("subagent", {
            "action": "await", "ids": [successor], "timeout_ms": 10000,
            "verbosity": "full",
        })], None
    reads = [
        call for call in calls
        if call["name"] == "read" and call["args"].get("path") == "agent://" + successor
    ]
    if not reads:
        return [("read", {"path": "agent://" + successor})], None
    values = [value for call in reads for value in objects(results.get(call["id"], ""))]
    completed = any(
        value.get("status") == "completed"
        and value.get("request_id") == fixture["requestId"]
        and value.get("answer_consumed") is True
        and value.get("outcome") == "successor"
        for value in values
    )
    if not completed:
        record({"event": "contract_gap", "reason": "successor-outcome-invalid"})
        return [], "SUCCESSOR_CONTRACT_GAP: successor did not confirm the preserved answer"
    record({
        "event": "successor_completed",
        "predecessorChildId": predecessor,
        "successorChildId": successor,
        "identityDiffers": True,
        "requestIdPreserved": True,
        "checkpointPreserved": True,
        "answerConsumed": True,
        "outcome": "successor",
        "originalResumed": False,
    })
    return [], "SUCCESSOR_FLOW_COMPLETE: explicit successor consumed preserved answer"


class ProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: Any) -> None:
        pass

    def record(self, value: dict[str, Any]) -> None:
        append_jsonl(self.server.metadata_path, {"time": time.time(), **value})

    def send_json(self, code: int, value: Any) -> None:
        payload = json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        self.send_json(200, {"ok": True, "scope": "loopback successor audit"})

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        if self.path != "/v1/chat/completions" or size > 4_000_000:
            self.send_json(400, {"error": {"message": "bounded fixture rejection"}})
            return
        body = json.loads(self.rfile.read(size))
        fixture_path = self.server.runtime / "fixture-data.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        users = [
            content_text(message)
            for message in body.get("messages", [])
            if message.get("role") == "user"
        ]
        joined = "\n".join(users)
        if "[PREDECESSOR_CHILD]" in joined:
            actions, message = predecessor_child_plan(body, fixture, self.record)
            side = "predecessor-child"
        elif "[SUCCESSOR_CHILD]" in joined:
            actions, message = successor_child_plan(body, fixture, self.record)
            side = "successor-child"
        elif "[SUCCESSOR_ROOT:B]" in joined:
            actions, message = launch_b_plan(body, fixture, self.record)
            side = "launch-b"
        else:
            actions, message = launch_a_plan(body, fixture, self.record)
            side = "launch-a"
        if fixture.get("predecessorChildId"):
            write_json(fixture_path, fixture)
        self.record({
            "event": "model_response", "side": side,
            "toolNames": [name for name, _ in actions], "terminalText": bool(message),
        })
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        response_id = uuid.uuid4().hex

        def emit(delta: dict[str, Any], finish: str | None = None) -> None:
            data = {
                "id": "chatcmpl-" + response_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": MODEL,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            self.wfile.write(("data: " + json.dumps(data) + "\n\n").encode())
            self.wfile.flush()

        try:
            emit({"role": "assistant", "content": ""})
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
        except (BrokenPipeError, ConnectionResetError):
            self.record({"event": "client_disconnected", "side": side})


def provider(runtime: Path, port: int) -> None:
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    runtime.chmod(0o700)
    server = ThreadingHTTPServer(("127.0.0.1", port), ProviderHandler)
    server.daemon_threads = True
    server.runtime = runtime
    server.metadata_path = runtime / "provider-metadata.jsonl"
    write_json(runtime / "provider.json", {
        "pid": os.getpid(),
        "port": server.server_port,
        "url": f"http://127.0.0.1:{server.server_port}/v1",
        "metadata": str(server.metadata_path),
    })
    server.serve_forever()


def safe_extract_wheel(wheel: Path, destination: Path) -> Path:
    wheel = wheel.resolve(strict=True)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    with zipfile.ZipFile(str(wheel)) as archive:
        root = destination.resolve()
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if root != target and root not in target.parents:
                raise ValueError(f"unsafe wheel member: {member.filename}")
        archive.extractall(str(destination))
    return destination


def add_product_path(product_path: Path) -> None:
    resolved = str(product_path.resolve(strict=True))
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


def minimal_process_env(runtime: Path) -> dict[str, str]:
    home = runtime / "home"
    temp = runtime / "tmp"
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp.mkdir(mode=0o700, parents=True, exist_ok=True)
    return {
        "HOME": str(home),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "TMPDIR": str(temp),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "TERM": "xterm-256color",
        "SHELL": "/bin/zsh",
    }


def models(url: str) -> dict[str, Any]:
    return {
        "providers": {"successor-audit": {
            "baseUrl": url,
            "api": "openai-completions",
            "auth": "none",
            "models": [{
                "id": MODEL,
                "name": "Synthetic GJC restart successor audit",
                "contextWindow": 128000,
                "maxTokens": 4096,
            }],
        }},
        "modelBindings": {"modelRoles": {"default": SELECTOR}},
    }


def prepare(runtime: Path, product_path: Path) -> dict[str, Any]:
    add_product_path(product_path)
    from orca_keychron_gjc import gjc_install

    provider_info = json.loads((runtime / "provider.json").read_text(encoding="utf-8"))
    case = runtime / "case"
    workspace, agent, sessions = case / "workspace", case / "agent", case / "sessions"
    for path in (workspace, agent, sessions, workspace / ".gjc" / "agents"):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    fixture = {
        "requestId": "req_restart",
        "question": "Continue the restart-safe synthetic operation?",
        "options": ["Continue with A", "Continue with B"],
        "checkpoint": "checkpoint-restart-v1",
        "actualAnswer": "Continue with A",
    }
    write_json(runtime / "fixture-data.json", fixture)
    write_json(agent / "models.yml", models(provider_info["url"]))
    write_json(agent / "config.yml", {
        "retry": {"enabled": False, "maxRetries": 0, "requestMaxRetries": 0},
        "task": {"enableLsp": False},
        "notifications": {"enabled": False},
        "telemetry": {"enabled": False},
        "marketplace": {"autoUpdate": False},
    })
    write_json(agent / "credential-auto-import-state.json", {
        "lastImportVersion": "0.16.4", "initialImportResolution": "declined",
    })
    (workspace / "AGENTS.md").write_text(
        "Isolated loopback-only restart successor audit. No real model or external I/O.\n",
        encoding="utf-8",
    )
    (workspace / ".gjc" / "agents" / "restart-child.md").write_text(
        "---\nname: restart-child\ndescription: Synthetic restart decision child\n"
        "tools: [yield]\nmodel: successor-audit/fixture\n---\n"
        "Perform only the deterministic loopback fixture action.\n",
        encoding="utf-8",
    )
    socket_path = runtime / "bridge.sock"
    install = gjc_install.install(scope="user", agent_dir=agent, socket_path=socket_path)
    write_json(case / "install-result.json", install)
    hook_source = product_path / "orca_keychron_gjc" / "assets" / "gjc_hook.ts"
    releases = list((agent / ".orca-keychron" / "releases").glob("*/gjc_hook.ts"))
    if len(releases) != 1:
        raise AssertionError("isolated install did not create exactly one hook release")
    environment = {
        **minimal_process_env(runtime),
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
        raise RuntimeError("gjc executable not found")

    def command(marker: str) -> list[str]:
        return [
            executable, "--model", SELECTOR, "--no-title", "--no-lsp", "--no-mcp",
            "--no-rules", "--no-pty", "--thinking", "off", "--session-dir",
            str(sessions), "--tools", "read,ask,task,subagent", marker,
        ]

    def direct(marker: str) -> str:
        forwarded_orca = " ".join(
            f'{name}="${name}"'
            for name in ("ORCA_TERMINAL_HANDLE", "ORCA_PANE_KEY", "ORCA_WORKTREE_ID")
        )
        return "cd {} && env -i {} {} {}".format(
            shlex.quote(str(workspace)),
            " ".join(f"{key}={shlex.quote(value)}" for key, value in environment.items()),
            forwarded_orca,
            shlex.join(command(marker)),
        )

    prepared = {
        "case": str(case),
        "sourceHookSha256": sha256(hook_source),
        "installedHookSha256": sha256(releases[0]),
        "commands": {"launchA": direct("[SUCCESSOR_ROOT:A]"),
                     "launchB": direct("[SUCCESSOR_ROOT:B]")},
    }
    assert prepared["sourceHookSha256"] == prepared["installedHookSha256"]
    write_json(case / "prepared.json", prepared)
    return prepared


def receiver(runtime: Path, product_path: Path) -> None:
    add_product_path(product_path)
    import orca_keychron_gjc.gjc_source as source_module

    original = source_module.parse_snapshot
    wire = runtime / "wire-metadata.jsonl"

    def observed(payload: Any) -> Any:
        snapshot = original(payload)
        append_jsonl(wire, {
            "observedAt": time.time(),
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
    source = source_module.GjcStatusSource(
        runtime / "bridge.sock", ["orca"], max_slots=12,
        registry_path=runtime / "registry.json",
    )
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_args: stop.set())
    source.start()
    write_json(runtime / "receiver.json", {"pid": os.getpid(), "wire": str(wire)})
    try:
        while not stop.wait(0.25):
            source.indicators()
    finally:
        source.stop()


def status(runtime: Path, product_path: Path) -> dict[str, Any]:
    add_product_path(product_path)
    from orca_keychron_gjc.gjc_source import request_control

    return request_control(runtime / "bridge.sock", "status")["status"]


def assert_waiting_before_answer(row: dict[str, Any]) -> None:
    assert row["state"] == "waiting", "launch must remain waiting before a valid answer"
    assert row["pendingRequests"] >= 1, "pending decision/ask must remain unresolved"
    assert row["connected"] is True, "pre-answer launch must be live"


def assert_answer_resolved(row: dict[str, Any]) -> None:
    assert row["pendingRequests"] == 0, "valid answer must resolve pending decision state"


def run_json(command: list[str], timeout: float = 15.0) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {result.stderr.strip()}"
        )
    return json.loads(result.stdout)


def orca(*arguments: str) -> dict[str, Any]:
    return run_json(["orca", *arguments, "--json"])


def jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def wait_for(predicate: Callable[[], Any], description: str, timeout: float = 30.0) -> Any:
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value:
            return value
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for {description}")
        threading.Event().wait(min(0.1, remaining))


def find_event(path: Path, event: str) -> dict[str, Any] | None:
    return next((row for row in reversed(jsonl(path)) if row.get("event") == event), None)


def terminal_text(handle: str) -> str:
    response = orca("terminal", "read", "--terminal", handle)
    terminal = response["result"]["terminal"]
    return "\n".join(terminal.get("tail", []))


def create_terminal(title: str, command: str) -> str:
    response = orca(
        "terminal", "create", "--worktree", "active", "--title", title,
        "--command", command,
    )
    return response["result"]["terminal"]["handle"]


def close_terminal(handle: str) -> dict[str, Any]:
    return orca("terminal", "close", "--terminal", handle)


def send_terminal(handle: str, text: str, enter: bool = False) -> None:
    arguments = ["terminal", "send", "--terminal", handle, "--text", text]
    if enter:
        arguments.append("--enter")
    orca(*arguments)


def launch_row(runtime: Path, product_path: Path, handle: str) -> dict[str, Any] | None:
    for row in status(runtime, product_path).get("launches", []):
        if handle in row.get("targetPaneKeys", []) or row.get("terminalHandle") == handle:
            return row
    # Current status schema exposes pane targets, while exact terminal is in wire metadata.
    launch_ids = {
        row["launchId"] for row in jsonl(runtime / "wire-metadata.jsonl")
        if row.get("root", {}).get("terminalHandle") == handle
    }
    return next(
        (row for row in status(runtime, product_path).get("launches", [])
         if row.get("launchId") in launch_ids),
        None,
    )


def stop_process(process: subprocess.Popen) -> dict[str, Any]:
    outcome = {"pid": process.pid, "terminated": False, "killed": False}
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
            outcome["terminated"] = True
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            outcome["killed"] = True
    else:
        outcome["terminated"] = True
    outcome["returncode"] = process.returncode
    return outcome


def owned_broker_pids(runtime: Path) -> list[int]:
    agent_dir = str(runtime / "case" / "agent")
    result = subprocess.run(
        ["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=True
    )
    pids = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) != 2:
            continue
        command = fields[1]
        if "gjc sdk broker-internal" in command and "--agent-dir " + agent_dir in command:
            pids.append(int(fields[0]))
    return pids


def stop_owned_pid(pid: int) -> dict[str, Any]:
    outcome = {"pid": pid, "terminated": False, "killed": False, "kind": "gjc-broker"}
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        outcome["terminated"] = True
        return outcome
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            outcome["terminated"] = True
            return outcome
        threading.Event().wait(0.1)
    os.kill(pid, signal.SIGKILL)
    outcome["killed"] = True
    return outcome


def perform(
    runtime: Path, wheel: Path | None, expected_wheel_sha256: str | None = None
) -> dict[str, Any]:
    runtime = runtime.resolve()
    if runtime.exists():
        raise RuntimeError("runtime already exists; use a fresh --runtime")
    if Path("/private/tmp") not in runtime.parents:
        raise RuntimeError("runtime must be a fresh canonical path below /private/tmp")
    runtime.mkdir(mode=0o700, parents=True)
    if wheel:
        product_path = safe_extract_wheel(wheel, runtime / "product")
        wheel_sha256 = sha256(wheel.resolve())
        if expected_wheel_sha256 and wheel_sha256 != expected_wheel_sha256:
            raise RuntimeError("frozen wheel SHA-256 does not match the expected digest")
        product_provenance = {
            "kind": "wheel-extracted-import",
            "path": str(wheel.resolve()),
            "sha256": wheel_sha256,
            "expectedSha256": expected_wheel_sha256,
        }
    else:
        product_path = REPO / "src"
        product_provenance = {
            "kind": "workspace",
            "path": str(product_path),
            "hookSha256": sha256(product_path / "orca_keychron_gjc/assets/gjc_hook.ts"),
        }
    provider_process: subprocess.Popen | None = None
    receiver_process: subprocess.Popen | None = None
    terminals: list[str] = []
    cleanup: dict[str, Any] = {"terminals": [], "processes": []}
    evidence: dict[str, Any] = {
        "schemaVersion": 1,
        "verdict": "failed",
        "runtime": str(runtime),
        "gjcVersion": subprocess.run(
            ["gjc", "--version"], capture_output=True, text=True, check=True,
            env=minimal_process_env(runtime),
        ).stdout.strip(),
        "product": product_provenance,
        "requirements": ["GJC-DECISION-RESTART", "GJC-LAUNCH-LIFECYCLE", "GJC-0.16.4"],
        "auditInputs": {
            "harnessSha256": sha256(BASE / "harness.py"),
            "testSha256": sha256(REPO / "tests/test_gjc_successor_fixture.py"),
            "workspaceHookSha256Before": sha256(
                REPO / "src/orca_keychron_gjc/assets/gjc_hook.ts"
            ),
        },
    }
    try:
        base_command = [sys.executable, str(BASE / "harness.py")]
        provider_process = subprocess.Popen(
            base_command + ["provider", "--runtime", str(runtime), "--port", "0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            env=minimal_process_env(runtime),
        )
        wait_for(lambda: (runtime / "provider.json").exists(), "provider readiness")
        prepared = prepare(runtime, product_path)
        receiver_process = subprocess.Popen(
            base_command + ["receiver", "--runtime", str(runtime),
                            "--product-path", str(product_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            env=minimal_process_env(runtime),
        )
        wait_for(lambda: (runtime / "receiver.json").exists(), "receiver readiness")
        wait_for(lambda: (runtime / "bridge.sock").exists(), "receiver socket")
        metadata = runtime / "provider-metadata.jsonl"

        launch_a_handle = create_terminal("gjc-successor-a", prepared["commands"]["launchA"])
        terminals.append(launch_a_handle)
        wait_for(
            lambda: find_event(metadata, "launch_a_question_requested"),
            "launch A parent question",
        )
        wait_for(
            lambda: fixture_question_visible(launch_a_handle),
            "launch A actual question surface",
        )
        waiting_a = wait_for(
            lambda: launch_row(runtime, product_path, launch_a_handle),
            "launch A product status",
        )
        assert_waiting_before_answer(waiting_a)
        send_terminal(launch_a_handle, "", enter=True)
        captured = wait_for(
            lambda: find_event(metadata, "launch_a_answer_captured"),
            "launch A valid answer capture",
        )
        answered_a = wait_for(
            lambda: resolved_launch_row(runtime, product_path, launch_a_handle),
            "launch A pending resolution",
        )
        assert_answer_resolved(answered_a)
        wire_a = [
            row for row in jsonl(runtime / "wire-metadata.jsonl")
            if row.get("root", {}).get("terminalHandle") == launch_a_handle
        ]
        assert wire_a, "launch A emitted no native hook snapshots"
        launch_a_id = wire_a[-1]["launchId"]
        launch_a_pid = wire_a[-1]["pid"]
        send_terminal(launch_a_handle, "/exit", enter=True)
        closed_a = wait_for(
            lambda: next((
                row for row in reversed(jsonl(runtime / "wire-metadata.jsonl"))
                if row.get("launchId") == launch_a_id and row.get("closed") is True
            ), None),
            "launch A closed snapshot",
        )
        wait_for(
            lambda: all(
                row.get("launchId") != launch_a_id
                for row in status(runtime, product_path).get("launches", [])
            ),
            "launch A tracker removal",
        )

        launch_b_handle = create_terminal("gjc-successor-b", prepared["commands"]["launchB"])
        terminals.append(launch_b_handle)
        rejected = wait_for(
            lambda: find_event(metadata, "old_resume_rejected"),
            "fresh-process predecessor resume rejection",
        )
        completed = wait_for(
            lambda: find_event(metadata, "successor_completed"),
            "successor completion",
        )
        row_b = wait_for(
            lambda: launch_row(runtime, product_path, launch_b_handle),
            "launch B product status",
        )
        assert row_b["launchId"] != launch_a_id, "fresh GJC process must have a new launch ID"
        assert row_b["pendingRequests"] == 0
        assert row_b["state"] == "done"
        wire_b = [
            row for row in jsonl(runtime / "wire-metadata.jsonl")
            if row.get("root", {}).get("terminalHandle") == launch_b_handle
        ]
        assert wire_b, "launch B emitted no native hook snapshots"
        assert wire_b[-1]["pid"] != launch_a_pid, "fresh GJC process must have a new PID"
        launch_b_id = wire_b[-1]["launchId"]
        send_terminal(launch_b_handle, "/exit", enter=True)
        closed_b = wait_for(
            lambda: next((
                row for row in reversed(jsonl(runtime / "wire-metadata.jsonl"))
                if row.get("launchId") == launch_b_id and row.get("closed") is True
            ), None),
            "launch B closed snapshot",
        )
        fixture = json.loads((runtime / "fixture-data.json").read_text(encoding="utf-8"))
        evidence.update({
            "verdict": "pass",
            "fixtureData": fixture,
            "install": {
                "sourceHookSha256": prepared["sourceHookSha256"],
                "installedHookSha256": prepared["installedHookSha256"],
                "isolated": True,
            },
            "launchA": {
                "terminalHandle": launch_a_handle,
                "launchId": launch_a_id,
                "pid": launch_a_pid,
                "preAnswer": waiting_a,
                "postAnswer": answered_a,
                "answerCapture": captured,
                "closed": {"sequence": closed_a["sequence"], "closed": True},
            },
            "launchB": {
                "terminalHandle": launch_b_handle,
                "launchId": launch_b_id,
                "pid": wire_b[-1]["pid"],
                "predecessorResume": rejected,
                "successor": completed,
                "finalStatus": row_b,
                "closed": {"sequence": closed_b["sequence"], "closed": True},
            },
            "assertions": {
                "actualPredecessorYieldedPendingDecision": True,
                "unresolvedUntilValidActualAnswer": True,
                "predecessorNotResumableAfterRestart": True,
                "successorIdentityDiffers": True,
                "requestCheckpointAnswerValidated": True,
                "finalOutcomeExplicitSuccessor": True,
                "launchIdsAndPidsDistinct": True,
                "productStatusLifecycleValidated": True,
                "realModelUsed": False,
                "physicalHidUsed": False,
            },
        })
        return evidence
    except Exception as error:
        evidence["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        for handle in reversed(terminals):
            try:
                result = close_terminal(handle)
                cleanup["terminals"].append({
                    "handle": handle,
                    "ptyKilled": result["result"]["close"]["ptyKilled"],
                })
            except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
                cleanup["terminals"].append({"handle": handle, "error": str(error)})
        for process in (receiver_process, provider_process):
            if process is not None:
                cleanup["processes"].append(stop_process(process))
        for pid in owned_broker_pids(runtime):
            cleanup["processes"].append(stop_owned_pid(pid))
        cleanup["ownedBrokerPidsRemaining"] = owned_broker_pids(runtime)
        socket_path = runtime / "bridge.sock"
        if socket_path.exists():
            socket_path.unlink()
        cleanup["socketRemoved"] = not socket_path.exists()
        evidence["cleanup"] = cleanup
        evidence["auditInputs"]["workspaceHookSha256After"] = sha256(
            REPO / "src/orca_keychron_gjc/assets/gjc_hook.ts"
        )
        evidence["auditInputs"]["workspaceHookUnchanged"] = (
            evidence["auditInputs"]["workspaceHookSha256Before"]
            == evidence["auditInputs"]["workspaceHookSha256After"]
        )
        write_json(runtime / "verdict.json", evidence)


def fixture_question_visible(handle: str) -> bool:
    text = terminal_text(handle)
    return "Continue the restart-safe synthetic operation?" in text and "Continue with A" in text


def resolved_launch_row(
    runtime: Path, product_path: Path, handle: str
) -> dict[str, Any] | None:
    row = launch_row(runtime, product_path, handle)
    if row and row.get("pendingRequests") == 0:
        return row
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="operation", required=True)
    provider_parser = sub.add_parser("provider")
    provider_parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    provider_parser.add_argument("--port", type=int, default=0)
    receiver_parser = sub.add_parser("receiver")
    receiver_parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    receiver_parser.add_argument("--product-path", type=Path, required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    run_parser.add_argument("--wheel", type=Path)
    run_parser.add_argument("--expected-wheel-sha256")
    args = parser.parse_args()
    if args.operation == "provider":
        provider(args.runtime.resolve(), args.port)
    elif args.operation == "receiver":
        receiver(args.runtime.resolve(), args.product_path)
    else:
        evidence = perform(args.runtime, args.wheel, args.expected_wheel_sha256)
        print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
