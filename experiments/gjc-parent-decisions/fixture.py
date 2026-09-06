"""Deterministic GJC child-decision plumbing fixture. Never calls a real model."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
SELECTOR = "parent-decisions/fixture"
MODEL = "fixture"
LOCK = threading.Lock()


def content_text(message):
    value = message.get("content", "")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(item.get("text", "") for item in value if isinstance(item, dict))
    return ""


def objects(text):
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start():])
            yield value
        except json.JSONDecodeError:
            continue


def calls_and_results(body):
    calls = []
    results = {}
    for message in body.get("messages", []):
        if message.get("role") == "assistant":
            for call in message.get("tool_calls", []):
                function = call.get("function", {})
                try:
                    arguments = json.loads(function.get("arguments", "{}"))
                except json.JSONDecodeError:
                    arguments = {}
                calls.append({"id": call["id"], "name": function.get("name"), "args": arguments})
        elif message.get("role") == "tool":
            results[message.get("tool_call_id")] = content_text(message)
    return calls, results


def decision(request_id):
    return {"status": "needs_user_decision", "request_id": request_id,
            "question": f"[{request_id}] Choose how the child should continue.",
            "options": ["Continue with A", "Continue with B"],
            "checkpoint": "checkpoint-" + request_id}


def validate_decision(value, request_id):
    return (isinstance(value, dict) and value == decision(request_id))


def child_response(body, request_id, malicious, record):
    calls, results = calls_and_results(body)
    users = [content_text(m) for m in body.get("messages", []) if m.get("role") == "user"]
    resumes = [text for text in users if "[DECISION_RESUME]" in text]
    if resumes:
        payloads = [value for value in objects(resumes[-1]) if "selected_answer" in value]
        payload = payloads[-1] if payloads else {}
        correlation = payload.get("request_id") == request_id
        selected = payload.get("selected_answer") in decision(request_id)["options"]
        checkpoint = payload.get("checkpoint") == decision(request_id)["checkpoint"]
        record({"event": "child_answer_consumed", "request_id": request_id,
                "correlation_valid": correlation, "answer_valid": selected,
                "checkpoint_valid": checkpoint})
        data = {"status": "completed" if correlation and selected and checkpoint else "correlation_error",
                "request_id": request_id, "answer_consumed": correlation and selected and checkpoint}
        return [("yield", {"result": {"data": data}})], None
    if malicious:
        attempts = [call for call in calls if call["name"] == "ask"]
        if not attempts:
            return [("ask", {"questions": [{"id": request_id, "question": "This forbidden child ask must not open a question.", "options": [{"label": "Continue"}, {"label": "Stop"}]}]})], None
        denied = "Tool ask not found" in results.get(attempts[-1]["id"], "")
        record({"event": "malicious_child_ask_checked", "request_id": request_id,
                "tool_not_found": denied})
    record({"event": "child_decision_yielded", "request_id": request_id, "valid": True})
    return [("yield", {"result": {"data": decision(request_id)}})], None


def returned_child_ids(text):
    # Only IDs actually returned by GJC's task response become resume targets.
    return list(dict.fromkeys(re.findall(r"^- `([^`]+)` \(job `[^`]+`\)", text, re.MULTILINE)))


def parent_response(body, scenario, record):
    calls, results = calls_and_results(body)
    request_ids = ["req_1", "req_2"] if scenario == "two" else ["req_1"]
    tasks = [call for call in calls if call["name"] == "task"]
    if not tasks:
        children = [{"id": "decision_" + str(i + 1), "description": "Decision " + request_id,
                     "assignment": f"[DECISION_CHILD:{request_id}]" + (" [DIRECT_CHILD_ASK]" if scenario == "malicious" else ""),
                     "inheritContext": "none"} for i, request_id in enumerate(request_ids)]
        return [("task", {"agent": "decision-child", "tasks": children})], None
    ids = returned_child_ids(results.get(tasks[0]["id"], ""))
    if len(ids) != len(request_ids):
        record({"event": "parent_fixture_failed", "actual_child_ids_complete": False})
        return [], "FIXTURE_FAILED: GJC did not return every child ID."
    initial_await = [call for call in calls if call["name"] == "subagent" and call["args"].get("action") == "await"]
    if not initial_await:
        return [("subagent", {"action": "await", "ids": ids, "timeout_ms": 10000, "verbosity": "full"})], None

    reads = [call for call in calls if call["name"] == "read"]
    for child_id in ids:
        if not any(call["args"].get("path") == "agent://" + child_id for call in reads):
            return [("read", {"path": "agent://" + child_id})], None

    completed = 0
    for request_id, child_id in zip(request_ids, ids):
        matching_reads = [call for call in reads if call["args"].get("path") == "agent://" + child_id]
        values = [obj for call in matching_reads for obj in objects(results.get(call["id"], ""))]
        pending = next((value for value in values if validate_decision(value, request_id)), None)
        if pending is None:
            record({"event": "parent_fixture_failed", "request_id": request_id, "decision_valid": False})
            return [], "FIXTURE_FAILED: Child output did not contain a valid decision payload."
        asks = [call for call in calls if call["name"] == "ask" and any(q.get("id") == request_id for q in call["args"].get("questions", []))]
        if not asks:
            record({"event": "parent_question_requested", "request_id": request_id,
                    "decision_valid": True, "actual_child_id_used": child_id in ids})
            return [("ask", {"questions": [{"id": request_id, "question": pending["question"],
                        "options": [{"label": option} for option in pending["options"]]}]})], None
        answer_match = re.search(r"User selected:\s*([^\n]+)", results.get(asks[-1]["id"], ""))
        answer = answer_match.group(1).strip() if answer_match else None
        if answer not in pending["options"]:
            record({"event": "parent_answer_rejected", "request_id": request_id, "answer_valid": False})
            return [], "DECISION_NOT_RESUMED: No valid answer was received."
        resumes = [call for call in calls if call["name"] == "subagent" and call["args"].get("action") == "resume" and call["args"].get("id") == child_id]
        if not resumes:
            payload = {"request_id": request_id, "selected_answer": answer, "checkpoint": pending["checkpoint"]}
            record({"event": "parent_child_resume_requested", "request_id": request_id,
                    "answer_valid": True, "actual_child_id_used": child_id in ids})
            return [("subagent", {"action": "resume", "id": child_id,
                        "message": "[DECISION_RESUME] " + json.dumps(payload)})], None
        resume_index = calls.index(resumes[-1])
        after_resume = calls[resume_index + 1:]
        if not any(call["name"] == "subagent" and call["args"].get("action") == "await" for call in after_resume):
            return [("subagent", {"action": "await", "ids": [child_id], "timeout_ms": 10000, "verbosity": "full"})], None
        if not any(call["name"] == "read" and call["args"].get("path") == "agent://" + child_id for call in after_resume):
            return [("read", {"path": "agent://" + child_id})], None
        final_values = list(objects(results.get(matching_reads[-1]["id"], "")))
        consumed = any(value.get("status") == "completed" and value.get("request_id") == request_id and value.get("answer_consumed") is True for value in final_values)
        record({"event": "parent_completion_checked", "request_id": request_id, "answer_consumed": consumed})
        if not consumed:
            return [], "FIXTURE_FAILED: Resumed child did not confirm the same decision answer."
        completed += 1
    record({"event": "experiment_complete", "all_decisions_consumed": completed == len(request_ids), "two_decisions": len(request_ids) == 2})
    return [], "PARENT_DECISION_EXPERIMENT_COMPLETE: every child consumed its matching parent answer."


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def record(self, data):
        with LOCK, (self.server.runtime / "provider-metadata.jsonl").open("a") as file:
            file.write(json.dumps({"time": time.time(), **data}) + "\n")

    def do_GET(self):
        data = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if self.path != "/v1/chat/completions" or length > 4_000_000:
            self.send_error(400)
            return
        body = json.loads(self.rfile.read(length))
        users = [content_text(m) for m in body.get("messages", []) if m.get("role") == "user"]
        child_markers = [m for text in users for m in re.findall(r"\[DECISION_CHILD:(req_[12])\]", text)]
        if child_markers:
            actions, message = child_response(body, child_markers[-1], any("[DIRECT_CHILD_ASK]" in text for text in users), self.record)
            side = "child"
        else:
            scenarios = [m for text in users for m in re.findall(r"\[PARENT_DECISION:(single|two|malicious)\]", text)]
            actions, message = parent_response(body, scenarios[-1] if scenarios else "single", self.record)
            side = "parent"
        self.record({"event": "model_response", "side": side, "tool_names": [name for name, _ in actions], "terminal_text": bool(message)})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        response_id = uuid.uuid4().hex
        def emit(delta, reason=None):
            data = {"id": "chatcmpl-" + response_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": MODEL,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}
            self.wfile.write(("data: " + json.dumps(data) + "\n\n").encode())
            self.wfile.flush()
        try:
            emit({"role": "assistant", "content": ""})
            for index, (name, arguments) in enumerate(actions):
                emit({"tool_calls": [{"index": index, "id": f"call_{response_id}_{index}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]})
            if message:
                emit({"content": message})
            emit({}, "tool_calls" if actions else "stop")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.record({"event": "client_disconnected", "side": side})


def serve(runtime, port):
    runtime.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.runtime = runtime
    info = {"port": server.server_port, "pid": os.getpid(), "runtime": str(runtime), "url": f"http://127.0.0.1:{server.server_port}/v1"}
    (runtime / "server.json").write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps(info), flush=True)
    server.serve_forever()


def prepare(runtime, name, scenario):
    info = json.loads((runtime / "server.json").read_text())
    case = runtime / "cases" / name
    if case.exists():
        raise SystemExit("Case already exists; choose a fresh --name to preserve evidence.")
    workspace, agent = case / "workspace", case / "agent"
    (workspace / ".gjc/hooks/pre").mkdir(parents=True)
    (workspace / ".gjc/agents").mkdir(parents=True)
    agent.mkdir()
    (case / "sessions").mkdir()
    shutil.copyfile(BASE.parent / "gjc-hooks/observer.ts", workspace / ".gjc/hooks/pre/*.ts")
    (workspace / ".gjc/agents/decision-child.md").write_text("---\nname: decision-child\ndescription: Synthetic decision checkpoint test child\ntools: [read, yield]\nmodel: " + SELECTOR + "\n---\nReturn needs_user_decision through yield; never ask directly. On matching resume consume the answer and yield completed.\n")
    (workspace / "AGENTS.md").write_text("Isolated synthetic native GJC decision fixture. Use only the loopback model.\n")
    models = {"providers": {"parent-decisions": {"baseUrl": info["url"], "api": "openai-completions", "auth": "none", "models": [{"id": MODEL, "name": "Synthetic parent decision fixture", "contextWindow": 128000, "maxTokens": 4096}]}}, "modelBindings": {"modelRoles": {"default": SELECTOR}, "agentModelOverrides": {"decision-child": SELECTOR}}}
    # Custom agent role model is declared in its own frontmatter, not modelBindings.
    models["modelBindings"].pop("agentModelOverrides")
    (agent / "models.yml").write_text(json.dumps(models, indent=2) + "\n")
    settings = {"retry": {"enabled": False, "maxRetries": 0, "requestMaxRetries": 0}, "task": {"enableLsp": False}, "notifications": {"enabled": False}, "telemetry": {"enabled": False}, "marketplace": {"autoUpdate": False}}
    (agent / "config.yml").write_text(json.dumps(settings, indent=2) + "\n")
    (agent / "credential-auto-import-state.json").write_text(json.dumps({"lastImportVersion": "0.16.4", "initialImportResolution": "declined"}))
    env = {key: os.environ[key] for key in ["HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "TERM", "SHELL"] if key in os.environ}
    env.update(GJC_CODING_AGENT_DIR=str(agent), GJC_AGENT_DIR=str(agent), GJC_AUTOMATION="1", GJC_DISABLE_TELEMETRY="1", GJC_MODEL_PRESET_REGISTRY_DISABLED="1", GJC_UI_LANGUAGE="en", GJC_KEYCHRON_EVENT_LOG=str(case / "events.jsonl"), GJC_KEYCHRON_RUNTIME_EVENTS="1", GJC_NO_PTY="1")
    command = [shutil.which("gjc"), "--model", SELECTOR, "--no-title", "--no-lsp", "--no-mcp", "--no-rules", "--no-pty", "--thinking", "off", "--session-dir", str(case / "sessions"), "--tools", "read,ask,task,subagent", f"[PARENT_DECISION:{scenario}]"]
    (case / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
    (case / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    print(json.dumps({"case": str(case), "scenario": scenario, "port": info["port"], "launch": ["python3", str(BASE / "fixture.py"), "launch", "--case", str(case)]}), flush=True)
    return case


def launch(case, print_mode=False):
    env = json.loads((case / "environment.json").read_text())
    for key in ["ORCA_TERMINAL_HANDLE", "ORCA_PANE_KEY", "ORCA_TAB_ID", "ORCA_WORKTREE_ID"]:
        if key in os.environ:
            env[key] = os.environ[key]
    (case / "terminal-identity.json").write_text(json.dumps({key: value for key, value in env.items() if key.startswith("ORCA_")}, indent=2) + "\n")
    command = json.loads((case / "command.json").read_text())
    if print_mode:
        command[1:1] = ["--print", "--mode", "json"]
        env["GJC_SDK_DISABLE"] = "1"
        try:
            result = subprocess.run(
                command,
                cwd=case / "workspace",
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=25,
                check=False,
            )
            stdout, stderr, code, timed_out = result.stdout, result.stderr, result.returncode, False
        except subprocess.TimeoutExpired as error:
            stdout, stderr, code, timed_out = error.stdout or b"", error.stderr or b"", None, True
        (case / "stdout.jsonl").write_bytes(stdout)
        (case / "stderr.log").write_bytes(stderr)
        result = {"case": str(case), "returncode": code, "timed_out": timed_out}
        (case / "print-result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    else:
        os.chdir(case / "workspace")
        os.execve(command[0], command, env)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["serve", "prepare", "launch", "print"])
    parser.add_argument("--runtime", type=Path, default=Path("/tmp/gjc-parent-decisions"))
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--name", default="single")
    parser.add_argument("--scenario", choices=["single", "two", "malicious"], default="single")
    parser.add_argument("--case", type=Path)
    args = parser.parse_args()
    if args.operation == "serve":
        serve(args.runtime, args.port)
    elif args.operation == "prepare":
        prepare(args.runtime, args.name, args.scenario)
    else:
        launch(args.case, args.operation == "print")


if __name__ == "__main__":
    main()
