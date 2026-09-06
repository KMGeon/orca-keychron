import { afterEach, expect, test } from "bun:test";
import { createServer, type Socket } from "node:net";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Publisher, createHook, type HookAPI, type HookContext } from "../src/orca_keychron_gjc/assets/gjc_hook";

const cleanup: (() => void)[] = [];
afterEach(() => { while (cleanup.length) cleanup.pop()!(); });
function fixture(options: Record<string, any> = {}, env: Record<string, string> = {}) {
  const publisher = new Publisher({ socketPath: "/tmp/keychron-hook-test-absent.sock", ...options }, {
    ORCA_TERMINAL_HANDLE: "term_test", ORCA_PANE_KEY: "tab:leaf", ORCA_WORKTREE_ID: "wt", ...env,
  });
  cleanup.push(() => publisher.dispose());
  const handlers = new Map<string, Function>();
  const api: HookAPI = { on: (type, handler) => { handlers.set(type, handler); } };
  publisher.attach(api);
  let id = "root";
  const context: HookContext = { sessionManager: { getSessionId: () => id }, hasUI: true };
  // ExtensionRunner.createContext creates a fresh readonly facade each event.
  const send = (type: string, event: Record<string, any> = {}, ctx = context) => handlers.get(type)?.(event, {
    ...ctx, sessionManager: Object.freeze({ getSessionId: () => ctx.sessionManager?.getSessionId?.() }),
  });
  const child = (id: string): HookContext => ({ sessionManager: { getSessionId: () => id }, hasUI: false });
  const state = (id = "root") => publisher.snapshot()?.sessions.find(s => s.sessionId === id)!;
  send("session_start");
  return { publisher, api, handlers, context, send, child, state, switchTo: (value: string, reason = "new") => { id = value; send("session_switch", { type: "session_switch", reason }); } };
}
const assistant = (stopReason: string) => ({ role: "assistant", stopReason });
const decision = (request_id: string) => ({ status: "needs_user_decision", request_id, question: "SECRET QUESTION", options: ["SECRET A", "SECRET B"], checkpoint: "SECRET CHECKPOINT" });
function yieldResult(f: ReturnType<typeof fixture>, ctx: HookContext, id: string, data: unknown) {
  f.send("tool_execution_start", { toolName: "yield", toolCallId: id }, ctx);
  f.send("tool_execution_end", { toolName: "yield", toolCallId: id, isError: false, result: { details: { status: "success", data } } }, ctx);
}
async function until(predicate: () => boolean, ms = 2000) {
  const deadline = Date.now() + ms;
  while (!predicate() && Date.now() < deadline) await new Promise(r => setTimeout(r, 5));
  expect(predicate()).toBe(true);
}

test("requires actual interactive Orca identity; explicitly headless fixtures allowed", () => {
  expect(fixture({}, { ORCA_PANE_KEY: "" }).publisher.snapshot()).toBeUndefined();
  expect(fixture({}, { ORCA_KEYCHRON_OWNER_PID: String(process.pid + 1) }).publisher.snapshot()).toBeUndefined();
  const f = fixture();
  expect(f.handlers.has("tool_call")).toBe(false);
  expect(f.handlers.has("tool_execution_start")).toBe(true);
  const p = new Publisher({ socketPath: "/tmp/test.sock" }, { ORCA_TERMINAL_HANDLE: "t", ORCA_PANE_KEY: "p", ORCA_WORKTREE_ID: "w" });
  cleanup.push(() => p.dispose());
  let start: Function;
  p.attach({ on: (type, handler) => { if (type === "session_start") start = handler; } });
  start!({}, { hasUI: false, sessionManager: { getSessionId: () => "sdk" } });
  expect(p.snapshot()).toBeUndefined();
});

test("duplicate loaders and repeated or late starts never double count asks", () => {
  const f = fixture();
  f.publisher.attach(f.api);
  f.send("agent_start");
  const event = { toolName: "ask", toolCallId: "a" };
  f.send("tool_execution_start", event);
  f.send("tool_execution_start", event);
  f.send("tool_execution_start", { ...event });
  f.send("tool_execution_start", { ...event, toolCallId: "b" });
  expect(f.state()).toMatchObject({ state: "waiting", pendingAsks: 2 });
  f.send("tool_execution_end", { ...event, isError: false });
  f.send("tool_execution_start", { ...event });
  expect(f.state().pendingAsks).toBe(1);
  f.send("agent_end", { messages: [assistant("stop")] });
  expect(f.state().state).toBe("waiting");
});

test("tool name mismatch cannot clear a pending ask", () => {
  const f = fixture();
  f.send("tool_execution_start", { toolName: "ask", toolCallId: "a" });
  f.send("tool_execution_end", { toolName: "read", toolCallId: "a" });
  expect(f.state().pendingAsks).toBe(1);
  expect(f.publisher.snapshot()?.complete).toBe(false);
});

test("final assistant outcome, retry, late failures, pause and queued work", () => {
  const f = fixture();
  f.send("agent_start");
  f.send("tool_execution_start", { toolName: "bash", toolCallId: "b" });
  f.send("agent_failed");
  f.send("tool_execution_end", { toolName: "bash", toolCallId: "b", isError: true });
  expect(f.state().state).toBe("failed");
  f.send("auto_retry_start");
  expect(f.state().state).toBe("working");
  f.send("agent_end", { stopReason: "completed", messages: [assistant("error"), assistant("stop")] });
  expect(f.state().state).toBe("done");
  f.send("agent_start");
  f.send("agent_end", { stopReason: "completed", messages: [assistant("toolUse")] });
  expect(f.state().state).toBe("unknown");
  f.send("agent_end", { messages: [assistant("aborted")] });
  expect(f.state().state).toBe("cancelled");
  f.send("agent_end", { stopReason: "paused" });
  expect(f.state().state).toBe("paused");
  f.context.hasQueuedMessages = () => true;
  f.send("agent_start");
  f.send("agent_end", { messages: [assistant("stop")] });
  expect(f.state().state).toBe("working");
});

test("cancelled ask followed by completed toolUse is never green", () => {
  const f = fixture();
  f.send("agent_start");
  f.send("tool_execution_start", { toolName: "ask", toolCallId: "a" });
  f.send("agent_end", { stopReason: "completed", messages: [assistant("toolUse")] });
  f.send("tool_execution_end", { toolName: "ask", toolCallId: "a", isError: true });
  expect(f.state()).toMatchObject({ state: "unknown", pendingAsks: 0 });
});

test("child shutdown and parent completion retain decision; only matching real answer clears it", () => {
  const f = fixture(); const child = f.child("child");
  f.send("session_start", {}, child);
  yieldResult(f, child, "y", decision("request"));
  f.send("session_shutdown", {}, child);
  f.send("agent_end", { messages: [assistant("stop")] });
  expect(f.state("child")).toMatchObject({ state: "waiting", pendingDecisions: 1 });
  for (const [index, details] of [{ answers: { request: "yes" } }, { selectedOptions: ["yes"], cancelled: true }, { customInput: "yes", timedOut: true }, { clarificationQuestion: "why", selectedOptions: ["yes"] }, { results: [{ id: "wrong", selectedOptions: ["yes"] }] }].entries()) {
    f.send("tool_execution_start", { toolName: "ask", toolCallId: `a${index}`, args: { questions: [{ id: "request" }] } });
    f.send("tool_execution_end", { toolName: "ask", toolCallId: `a${index}`, isError: false, result: { details } });
    expect(f.state("child").pendingDecisions).toBe(1);
  }
  f.send("tool_execution_start", { toolName: "ask", toolCallId: "actual", args: { questions: [{ id: "request" }] } });
  f.send("tool_execution_end", { toolName: "ask", toolCallId: "actual", isError: false, result: { details: { selectedOptions: ["yes"] } } });
  expect(f.state("child")).toMatchObject({ state: "unknown", pendingDecisions: 0 });
  expect(JSON.stringify(f.publisher.snapshot())).not.toContain("SECRET");
});

test("multi-answer correlation clears only matching decision and collisions stay uncertain", () => {
  const f = fixture(); const a = f.child("a"), b = f.child("b");
  yieldResult(f, a, "y1", decision("one")); yieldResult(f, b, "y2", decision("two"));
  f.send("tool_execution_start", { toolName: "ask", toolCallId: "ask", args: { questions: [{ id: "one" }, { id: "two" }] } });
  f.send("tool_execution_end", { toolName: "ask", toolCallId: "ask", isError: false, result: { details: { results: [{ id: "two", customInput: "answer" }, { id: "one", selectedOptions: [] }] } } });
  expect(f.state("a").pendingDecisions).toBe(1); expect(f.state("b").pendingDecisions).toBe(0);
  yieldResult(f, b, "y3", decision("one"));
  f.send("tool_execution_start", { toolName: "ask", toolCallId: "collision", args: { questions: [{ id: "one" }] } });
  f.send("tool_execution_end", { toolName: "ask", toolCallId: "collision", isError: false, result: { details: { customInput: "answer" } } });
  expect(f.publisher.snapshot()?.complete).toBe(false);
  expect(f.state("a").pendingDecisions + f.state("b").pendingDecisions).toBe(2);
});

test("malformed yield is unknown, child shutdown alone never proves success", () => {
  for (const data of [undefined, null, { ...decision("r"), options: ["same", "same"] }, { ...decision("r"), checkpoint: "" }]) {
    const f = fixture(); const child = f.child("child");
    yieldResult(f, child, "y", data); f.send("session_shutdown", {}, child);
    expect(f.state("child").state).toBe("unknown");
  }
  const f = fixture(); const child = f.child("child");
  f.send("session_start", {}, child); f.send("session_shutdown", {}, child);
  expect(f.state("child").state).toBe("unknown");
  yieldResult(f, child, "y", { summary: "SECRET RESULT" });
  f.send("session_shutdown", {}, child);
  expect(f.state("child").state).toBe("done");
});

test("parent instructions append without replacing prompt and stay root-only", () => {
  const f = fixture({ parentInstructions: "bridge instructions" });
  expect(f.send("before_agent_start", { systemPrompt: ["existing"] })).toEqual({ systemPrompt: ["existing", "bridge instructions"] });
  expect(f.send("before_agent_start", { systemPrompt: ["existing", "bridge instructions"] })).toEqual({ systemPrompt: ["existing", "bridge instructions"] });
  expect(f.send("before_agent_start", { systemPrompt: ["child"] }, f.child("child"))).toBeUndefined();
});

test("session and tool bounds mark incomplete while retaining a valid root", () => {
  const f = fixture();
  for (let i = 0; i < 260; i++) f.send("session_start", {}, f.child(`${i}-` + "😀".repeat(250)));
  expect(f.publisher.snapshot()?.sessions).toHaveLength(256);
  f.switchTo("new-root-at-limit");
  const snapshot = f.publisher.snapshot()!;
  expect(snapshot.complete).toBe(false);
  expect(snapshot.sessions.filter(s => s.role === "root")).toHaveLength(1);
  expect(snapshot.sessions.some(s => s.sessionId === snapshot.root.sessionId)).toBe(true);
  expect(Buffer.byteLength(JSON.stringify(snapshot))).toBeLessThan(512 * 1024);
  const g = fixture();
  for (let i = 0; i < 129; i++) g.send("tool_execution_start", { toolName: "ask", toolCallId: `a${i}` });
  expect(g.state().pendingAsks).toBe(128); expect(g.publisher.snapshot()?.complete).toBe(false);
});

test("normal session switch keeps one root and preserves old unresolved requests", () => {
  const f = fixture();
  f.send("tool_execution_start", { toolName: "ask", toolCallId: "a" }); f.switchTo("new-root");
  expect(f.publisher.snapshot()?.root.sessionId).toBe("new-root");
  expect(f.state("root")).toMatchObject({ role: "child", state: "waiting" });
});

test("fresh readonly facades preserve /new and resume work, completion and shutdown", async () => {
  const f = fixture();
  const frames = [f.publisher.snapshot()];
  for (const [id, reason] of [["new-root", "new"], ["root", "resume"]]) {
    f.switchTo(id, reason);
    expect(f.publisher.snapshot()?.root.sessionId).toBe(id);
    expect(f.publisher.snapshot()?.sessions.filter(s => s.role === "root")).toHaveLength(1);
    f.send("agent_start");
    expect(f.state(id).state).toBe("working");
    frames.push(f.publisher.snapshot());
    f.send("agent_end", { messages: [assistant("stop")] });
    expect(f.state(id).state).toBe("done");
    frames.push(f.publisher.snapshot());
  }
  await f.send("session_shutdown");
  expect(f.publisher.snapshot()?.closed).toBe(true);
  expect(f.state().state).toBe("closed");
  frames.push(f.publisher.snapshot());
  const result = Bun.spawnSync(["python3", "-c", "import sys,json; from orca_keychron_gjc.gjc_protocol import parse_snapshot; frames=json.load(sys.stdin); [parse_snapshot(frame) for frame in frames]; print(len(frames))"], {
    env: { ...process.env, PYTHONPATH: "src" }, stdin: Buffer.from(JSON.stringify(frames)),
  });
  expect(result.exitCode).toBe(0);
  expect(result.stdout.toString().trim()).toBe("6");
});

test("unrelated interactive loader cannot switch, mutate or close the root even with a reused ID", () => {
  const f = fixture();
  const handlers = new Map<string, Function>();
  f.publisher.attach({ on: (type, fn) => handlers.set(type, fn) });
  for (const id of ["unrelated", "root"]) {
    for (const type of ["session_start", "session_switch", "agent_start", "session_shutdown"]) {
      handlers.get(type)!({ type, reason: "resume" }, { hasUI: true, sessionManager: Object.freeze({ getSessionId: () => id }) });
    }
  }
  expect(f.publisher.snapshot()?.root.sessionId).toBe("root");
  expect(f.publisher.snapshot()?.closed).toBe(false);
  expect(f.publisher.snapshot()?.sessions).toHaveLength(1);
  expect(f.state().state).toBe("idle");
});

test("headless child reopening current root cannot switch or shut it down", async () => {
  const f = fixture();
  f.switchTo("resumed", "resume");
  for (const type of ["session_start", "session_switch", "agent_start", "session_shutdown"]) {
    f.send(type, { reason: "resume" }, f.child("resumed"));
  }
  expect(f.publisher.snapshot()).toMatchObject({ closed: false, complete: false, root: { sessionId: "resumed" } });
  expect(f.state("resumed").state).toBe("idle");
  f.send("agent_start");
  expect(f.state("resumed").state).toBe("working");
  f.send("agent_end", { messages: [assistant("stop")] });
  await f.send("session_shutdown");
  expect(f.publisher.snapshot()?.closed).toBe(true);
});

test("duplicate root loaders remain recognized when event delivery order changes after switch", async () => {
  const f = fixture();
  const second = new Map<string, Function>();
  f.publisher.attach({ on: (type, fn) => second.set(type, fn) });
  const event = { type: "agent_start" };
  f.send("agent_start", event);
  second.get("agent_start")!(event, { hasUI: true, sessionManager: { getSessionId: () => "root" } });
  const context = () => ({ hasUI: true, sessionManager: Object.freeze({ getSessionId: () => "new" }) });
  second.get("session_switch")!({ type: "session_switch", reason: "new" }, context());
  second.get("agent_start")!({}, context());
  second.get("agent_end")!({ messages: [assistant("stop")] }, context());
  expect(f.state("new").state).toBe("done");
  await second.get("session_shutdown")!({}, context());
  expect(f.publisher.snapshot()?.closed).toBe(true);
});

test("socket reconnect replaces lost history with latest complete snapshot and flushes closure", async () => {
  const dir = mkdtempSync(join(tmpdir(), "gjc-hook-")); const path = join(dir, "s");
  cleanup.push(() => rmSync(dir, { recursive: true, force: true }));
  const frames: any[] = []; const clients = new Set<Socket>();
  const server = createServer(socket => { clients.add(socket); let buffer = ""; socket.on("data", data => { buffer += data; let end: number; while ((end = buffer.indexOf("\n")) >= 0) { frames.push(JSON.parse(buffer.slice(0, end))); buffer = buffer.slice(end + 1); } }); socket.on("close", () => clients.delete(socket)); });
  cleanup.push(() => { for (const client of clients) client.destroy(); server.close(); });
  const f = fixture({ socketPath: path, heartbeatMs: 30 });
  f.send("agent_start");
  await new Promise<void>(r => server.listen(path, r));
  await until(() => frames.length > 0);
  const first = frames.at(-1);
  expect(first.sessions[0].state).toBe("working");
  for (const client of clients) client.destroy();
  f.send("tool_execution_start", { toolName: "ask", toolCallId: "pending" }, f.child("child"));
  f.send("agent_end", { messages: [assistant("stop")] });
  await until(() => frames.some(frame => frame.sequence > first.sequence && frame.sessions.some((s: any) => s.sessionId === "child" && s.pendingAsks === 1)));
  const last = frames.at(-1);
  expect(last.complete).toBe(true); expect(last.sessions).toHaveLength(2);
  const count = frames.length; await until(() => frames.length > count);
  await f.send("session_shutdown");
  await until(() => frames.some(frame => frame.closed === true));
  expect(frames.at(-1).sessions.find((s: any) => s.sessionId === "child").pendingAsks).toBe(1);
});

test("backpressure coalesces to one latest frame and bounded shutdown completes without receiver", async () => {
  const f = fixture(); const p = f.publisher as any; const writes: string[] = [];
  p.socket = { write: (line: string) => { writes.push(line); return false; }, destroy: () => {} };
  p.connected = true;
  p.publish();
  for (let i = 0; i < 1000; i++) { f.send("agent_start"); p.publish(); }
  f.send("tool_execution_start", { toolName: "ask", toolCallId: "last" }); p.publish();
  expect(writes).toHaveLength(1);
  expect(JSON.parse(p.latest).sessions[0].pendingAsks).toBe(1);
  p.writing = false; p.flush();
  expect(writes).toHaveLength(2); expect(p.latest).toBeUndefined();
  p.socket = undefined; p.connected = false;
  const started = Date.now(); await f.send("session_shutdown");
  expect(Date.now() - started).toBeLessThan(1000);
});

test("separate installed loaders share a publisher and duplicate events", () => {
  const singleton = Symbol.for("orca-keychron.gjc-hook.publisher.v1");
  const globals = globalThis as any;
  const previous = globals[singleton];
  const saved = { ...process.env };
  cleanup.push(() => { globals[singleton]?.dispose(); if (previous) globals[singleton] = previous; else delete globals[singleton]; for (const key of ["ORCA_TERMINAL_HANDLE", "ORCA_PANE_KEY", "ORCA_WORKTREE_ID", "ORCA_KEYCHRON_OWNER_PID"]) { if (saved[key] === undefined) delete process.env[key]; else process.env[key] = saved[key]; } });
  delete globals[singleton]; delete process.env.ORCA_KEYCHRON_OWNER_PID;
  Object.assign(process.env, { ORCA_TERMINAL_HANDLE: "t", ORCA_PANE_KEY: "p", ORCA_WORKTREE_ID: "w" });
  const handlers: Map<string, Function>[] = [new Map(), new Map()];
  const publishers = handlers.map(map => createHook({ on: (type, fn) => map.set(type, fn) }, { socketPath: "/tmp/absent-gjc-test.sock", allowHeadless: true }));
  expect(publishers[0]).toBe(publishers[1]);
  const context = { hasUI: false, sessionManager: { getSessionId: () => "headless" } };
  const start = {};
  for (const map of handlers) map.get("session_start")!(start, context);
  const ask = { toolName: "ask", toolCallId: "a" };
  for (const map of handlers) map.get("tool_execution_start")!(ask, context);
  expect(publishers[0]?.snapshot()?.sessions).toHaveLength(1);
  expect(publishers[0]?.snapshot()?.sessions[0].pendingAsks).toBe(1);
  expect(String(process.env.ORCA_KEYCHRON_OWNER_PID)).toBe(String(process.pid));
});

test("emitted snapshots satisfy the actual Python receiver schema, including closed pending child", async () => {
  const f = fixture();
  yieldResult(f, f.child("child"), "yield", decision("r"));
  const frames = [f.publisher.snapshot()];
  await f.send("session_shutdown"); frames.push(f.publisher.snapshot());
  const result = Bun.spawnSync(["python3", "-c", "import sys,json; from orca_keychron_gjc.gjc_protocol import parse_snapshot; frames=json.load(sys.stdin); [parse_snapshot(frame) for frame in frames]; print(len(frames))"], {
    env: { ...process.env, PYTHONPATH: "src" }, stdin: Buffer.from(JSON.stringify(frames)),
  });
  expect(result.exitCode).toBe(0);
  expect(result.stdout.toString().trim()).toBe("2");
});

test("exhausted retry remains failed when an outstanding tool ends late", () => {
  const f = fixture();
  f.send("agent_start");
  f.send("tool_execution_start", { toolName: "read", toolCallId: "late" });
  f.send("auto_retry_start"); f.send("auto_retry_end", { success: false });
  f.send("tool_execution_end", { toolName: "read", toolCallId: "late", isError: false });
  expect(f.state().state).toBe("failed");
});

test("resolved-call memory is bounded and exhaustion explicitly downgrades coverage", () => {
  const f = fixture();
  for (let i = 0; i < 2050; i++) f.send("tool_execution_end", { toolName: "read", toolCallId: `r${i}`, isError: false });
  expect((f.publisher as any).sessions.get("root").resolved.size).toBe(2048);
  expect(f.publisher.snapshot()?.complete).toBe(false);
  f.send("tool_execution_start", { toolName: "ask", toolCallId: "bad\u0000id" });
  expect(f.state().pendingAsks).toBe(0);
});
