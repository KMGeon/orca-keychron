#!/usr/bin/env python3
"""Local deterministic OpenAI-compatible provider for native GJC hook experiments.

No third-party dependencies, external calls, secrets, request bodies or tool
arguments in logs. Scenarios are selected with [GJC_CASE:scenario] in user text.
"""
import argparse
import hashlib
import json
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCENARIOS = ["success", "read", "bash", "tool_failure", "retry", "ask", "ask_two", "ask_parallel", "task", "task_ask", "task_mixed", "hang", "slow", "http_error", "stream_error", "child_success", "child_ask", "child_slow"]
SCENARIOS += ["task_wait", "task_pair", "task_nested", "task_fail", "task_wait_ask", "task_wait_mixed", "child_nested", "child_http_error", "transient_error", "bash_slow"]
LOCK = threading.Lock()
TRANSIENT_ATTEMPTS = {}


def extract_text(message):
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return "\n".join(part.get("text", "") for part in content if isinstance(part, dict)) if isinstance(content, list) else ""


def pick_scenario(body):
    for message in reversed(body.get("messages", [])):
        if message.get("role") != "user":
            continue
        matches = re.findall(r"\[GJC_CASE:([a-z_]+)\]", extract_text(message))
        if matches:
            return matches[-1]
    model = body.get("model", "success")
    return model.removeprefix("lab-") if model.startswith("lab-") else "success"


def turn_tool_calls(body):
    messages = body.get("messages", [])
    # Only count calls after the most recent real scenario-bearing user prompt.
    last_prompt = max((i for i, m in enumerate(messages) if m.get("role") == "user" and "[GJC_CASE:" in extract_text(m)), default=-1)
    return [call for m in messages[last_prompt + 1:] if m.get("role") == "assistant" for call in m.get("tool_calls", [])]


def question(qid):
    return {"id": qid, "question": "Local Keychron experiment: select Continue or Stop.", "options": [{"label": "Continue"}, {"label": "Stop"}], "multi": False}


def plan(body, scenario):
    calls = turn_tool_calls(body)
    step = len(calls)
    fixture = str(ROOT / "fixture.txt")
    awaited_tasks = {
        "task_wait": ["child_success"],
        "task_pair": ["child_success", "child_success"],
        "task_nested": ["child_nested"],
        "child_nested": ["child_success"],
        "task_fail": ["child_http_error"],
        "task_wait_ask": ["child_ask"],
        "task_wait_mixed": ["child_ask", "child_slow", "child_success"],
    }
    if scenario in awaited_tasks:
        children = awaited_tasks[scenario]
        if step == 0:
            return [("task", {"agent": ("lab-leaf" if scenario == "child_nested" else "executor"), "tasks": [{"id": f"lab_child_{i}", "description": child, "assignment": f"[GJC_CASE:{child}] Local deterministic hook experiment. Perform only the local mock provider's harmless action.", "inheritContext": "none"} for i, child in enumerate(children)]})]
        if step == 1 and scenario != "child_nested":
            return [("subagent", {"action": "await", "ids": [f"{i}-lab_child_{i}" for i in range(len(children))], "timeout_ms": 10000})]
        return []
    if scenario == "bash_slow" and step == 0:
        return [("bash", {"command": "python3 -c 'import time; print(\"LOCAL_BASH_SLEEP\", flush=True); time.sleep(20)'", "timeout": 25})]
    if scenario in {"read", "bash", "tool_failure", "retry", "ask", "ask_two", "ask_parallel", "child_ask", "task", "task_ask", "task_mixed"}:
        if step == 0:
            if scenario == "read":
                return [("read", {"path": fixture})]
            if scenario == "bash":
                return [("bash", {"command": "printf 'KEYCHRON_HOOK_LAB_OK\\n'", "timeout": 5})]
            if scenario in {"tool_failure", "retry"}:
                return [("read", {"path": str(ROOT / "intentionally-does-not-exist.txt")})]
            if scenario in {"ask", "child_ask"}:
                return [("ask", {"questions": [question("lab_q1")]})]
            if scenario == "ask_two":
                return [("ask", {"questions": [question("lab_q1"), question("lab_q2")]})]
            if scenario == "ask_parallel":
                return [("ask", {"questions": [question("lab_q1")]}), ("ask", {"questions": [question("lab_q2")]})]
            child_scenarios = {"task": ["child_success"], "task_ask": ["child_ask"], "task_mixed": ["child_ask", "child_slow", "child_success"]}[scenario]
            return [("task", {"agent": ("lab-leaf" if scenario == "child_nested" else "executor"), "tasks": [{"id": f"lab_child_{i}", "description": child, "assignment": f"[GJC_CASE:{child}] Local deterministic hook experiment. Perform only the local mock provider's harmless action.", "inheritContext": "none"} for i, child in enumerate(child_scenarios)]})]
        if scenario == "retry" and step == 1:
            return [("read", {"path": fixture})]
    return []


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def record(self, value):
        with LOCK:
            with self.server.log_path.open("a") as output:
                output.write(json.dumps({"time": time.time(), **value}) + "\n")

    def send_json(self, code, value):
        payload = json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"ok": True, "scope": "loopback deterministic provider"})
        elif self.path == "/v1/models":
            self.send_json(200, {"object": "list", "data": [{"id": "lab-" + case, "object": "model", "owned_by": "local-hook-lab"} for case in SCENARIOS]})
        else:
            self.send_json(404, {"error": {"message": "Local experiment route not found"}})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_json(404, {"error": {"message": "Only chat completions supported"}})
            return
        size = int(self.headers.get("Content-Length", 0))
        if size > 8_000_000:
            self.send_json(413, {"error": {"message": "Experiment body limit"}})
            return
        body = json.loads(self.rfile.read(size))
        scenario = pick_scenario(body)
        request_id = uuid.uuid4().hex[:12]
        tools = [tool.get("function", {}).get("name") for tool in body.get("tools", [])]
        steps = len(turn_tool_calls(body))
        self.record({"event": "request", "request_id": request_id, "scenario": scenario, "model": body.get("model"), "message_count": len(body.get("messages", [])), "tool_names": tools, "prior_tool_call_count": steps, "stream": body.get("stream")})
        if scenario in {"http_error", "child_http_error"}:
            self.send_json(400, {"error": {"message": "LOCAL_EXPERIMENT_HTTP_FAILURE", "type": "invalid_request_error", "code": "lab_failure"}})
            self.record({"event": "http_error_sent", "request_id": request_id, "status": 400})
            return
        if scenario == "transient_error":
            # Same prompt receives one transient failure followed by success.
            user_text = "\n".join(extract_text(m) for m in body.get("messages", []) if m.get("role") == "user")
            transient_key = hashlib.sha256(user_text.encode()).hexdigest()
            with LOCK:
                attempt = TRANSIENT_ATTEMPTS.get(transient_key, 0)
                TRANSIENT_ATTEMPTS[transient_key] = attempt + 1
            if attempt < 6:
                self.send_json(503, {"error": {"message": "LOCAL_EXPERIMENT_TRANSIENT_FAILURE", "type": "server_error", "code": "lab_transient"}})
                self.record({"event": "transient_error_sent", "request_id": request_id, "status": 503, "attempt": attempt + 1})
                return
            self.record({"event": "transient_recovered", "request_id": request_id, "attempt": attempt + 1})
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            response_id = "chatcmpl-lab-" + request_id

            def emit(delta, finish=None, usage=None):
                chunk = {"id": response_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": body.get("model", "lab-success"), "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                if usage:
                    chunk["usage"] = usage
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.flush()

            emit({"role": "assistant", "content": ""})
            if scenario == "hang":
                emit({"content": "LOCAL_EXPERIMENT_WAITING "})
                for _ in range(180):
                    time.sleep(1)
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                self.record({"event": "hang_timeout", "request_id": request_id})
            elif scenario in {"slow", "child_slow"}:
                for index in range(12):
                    emit({"content": f"LOCAL_PROGRESS_{index} "})
                    time.sleep(1)
            elif scenario == "stream_error":
                emit({"content": "LOCAL_EXPERIMENT_PARTIAL "})
                emit({}, "content_filter")
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                self.record({"event": "stream_error_sent", "request_id": request_id})
                return

            actions = plan(body, scenario)
            if not actions and scenario.startswith("child_") and "yield" in tools:
                actions = [("yield", {"result": {"data": {"case": scenario, "result": "LOCAL_EXPERIMENT_CHILD_COMPLETE"}}})]
            for index, (name, arguments) in enumerate(actions):
                emit({"tool_calls": [{"index": index, "id": f"call_{request_id}_{index}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]})
            if not actions:
                emit({"content": "LOCAL_EXPERIMENT_COMPLETE " + scenario})
            emit({}, "tool_calls" if actions else "stop", {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.record({"event": "response_sent", "request_id": request_id, "scenario": scenario, "tool_calls": [name for name, _ in actions], "finish_reason": "tool_calls" if actions else "stop"})
        except (BrokenPipeError, ConnectionResetError):
            self.record({"event": "client_disconnected", "request_id": request_id, "scenario": scenario})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--agent-dir", type=Path, default=ROOT / "agent")
    parser.add_argument("--log", type=Path, default=ROOT / "requests.jsonl")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    server.log_path = args.log
    args.agent_dir.mkdir(parents=True, exist_ok=True)
    port = server.server_port
    config = {"providers": {"keychron-lab": {"baseUrl": f"http://127.0.0.1:{port}/v1", "api": "openai-completions", "auth": "none", "models": [{"id": "lab-" + case, "name": "Local " + case, "contextWindow": 128000, "maxTokens": 4096} for case in SCENARIOS]}}, "modelBindings": {"modelRoles": {"default": "keychron-lab/lab-success"}, "agentModelOverrides": {"executor": "keychron-lab/lab-success"}}}
    # JSON is a YAML subset and accepted by the official YAML reader.
    (args.agent_dir / "models.yml").write_text(json.dumps(config, indent=2) + "\n")
    (ROOT / "fixture.txt").write_text("KEYCHRON_HOOK_LAB_FIXTURE\n")
    info = {"pid": __import__("os").getpid(), "url": f"http://127.0.0.1:{port}/v1", "port": port, "agent_dir": str(args.agent_dir), "models_file": str(args.agent_dir / "models.yml"), "log_file": str(args.log)}
    (ROOT / "server-info.json").write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps(info), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
