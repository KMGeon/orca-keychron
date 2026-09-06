import { afterEach, expect, test } from "bun:test";
import { createServer, type Socket } from "node:net";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Publisher, type HookAPI, type HookContext } from "../src/orca_keychron_gjc/assets/gjc_hook";

const owned: Publisher[] = [];
afterEach(() => { for (const publisher of owned.splice(0)) publisher.dispose(); });
const secret = "PRIVACY_SENTINEL_670ad";
// GJC f50b17a: hooks/loader.ts createHookExtensionFactory passes the original
// payload through; extensions/runner.ts createContext allocates fresh facades.
// Separate native root/child factories have separate API registrations.
function fixture(socketPath = "/tmp/gjc-fault-670ad-absent.sock") {
  const publisher = new Publisher({ socketPath }, {
    ORCA_TERMINAL_HANDLE: "term_fixture", ORCA_PANE_KEY: "tab:leaf", ORCA_WORKTREE_ID: "fixture",
  });
  owned.push(publisher);
  function loader(initial: string, hasUI = false) {
    let id = initial;
    const handlers = new Map<string, (event: Record<string, unknown>, context: HookContext) => unknown>();
    const api: HookAPI = { on: (type, fn) => { handlers.set(type, fn); } };
    publisher.attach(api);
    const deliver = (type: string, payload: Record<string, unknown>) => handlers.get(type)!(payload, {
      hasUI, sessionManager: Object.freeze({ getSessionId: () => id }), hasQueuedMessages: () => false,
    });
    const send = (type: string, payload: Record<string, unknown> = {}) => deliver(type, { type, ...payload });
    return { send, deliver, switch: (next: string, reason = "resume") => { id = next; send("session_switch", { reason }); } };
  }
  const root = loader("root", true); root.send("session_start");
  const state = (id = "root") => publisher.snapshot()!.sessions.find(row => row.sessionId === id)!;
  return { publisher, loader, root, state };
}
type Loader = ReturnType<ReturnType<typeof fixture>["loader"]>;
const decision = (request_id: string) => ({ status: "needs_user_decision", request_id, question: secret, checkpoint: secret, options: [secret + "A", secret + "B"] });
function yieldDecision(loader: Loader, call: string, request: string) {
  loader.send("tool_execution_start", { toolName: "yield", toolCallId: call, args: { result: { data: decision(request) } } });
  loader.send("tool_execution_end", { toolName: "yield", toolCallId: call, isError: false, result: { content: [{ type: "text", text: secret }], details: { status: "success", data: decision(request), error: undefined } } });
}
function ask(loader: Loader, call: string, ...ids: string[]) {
  loader.send("tool_execution_start", { toolName: "ask", toolCallId: call, args: { questions: ids.map(id => ({ id, question: secret, options: [{ label: "yes" }, { label: "no" }] })) } });
}
function answer(loader: Loader, call: string, details: unknown) {
  loader.send("tool_execution_end", { toolName: "ask", toolCallId: call, isError: false, result: { details } });
}

test("H-ID: capacity /new tracks the actual root and its explicit shutdown", async () => {
  const f = fixture();
  const deep = f.loader("deep"); yieldDecision(deep, "y", "pending");
  for (let i = 0; i < 254; i++) f.loader(`c${i}`).send("session_start");
  const identity = f.publisher.snapshot()!;
  f.root.switch("new-root", "new");
  expect(f.publisher.snapshot()!.root.sessionId).toBe("new-root");
  expect(f.publisher.snapshot()!.sessions).toHaveLength(256);
  expect(f.publisher.snapshot()!.complete).toBe(false);
  expect(f.state("deep").pendingDecisions).toBe(1);
  expect(f.publisher.snapshot()!.launchId).toBe(identity.launchId);
  await f.root.send("session_shutdown");
  expect(f.publisher.snapshot()!.closed).toBe(true);
});

test("H-CORR: an ask predating a decision cannot resolve that later decision", () => {
  const f = fixture(); const child = f.loader("child");
  ask(f.root, "earlier-ask", "request");
  yieldDecision(child, "later-yield", "request");
  answer(f.root, "earlier-ask", { customInput: "yes" });
  expect(f.state("child").pendingDecisions).toBe(1);
});

for (const pending of ["ask", "decision"] as const) {
  test(`H-ID: capacity /new preserves sole ${pending} before nonpending active sessions`, () => {
    const f = fixture();
    f.root.send("agent_start");
    const child = f.loader("only-human-request");
    child.send("agent_start");
    if (pending === "ask") ask(child, "ask", "request");
    else yieldDecision(child, "yield", "request");
    for (let i = 0; i < 254; i++) f.loader(`active-${i}`).send("agent_start");
    f.root.switch("new-root", "new");
    const snapshot = f.publisher.snapshot()!;
    expect(snapshot.root.sessionId).toBe("new-root");
    expect(snapshot.complete).toBe(false);
    expect(snapshot.sessions).toHaveLength(256);
    expect(snapshot.sessions.reduce((sum, row) => sum + row.pendingAsks + row.pendingDecisions, 0)).toBe(1);
    expect(f.state("only-human-request").state).toBe("waiting");
  });
}

test("H-CORR: concurrent old answers cannot resolve a reused request ID", () => {
  const f = fixture(); const child = f.loader("child");
  yieldDecision(child, "y1", "r");
  ask(f.root, "a1", "r"); ask(f.root, "a2", "r");
  answer(f.root, "a1", { customInput: "yes" });
  expect(f.state("child").pendingDecisions).toBe(0);
  child.send("agent_start"); yieldDecision(child, "y2", "r");
  answer(f.root, "a2", { customInput: "stale" });
  expect(f.state("child").pendingDecisions).toBe(1);
  ask(f.root, "fresh", "r"); answer(f.root, "fresh", { customInput: "current" });
  expect(f.state("child").pendingDecisions).toBe(0);
});

test("H-PENDING: root completion and nested terminal events retain every deep request", () => {
  const f = fixture();
  for (const id of ["child", "grandchild", "great-grandchild"]) {
    const child = f.loader(id); child.send("session_start"); yieldDecision(child, "y", id);
    child.send("agent_end", { messages: [{ role: "assistant", stopReason: "stop" }] });
    child.send("session_shutdown");
  }
  f.root.send("agent_end", { messages: [{ role: "assistant", stopReason: "stop" }] });
  f.root.switch("new", "new"); f.root.switch("root");
  expect(f.publisher.snapshot()!.sessions.filter(row => row.state === "waiting")).toHaveLength(3);
  ask(f.root, "multi", "child", "grandchild", "great-grandchild");
  answer(f.root, "multi", { results: [{ id: "child", customInput: "yes" }, { id: "grandchild", selectedOptions: [], cancelled: true }, { id: "great-grandchild", selectedOptions: ["yes"], clarificationQuestion: "why" }] });
  expect(f.state("child").pendingDecisions).toBe(0);
  expect(f.state("grandchild").pendingDecisions).toBe(1);
  expect(f.state("great-grandchild").pendingDecisions).toBe(1);
  expect(JSON.stringify(f.publisher.snapshot())).not.toContain(secret);
});

test("H-PRIORITY: pending ask remains waiting over failure, cancellation and retry", () => {
  const f = fixture(); ask(f.root, "pending", "r");
  for (const [type, payload] of [["agent_failed", { error: secret }], ["agent_end", { stopReason: "aborted" }], ["auto_retry_start", { errorMessage: secret }]] as const) {
    f.root.send(type, payload);
    expect(f.state()).toMatchObject({ state: "waiting", pendingAsks: 1 });
  }
  f.root.send("auto_retry_end", { success: false, attempt: 3, finalError: secret });
  answer(f.root, "pending", { cancelled: true });
  expect(f.state().state).toBe("failed");
  expect(JSON.stringify(f.publisher.snapshot())).not.toContain(secret);
});

test.each([null, {}, { status: "success" }, { status: "success", data: null }, { status: "forged", data: decision("r") }, { status: "success", data: decision("r"), error: secret }, { status: "success", data: { ...decision("r"), options: ["same", "same"] } }])("H-YIELD: malformed yield receipt stays unknown %#", details => {
  const f = fixture(); const child = f.loader("child");
  child.send("tool_execution_start", { toolName: "yield", toolCallId: "y" });
  child.send("tool_execution_end", { toolName: "yield", toolCallId: "y", isError: false, result: { details } });
  child.send("session_shutdown");
  expect(f.state("child")).toMatchObject({ state: "unknown", pendingDecisions: 0 });
});

test("H-BOUNDS: independent session tool IDs deduplicate, overflow remains incomplete", () => {
  const f = fixture(); const child = f.loader("child");
  ask(f.root, "same", "r"); ask(child, "same", "r");
  answer(f.root, "same", { customInput: "yes" });
  ask(f.root, "same", "r");
  expect(f.state().pendingAsks).toBe(0); expect(f.state("child").pendingAsks).toBe(1);
  for (let i = 0; i < 128; i++) ask(child, `call${i}`, "r");
  expect(f.state("child").pendingAsks).toBe(128);
  expect(f.publisher.snapshot()!.complete).toBe(false);
  child.send("agent_end", { messages: [{ role: "assistant", stopReason: "stop" }] });
  expect(f.state("child").state).toBe("waiting");
});

test("H-LOADER: original payloads establish duplicate root provenance in both delivery orders", () => {
  const f = fixture(); const project = f.loader("root", true);
  const original = { type: "agent_start" };
  f.root.deliver("agent_start", original); project.deliver("agent_start", original);
  const askEvent = { type: "tool_execution_start", toolCallId: "shared", toolName: "ask" };
  project.deliver("tool_execution_start", askEvent); f.root.deliver("tool_execution_start", askEvent);
  expect(f.state().pendingAsks).toBe(1);
  project.switch("new", "new");
  project.send("agent_end", { messages: [{ role: "assistant", stopReason: "stop" }] });
  expect(f.state("new").state).toBe("done");
  expect(f.state("root").pendingAsks).toBe(1);
  expect(f.publisher.snapshot()!.complete).toBe(true);
});

test("H-ID: child reopening current root never takes authority even after resume", () => {
  const f = fixture(); f.root.switch("resumed"); const reused = f.loader("resumed");
  reused.send("session_start"); reused.send("agent_failed", { error: secret }); reused.send("session_shutdown");
  expect(f.publisher.snapshot()).toMatchObject({ complete: false, closed: false, root: { sessionId: "resumed" } });
  expect(f.state("resumed").state).toBe("idle");
});

test("H-BOUNDS: exhausted receipt history never claims complete recovery", () => {
  const f = fixture();
  for (let i = 0; i < 2049; i++) answer(f.root, `a${i}`, { customInput: secret });
  expect(f.publisher.snapshot()!.complete).toBe(false);
  f.root.send("agent_start"); f.root.send("agent_end", { messages: [{ role: "assistant", stopReason: "stop" }] });
  expect(f.publisher.snapshot()!.complete).toBe(false);
  expect(JSON.stringify(f.publisher.snapshot())).not.toContain(secret);
});

test("H-TRANSPORT: event-synchronized Unix reconnect sends latest full state and closed flush", async () => {
  const dir = mkdtempSync(join(tmpdir(), "gjc-fault-")); const path = join(dir, "s");
  const clients = new Set<Socket>();
  const frames: ReturnType<Publisher["snapshot"]>[] = [];
  let notify: (() => void) | undefined;
  const server = createServer(socket => {
    clients.add(socket); socket.on("close", () => clients.delete(socket));
    let buffer = "";
    socket.on("data", data => {
      buffer += data;
      let end: number;
      while ((end = buffer.indexOf("\n")) !== -1) { frames.push(JSON.parse(buffer.slice(0, end))); buffer = buffer.slice(end + 1); }
      notify?.();
    });
  });
  async function frameWhere(predicate: (frame: NonNullable<ReturnType<Publisher["snapshot"]>>) => boolean) {
    if (frames.some(frame => frame && predicate(frame))) return;
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => { notify = undefined; reject(new Error("frame deadline exceeded")); }, 3000);
      notify = () => { if (frames.some(frame => frame && predicate(frame))) { clearTimeout(timer); notify = undefined; resolve(); } };
      notify();
    });
  }
  let f: ReturnType<typeof fixture> | undefined;
  try {
    await new Promise<void>((resolve, reject) => { server.once("error", reject); server.listen(path, resolve); });
    f = fixture(path); f.root.send("agent_start");
    await frameWhere(frame => frame.sessions[0].state === "working");
    const first = frames[0]!;
    for (const client of clients) client.destroy();
    const child = f.loader("grandchild"); yieldDecision(child, "y", "r");
    f.root.send("agent_end", { messages: [{ role: "assistant", stopReason: "stop" }] });
    await frameWhere(frame => frame.sequence > first.sequence && frame.sessions.some(row => row.pendingDecisions === 1));
    await f.root.send("session_shutdown");
    await frameWhere(frame => frame.closed);
    const last = frames[frames.length - 1]!;
    expect(last).toMatchObject({ closed: true, complete: true, launchId: first.launchId, producerId: first.producerId });
    expect(last.sessions.find(row => row.sessionId === "grandchild")).toMatchObject({ state: "waiting", pendingDecisions: 1 });
    expect(JSON.stringify(frames)).not.toContain(secret);
  } finally {
    f?.publisher.dispose();
    for (const client of clients) client.destroy();
    await new Promise<void>(resolve => server.close(() => resolve()));
    rmSync(dir, { recursive: true, force: true });
  }
});

async function runOwned(code: string, env: Record<string, string> = {}) {
  const child = Bun.spawn([process.execPath, "--eval", code], { env: { ...process.env, ...env }, stdout: "pipe", stderr: "pipe" });
  let deadline: ReturnType<typeof setTimeout>;
  try {
    const exit = await Promise.race([child.exited, new Promise<never>((_, reject) => { deadline = setTimeout(() => { child.kill(); reject(new Error("owned Bun process failed to exit within 5s")); }, 5000); })]);
    const stdout = await new Response(child.stdout).text(); const stderr = await new Response(child.stderr).text();
    expect(stderr).toBe(""); expect(exit).toBe(0);
    return stdout;
  } finally { clearTimeout(deadline!); if (child.exitCode === null) { child.kill(); await child.exited; } }
}
const moduleURL = new URL("../src/orca_keychron_gjc/assets/gjc_hook.ts", import.meta.url).href;
const nativeProcess = `
import { createHook } from ${JSON.stringify(moduleURL)};
const handlers = new Map();
const p = createHook({ on: (type, fn) => handlers.set(type, fn) });
const ctx = { hasUI: true, sessionManager: { getSessionId: () => 'root' } };
handlers.get('session_start')?.({type:'session_start'}, ctx);
`;
const processEnv = { ORCA_KEYCHRON_SOCKET: "/tmp/gjc-process-670ad-absent.sock", ORCA_TERMINAL_HANDLE: "term_fixture", ORCA_PANE_KEY: "tab:leaf", ORCA_WORKTREE_ID: "fixture", ORCA_KEYCHRON_OWNER_PID: "" };

test("H-LIVENESS: real Bun process exits with absent receiver without disposal", async () => {
  const stdout = await runOwned(nativeProcess + `await Promise.resolve(); console.log(Boolean(p.snapshot()));`, processEnv);
  expect(stdout.trim()).toBe("true");
});

test("H-LINEAGE: real nested process inherits owner marker and cannot claim a root", async () => {
  const nested = nativeProcess + `console.log(JSON.stringify({observed:Boolean(p.snapshot()), owner:process.env.ORCA_KEYCHRON_OWNER_PID, pid:process.pid}));`;
  const stdout = await runOwned(nativeProcess + `
const nested = Bun.spawnSync([process.execPath, '--eval', ${JSON.stringify(nested)}], {env:process.env});
if (nested.exitCode !== 0) throw new Error(nested.stderr.toString());
console.log(JSON.stringify({root:Boolean(p.snapshot()), parent:process.pid, child:JSON.parse(nested.stdout.toString())}));
`, processEnv);
  const value = JSON.parse(stdout);
  expect(value.root).toBe(true); expect(value.child.observed).toBe(false);
  expect(value.child.owner).toBe(String(value.parent)); expect(value.child.pid).not.toBe(value.parent);
});

test("H-BACKPRESSURE: real paused receiver bounds buffered frames and shutdown exits", async () => {
  const dir = mkdtempSync(join(tmpdir(), "gjc-stall-")); const path = join(dir, "s");
  const clients = new Set<Socket>();
  const server = createServer(socket => { clients.add(socket); socket.pause(); });
  try {
    await new Promise<void>((resolve, reject) => { server.once("error", reject); server.listen(path, resolve); });
    const stdout = await runOwned(nativeProcess + `
await Promise.resolve();
p.socket.ref();
await new Promise(resolve => p.socket.once('connect', resolve));
p.socket.unref();
for (let i=0; i<255; i++) handlers.get('session_start')({type:'session_start'}, {hasUI:false, sessionManager:{getSessionId:()=> 'child'+i}});
for (let i=0; i<2000; i++) p.publish();
handlers.get('tool_execution_start')({toolName:'ask',toolCallId:'last'},ctx); p.publish();
const bounded={writing:p.writing, buffered:p.socket.writableLength, latest:Buffer.byteLength(p.latest || ''), pending:JSON.parse(p.latest).sessions[0].pendingAsks};
await handlers.get('session_shutdown')({type:'session_shutdown'},ctx);
console.log(JSON.stringify({...bounded,closed:p.snapshot().closed}));
`, { ...processEnv, ORCA_KEYCHRON_SOCKET: path });
    const value = JSON.parse(stdout);
    expect(value).toMatchObject({ writing: true, pending: 1, closed: true });
    expect(value.buffered).toBeLessThan(512 * 1024);
    expect(value.latest).toBeLessThan(512 * 1024);
  } finally {
    for (const client of clients) client.destroy();
    await new Promise<void>(resolve => server.close(() => resolve()));
    rmSync(dir, { recursive: true, force: true });
  }
});

test("H-PENDING: reopening a child ID and late terminal events retain unresolved decision", () => {
  const f = fixture(); const original = f.loader("child");
  yieldDecision(original, "y", "r");
  const reopened = f.loader("child"); reopened.send("session_start"); reopened.send("agent_start");
  original.send("agent_end", { messages: [{ role: "assistant", stopReason: "stop" }] });
  original.send("session_shutdown");
  expect(f.state("child")).toMatchObject({ state: "waiting", pendingDecisions: 1 });
  ask(f.root, "fresh", "r"); answer(f.root, "fresh", { customInput: "current" });
  expect(f.state("child").pendingDecisions).toBe(0);
});
