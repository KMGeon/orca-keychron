/**
 * Orca Keychron observer for GJC 0.16.4 native hooks.
 * Named native loaders use the verified runtime tool_execution_* events because
 * native pre/<name>.ts filters tool_call to a tool with that exact name.
 * Only same-process native children belong to this publisher. No content leaves
 * this process: the protocol contains identities, states, and pending counts.
 */
import { randomUUID } from "node:crypto";
import { createConnection, type Socket } from "node:net";
import { isAbsolute } from "node:path";

type RecordValue = Record<string, unknown>;
type State = "idle" | "working" | "waiting" | "done" | "failed" | "paused" | "cancelled" | "unknown" | "closed";
export interface HookContext {
  sessionManager?: { getSessionId?(): string };
  hasUI?: boolean;
  hasQueuedMessages?(): boolean;
}
export interface HookAPI {
  on(event: string, handler: (event: RecordValue, context: HookContext) => unknown): void;
}
export interface HookOptions {
  socketPath?: string;
  allowHeadless?: boolean;
  heartbeatMs?: number;
  parentInstructions?: string;
}
interface Tool {
  name: string;
  questionIds: string[];
  decisionTokens: Map<string, symbol>;
}
interface Session {
  sessionId: string;
  state: State;
  active: boolean;
  maintenance: boolean;
  outcome?: "stop" | "toolUse" | "error" | "aborted" | "other";
  queued: boolean;
  tools: Map<string, Tool>;
  resolved: Set<string>;
  decisions: Map<string, symbol>;
  yielded?: "done" | "waiting" | "failed" | "unknown";
}
export interface Snapshot {
  version: 1;
  type: "snapshot";
  producerId: string;
  sequence: number;
  launchId: string;
  pid: number;
  startedAt: number;
  complete: boolean;
  closed: boolean;
  root: { sessionId: string; terminalHandle: string; paneKey: string; worktreeId: string };
  sessions: { sessionId: string; role: "root" | "child"; state: State; pendingAsks: number; pendingDecisions: number }[];
}

const EVENTS = ["session_start", "session_switch", "session_shutdown", "before_agent_start", "agent_start", "agent_end", "agent_failed", "turn_start", "message_end", "auto_retry_start", "auto_retry_end", "auto_compaction_start", "auto_compaction_end", "tool_execution_start", "tool_execution_end"];
const MAX_SESSIONS = 256;
const MAX_TOOLS = 128;
const MAX_RESOLVED = 2048;
const MAX_BYTES = 512 * 1024;
const OWNER_ENV = "ORCA_KEYCHRON_OWNER_PID";
const SINGLETON = Symbol.for("orca-keychron.gjc-hook.publisher.v1");

function record(value: unknown): RecordValue | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : undefined;
}
function identifier(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 && value.length <= 512 && !/[\x00-\x1f\x7f]/.test(value) ? value : undefined;
}
function text(value: unknown, max: number): value is string {
  return typeof value === "string" && value.trim().length > 0 && value.length <= max;
}
function decisionId(data: RecordValue): string | undefined {
  if (data.status !== "needs_user_decision" || !identifier(data.request_id) || !text(data.question, 10000) || !text(data.checkpoint, 16000)) return;
  if (!Array.isArray(data.options) || data.options.length < 2 || data.options.length > 16 || !data.options.every(option => text(option, 2000))) return;
  if (new Set(data.options).size !== data.options.length) return;
  return data.request_id as string;
}
function hasAnswer(value: RecordValue): boolean {
  // Clarification is another question, not an answer to the original decision.
  if (value.clarificationQuestion !== undefined || value.cancelled === true || value.timedOut === true) return false;
  return text(value.customInput, 16000) || (Array.isArray(value.selectedOptions) && value.selectedOptions.some(option => text(option, 2000)));
}
function newSession(sessionId: string): Session {
  return { sessionId, state: "idle", active: false, maintenance: false, queued: false, tools: new Map(), resolved: new Set(), decisions: new Map() };
}

/** Testable process-local state machine. Production loaders use createHook below. */
export class Publisher {
  readonly producerId = randomUUID();
  readonly launchId = randomUUID();
  readonly startedAt = Date.now();
  private readonly sessions = new Map<string, Session>();
  private readonly seen = new WeakSet<object>();
  private readonly attached = new WeakSet<object>();
  private readonly rootApis = new WeakSet<object>();
  private readonly rootEvents = new WeakSet<object>();
  private rootId?: string;
  private rootHasUI = false;
  private sequence = 0;
  private complete = true;
  private closed = false;
  private stopped = false;
  private pendingPublish = false;
  private socket?: Socket;
  private connected = false;
  private writing = false;
  private latest?: string;
  private retry?: ReturnType<typeof setTimeout>;
  private heartbeat?: ReturnType<typeof setInterval>;
  private backoff = 100;
  private closing?: Promise<void>;
  private readonly endpoint?: string;
  private readonly identity?: { terminalHandle: string; paneKey: string; worktreeId: string };
  private readonly enabled: boolean;

  constructor(private readonly options: HookOptions = {}, env: Record<string, string | undefined> = process.env) {
    const socketPath = options.socketPath ?? env.ORCA_KEYCHRON_SOCKET;
    this.endpoint = socketPath && isAbsolute(socketPath) && Buffer.byteLength(socketPath) <= 103 && !socketPath.includes("\0") ? socketPath : undefined;
    const terminalHandle = identifier(env.ORCA_TERMINAL_HANDLE);
    const paneKey = identifier(env.ORCA_PANE_KEY);
    const worktreeId = identifier(env.ORCA_WORKTREE_ID);
    if (terminalHandle && paneKey && worktreeId) this.identity = { terminalHandle, paneKey, worktreeId };
    // A nested CLI inherits the original process marker but must not seize its
    // pane. SDK-only hosts without an interactive session never register a root.
    this.enabled = Boolean(this.endpoint && this.identity && (!env[OWNER_ENV] || env[OWNER_ENV] === String(process.pid)));
    this.options = { ...options, allowHeadless: options.allowHeadless ?? env.ORCA_KEYCHRON_ALLOW_HEADLESS === "1" };
  }

  attach(api: HookAPI): void {
    if (!this.enabled || this.attached.has(api)) return;
    this.attached.add(api);
    for (const type of EVENTS) {
      api.on(type, (event, context) => {
        try {
          if (!record(event) || !context || this.stopped) return;
          // Directory user/project hooks receive the same original event.
          if (this.seen.has(event)) {
            if (this.rootEvents.has(event)) this.rootApis.add(api);
            return;
          }
          this.seen.add(event);
          const response = this.observe(type, event, context, api);
          if (type === "session_shutdown" && this.closed) return this.shutdown();
          return response;
        } catch {
          this.complete = false;
          this.schedule();
          // A recorder failure cannot block an approval, change tool output, or
          // prevent a GJC command from completing.
          return undefined;
        }
      });
    }
  }

  private observe(type: string, event: RecordValue, context: HookContext, api: HookAPI): unknown {
    const sessionId = identifier(context.sessionManager?.getSessionId?.());
    if (!sessionId) { if (this.rootId) { this.complete = false; this.schedule(); } return; }
    if (!this.rootId) {
      if (type !== "session_start" || (!context.hasUI && !this.options.allowHeadless)) return;
      this.rootId = sessionId;
      this.rootApis.add(api);
      this.rootHasUI = context.hasUI === true;
      this.sessions.set(sessionId, newSession(sessionId));
      const interval = Number.isFinite(this.options.heartbeatMs) ? Math.max(20, Math.min(this.options.heartbeatMs!, 2000)) : 2000;
      this.heartbeat = setInterval(() => this.publish(), interval);
      this.heartbeat.unref();
    }
    // Native loader APIs survive /new and resume; createContext makes a fresh
    // readonly session-manager facade on every event. Duplicate loaders join
    // this root only when they receive the same original root event above.
    const isRoot = this.rootApis.has(api) && (context.hasUI === true) === this.rootHasUI;
    if (context.hasUI && !isRoot) return;
    if (!isRoot && sessionId === this.rootId) {
      // A headless child may reopen the root's session file. Its shutdown and
      // tool events must not mutate/close the interactive root's record.
      this.complete = false;
      this.schedule();
      return;
    }
    if (isRoot) this.rootEvents.add(event);
    let session = this.sessions.get(sessionId);
    if (!session) {
      if (this.sessions.size >= MAX_SESSIONS) {
        this.complete = false;
        if (type !== "session_switch" || !isRoot) { this.schedule(); return; }
        // The current root must remain observable, especially its shutdown.
        // Prefer inactive records, then other work without human requests.
        // Only lose a pending request when every retained record has one;
        // coverage stays incomplete whenever retaining a new root needs eviction.
        const candidates = [...this.sessions.values()];
        const evicted = candidates.find(row => !row.active && !row.tools.size && !row.decisions.size && !row.maintenance && !row.queued)
          ?? candidates.find(row => !row.decisions.size && ![...row.tools.values()].some(tool => tool.name === "ask"))
          ?? candidates.find(row => row.sessionId !== this.rootId) ?? candidates[0];
        this.sessions.delete(evicted.sessionId);
      }
      session = newSession(sessionId);
      this.sessions.set(sessionId, session);
    }
    if (type === "session_switch" && isRoot) this.rootId = sessionId;
    session.queued = context.hasQueuedMessages?.() === true;
    let response: unknown;
    switch (type) {
      case "session_start":
        if (session.state === "closed") session.state = "unknown";
        break;
      case "before_agent_start":
        if (sessionId === this.rootId && text(this.options.parentInstructions, 64000) && Array.isArray(event.systemPrompt) && event.systemPrompt.every(item => typeof item === "string")) {
          const instructions = this.options.parentInstructions;
          response = { systemPrompt: event.systemPrompt.includes(instructions) ? event.systemPrompt : [...event.systemPrompt, instructions] };
        }
        break;
      case "agent_start":
        session.active = true;
        session.outcome = undefined;
        session.yielded = undefined;
        session.state = "working";
        break;
      case "turn_start":
        session.active = true;
        session.state = "working";
        break;
      case "message_end":
        this.assistant(session, [event.message]);
        break;
      case "agent_end":
        session.active = false;
        this.assistant(session, Array.isArray(event.messages) ? event.messages : []);
        if (event.stopReason === "paused") session.state = "paused";
        else if (event.stopReason === "aborted" || event.aborted === true) session.state = "cancelled";
        else if (event.stopReason === "error" || event.error || event.errorMessage) { session.outcome = "error"; session.state = "failed"; }
        else session.state = this.finalState(session);
        break;
      case "agent_failed":
        session.outcome = "error";
        session.active = false;
        session.state = "failed";
        break;
      case "auto_retry_start":
        session.active = true;
        session.outcome = undefined;
        session.yielded = undefined;
        session.state = "working";
        break;
      case "auto_retry_end":
        if (event.success !== true && event.willRetry !== true) {
          session.active = false;
          session.outcome = event.aborted === true ? "aborted" : "error";
          session.state = event.aborted === true ? "cancelled" : "failed";
        }
        break;
      case "auto_compaction_start":
        session.maintenance = true;
        break;
      case "auto_compaction_end":
        session.maintenance = false;
        if (!session.active && session.state === "done") session.state = "unknown";
        break;
      case "tool_execution_start":
        this.toolStart(session, event);
        break;
      case "tool_execution_end":
        this.toolEnd(session, event);
        break;
      case "session_shutdown":
        session.active = false;
        if (sessionId === this.rootId) {
          this.closed = true;
          session.state = "closed";
        } else if (!session.decisions.size && !["failed", "cancelled", "paused"].includes(session.state)) {
          // Yield is the native child completion receipt; shutdown by itself
          // cannot prove success, even when no agent_end was delivered.
          session.state = session.yielded === "done" ? "done" : session.yielded === "failed" ? "failed" : "unknown";
        }
        break;
    }
    this.schedule();
    return response;
  }

  private assistant(session: Session, messages: unknown[]): void {
    for (const item of messages) {
      const message = record(item);
      if (message?.role !== "assistant") continue;
      if (message.stopReason === "aborted") session.outcome = "aborted";
      else if (message.stopReason === "error" || message.error || message.errorMessage) session.outcome = "error";
      else session.outcome = ["stop", "toolUse"].includes(String(message.stopReason)) ? message.stopReason as "stop" | "toolUse" : "other";
    }
  }
  private finalState(session: Session): State {
    if (session.outcome === "error") return "failed";
    if (session.outcome === "aborted") return "cancelled";
    if (session.yielded === "failed") return "failed";
    if (session.queued || session.maintenance) return "working";
    if (session.tools.size) return "unknown";
    if (session.yielded === "unknown") return "unknown";
    if (session.yielded === "done" || session.outcome === "stop") return "done";
    return "unknown";
  }
  private toolStart(session: Session, event: RecordValue): void {
    const id = identifier(event.toolCallId), name = identifier(event.toolName);
    if (!id || !name) { this.complete = false; return; }
    if (session.resolved.has(id) || session.tools.has(id)) return;
    if (session.tools.size >= MAX_TOOLS) { this.complete = false; return; }
    const args = record(event.args);
    const questionIds = name === "ask" && Array.isArray(args?.questions)
      ? args.questions.slice(0, MAX_TOOLS).map(q => identifier(record(q)?.id)).filter((id): id is string => Boolean(id)) : [];
    const decisionTokens = new Map<string, symbol>();
    for (const questionId of questionIds) {
      const owners = [...this.sessions.values()].filter(child => child.decisions.has(questionId));
      if (owners.length === 1) decisionTokens.set(questionId, owners[0].decisions.get(questionId)!);
    }
    session.tools.set(id, { name, questionIds, decisionTokens });
    session.state = "working";
  }
  private toolEnd(session: Session, event: RecordValue): void {
    const id = identifier(event.toolCallId), name = identifier(event.toolName);
    if (!id || !name) { this.complete = false; return; }
    if (session.resolved.has(id)) return;
    const tool = session.tools.get(id);
    if (tool && tool.name !== name) { this.complete = false; return; }
    session.tools.delete(id);
    session.resolved.add(id);
    if (session.resolved.size > MAX_RESOLVED) {
      session.resolved.delete(session.resolved.values().next().value!);
      this.complete = false; // Bounded dedup memory exhausted; do not claim full coverage.
    }
    const result = record(event.result);
    const details = record(result?.details);
    if (name === "yield") {
      if (event.isError || !details || !["success", "aborted"].includes(String(details.status))) session.yielded = "unknown";
      else if (details.status === "aborted") session.yielded = "failed";
      else if (details.data === null || details.data === undefined || details.error !== undefined) session.yielded = "unknown";
      else {
        const data = record(details.data);
        if (data?.status === "needs_user_decision") {
          const requestId = decisionId(data);
          if (!requestId || session.decisions.size >= MAX_TOOLS) {
            session.yielded = "unknown";
            if (session.decisions.size >= MAX_TOOLS) this.complete = false;
          } else {
            // A new receipt for a reused ID cannot be answered by an older ask.
            if (!session.decisions.has(requestId)) session.decisions.set(requestId, Symbol());
            session.yielded = "waiting";
          }
        } else session.yielded = "done";
      }
      if (session.yielded === "done" || session.yielded === "failed" || session.yielded === "unknown") session.state = session.yielded;
    }
    if (name === "ask" && session.sessionId === this.rootId && event.isError === false && details && tool) {
      let answered: string[] = [];
      if (Array.isArray(details.results)) answered = details.results.map(record).filter((row): row is RecordValue => Boolean(row && hasAnswer(row))).map(row => identifier(row.id)).filter((id): id is string => Boolean(id && tool.questionIds.includes(id)));
      else if (tool.questionIds.length === 1 && hasAnswer(details)) answered = tool.questionIds;
      for (const requestId of answered) {
        const owners = [...this.sessions.values()].filter(child => child.decisions.has(requestId));
        if (owners.length > 1) { this.complete = false; continue; }
        for (const child of owners) {
          if (child.decisions.get(requestId) !== tool.decisionTokens.get(requestId)) continue;
          child.decisions.delete(requestId);
          child.yielded = undefined;
          child.state = child.active ? "working" : "unknown";
        }
      }
    }
    if (!session.active && session.state !== "paused" && session.state !== "cancelled" && session.state !== "closed") session.state = this.finalState(session);
  }

  snapshot(): Snapshot | undefined {
    if (!this.rootId || !this.identity) return;
    return {
      version: 1, type: "snapshot", producerId: this.producerId, sequence: Math.max(1, this.sequence), launchId: this.launchId,
      pid: process.pid, startedAt: this.startedAt, complete: this.complete, closed: this.closed,
      root: { sessionId: this.rootId, ...this.identity },
      sessions: [...this.sessions.values()].map(session => {
        const pendingAsks = [...session.tools.values()].filter(tool => tool.name === "ask").length;
        const pendingDecisions = session.decisions.size;
        let state = session.state;
        if (pendingAsks || pendingDecisions) state = "waiting";
        else if ((session.active || session.maintenance || session.queued) && !["failed", "cancelled", "paused"].includes(state)) state = "working";
        return { sessionId: session.sessionId, role: session.sessionId === this.rootId ? "root" : "child", state, pendingAsks, pendingDecisions };
      }),
    };
  }
  private schedule(): void {
    if (this.pendingPublish || this.stopped) return;
    this.pendingPublish = true;
    queueMicrotask(() => {
      this.pendingPublish = false;
      try { this.publish(); } catch { this.complete = false; }
    });
  }
  private publish(): void {
    if (this.stopped || !this.rootId) return;
    this.sequence++;
    const frame = this.snapshot();
    if (!frame) return;
    let line = JSON.stringify(frame) + "\n";
    if (Buffer.byteLength(line) > MAX_BYTES) {
      // Maximum identifier/session limits normally keep frames far below this.
      this.complete = false;
      frame.complete = false;
      frame.sessions = frame.sessions.filter(session => session.role === "root");
      line = JSON.stringify(frame) + "\n";
    }
    this.latest = line;
    this.flush();
    this.connect();
  }
  private connect(): void {
    if (this.stopped || this.socket || this.retry || !this.endpoint || !this.latest) return;
    try {
      const socket = createConnection({ path: this.endpoint });
      this.socket = socket;
      socket.unref();
      socket.on("connect", () => { if (this.socket !== socket) return; this.connected = true; this.backoff = 100; this.flush(); });
      socket.on("drain", () => { if (this.socket !== socket) return; this.writing = false; this.flush(); });
      socket.on("error", () => { /* Socket close schedules retry, no host exception. */ });
      socket.on("close", () => {
        if (this.socket !== socket) return;
        this.socket = undefined; this.connected = false; this.writing = false;
        if (!this.stopped) {
          this.retry = setTimeout(() => { this.retry = undefined; this.connect(); }, this.backoff);
          this.retry.unref();
          this.backoff = Math.min(2000, this.backoff * 2);
          // The receiver must get a full snapshot even if nothing changes.
          this.publish();
        }
      });
    } catch {
      this.retry = setTimeout(() => { this.retry = undefined; this.connect(); }, this.backoff);
      this.retry.unref();
    }
  }
  private flush(): void {
    if (!this.connected || !this.socket || this.writing || !this.latest) return;
    const line = this.latest;
    this.latest = undefined;
    this.writing = !this.socket.write(line);
  }
  private shutdown(): Promise<void> {
    if (this.closing) return this.closing;
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.publish();
    this.closing = new Promise(resolve => {
      let timer: ReturnType<typeof setTimeout>;
      let finished = false;
      const finish = () => {
        if (finished) return;
        finished = true;
        clearTimeout(timer);
        this.dispose();
        resolve();
      };
      // The only ref'ed timer is this explicitly awaited, bounded root shutdown.
      timer = setTimeout(finish, 250);
      const tryEnd = () => {
        this.flush();
        if (this.connected && this.socket && !this.latest) this.socket.end(finish);
      };
      this.socket?.once("connect", tryEnd);
      this.socket?.once("drain", tryEnd);
      tryEnd();
    });
    return this.closing;
  }
  /** Test/host disposal, not a claim that the observed GJC root closed. */
  dispose(): void {
    this.stopped = true;
    if (this.retry) clearTimeout(this.retry);
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.socket?.destroy();
    this.socket = undefined;
    this.latest = undefined;
  }
}

/** Safe managed native hook entrypoint; shared across separately installed copies. */
export function createHook(api: HookAPI, options: HookOptions = {}): Publisher | undefined {
  try {
    const globals = globalThis as unknown as Record<symbol, Publisher | undefined>;
    let publisher = globals[SINGLETON];
    if (!publisher) {
      publisher = new Publisher(options);
      globals[SINGLETON] = publisher;
      // Set before tools can launch a nested CLI. Never overwrite another owner.
      if (!process.env[OWNER_ENV]) process.env[OWNER_ENV] = String(process.pid);
    }
    publisher.attach(api);
    return publisher;
  } catch { return undefined; }
}
export default function hook(api: HookAPI): void { createHook(api); }
