/** GJC 0.16.4 native-hook observation experiment; no prompt/tool content exported.
 * Copy to PROJECT/.gjc/hooks/pre/*.ts (literal asterisk basename).
 * GJC_KEYCHRON_EVENT_LOG=/absolute/events.jsonl is optional durable experiment capture.
 * GJC_KEYCHRON_SOCKET=/absolute/events.sock OR GJC_KEYCHRON_PORT=12345 pushes JSONL.
 * GJC_KEYCHRON_RUNTIME_EVENTS=1 opts into events accepted by the 0.16.4 adapter
 * but absent from its legacy HookAPI TypeScript overloads. Version-sensitive.
 * Socket transport is best effort, bounded, and has no receiver acknowledgement.
 */
import { appendFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { createConnection, type Socket } from "node:net";

type Metadata = Record<string, unknown>;
type Context = { sessionManager?: { getSessionId?(): string; getHeader?(): Metadata | null }; hasUI?: boolean; isIdle?(): boolean; hasQueuedMessages?(): boolean };
type API = { on(event: string, handler: (event: Metadata, context: Context) => void): void };
export const DOCUMENTED_EVENTS = ["session_start", "session_switch", "session_branch", "session_tree", "session_shutdown", "before_agent_start", "agent_start", "agent_end", "turn_start", "turn_end", "auto_compaction_start", "auto_compaction_end", "auto_retry_start", "auto_retry_end", "tool_call", "tool_result"];
export const RUNTIME_EVENTS = ["tool_execution_start", "tool_execution_end", "agent_failed", "message_end"];

function boundedString(value: unknown): string | undefined {
  return typeof value === "string" ? value.slice(0, 512) : undefined;
}

export function safeMetadata(type: string, event: Metadata, context: Context): Metadata {
  const header = context.sessionManager?.getHeader?.();
  const metadata: Metadata = { type, sessionId: boundedString(context.sessionManager?.getSessionId?.()), parentSession: boundedString(header?.parentSession), hasUI: context.hasUI };
  for (const key of ["toolCallId", "toolName", "stopReason", "maintenanceOutcome"]) {
    const value = boundedString(event[key]);
    if (value !== undefined) metadata[key] = value;
  }
  for (const key of ["isError", "aborted", "willRetry", "skipped", "success", "unbounded"]) {
    if (typeof event[key] === "boolean") metadata[key] = event[key];
  }
  for (const key of ["turnIndex", "attempt", "maxAttempts", "delayMs"]) {
    if (typeof event[key] === "number" && Number.isFinite(event[key])) metadata[key] = event[key];
  }
  const reason = event.reason;
  if (["new", "resume", "fork", "threshold", "overflow", "idle"].includes(String(reason))) metadata.reason = reason;
  if (["context-full", "handoff"].includes(String(event.action))) metadata.action = event.action;
  metadata.hasError = Boolean(event.error || event.errorMessage || event.finalError);
  if (context.isIdle) metadata.isIdle = context.isIdle();
  if (context.hasQueuedMessages) metadata.hasQueuedMessages = context.hasQueuedMessages();
  // Loop-end "completed" can accompany assistant error/abort. Export outcome flags only.
  const messages = Array.isArray(event.messages) ? event.messages : event.message ? [event.message] : [];
  const assistantOutcomes = messages.filter((message: any) => message?.role === "assistant").map((message: any) => ({ stopReason: boundedString(message.stopReason), hasError: Boolean(message.errorMessage || message.error) }));
  if (assistantOutcomes.length) metadata.assistantOutcomes = assistantOutcomes.slice(-16);
  return metadata;
}

export function createTransport(env: Record<string, string | undefined> = process.env) {
  const logPath = env.GJC_KEYCHRON_EVENT_LOG;
  const socketPath = env.GJC_KEYCHRON_SOCKET;
  const port = Number(env.GJC_KEYCHRON_PORT);
  const endpoint = socketPath ? { path: socketPath } : Number.isInteger(port) && port > 0 && port < 65536 ? { host: "127.0.0.1", port } : undefined;
  const queue: string[] = [];
  let socket: Socket | undefined;
  let connected = false;
  let waitingDrain = false;
  let stopped = false;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let diskWrites = Promise.resolve();
  const stats = { enqueued: 0, sent: 0, dropped: 0, connectionErrors: 0, diskErrors: 0 };

  function flush() {
    if (!connected || !socket || waitingDrain) return;
    while (queue.length) {
      const line = queue.shift()!;
      stats.sent++;
      if (!socket.write(line)) { waitingDrain = true; return; }
    }
  }
  function connect() {
    if (stopped || !endpoint || socket || !queue.length) return;
    try {
      const active = createConnection(endpoint);
      socket = active;
      active.unref();
      active.on("connect", () => { connected = true; flush(); });
      active.on("drain", () => { waitingDrain = false; flush(); });
      active.on("error", () => { stats.connectionErrors++; });
      active.on("close", () => {
        connected = false;
        waitingDrain = false;
        socket = undefined;
        if (!stopped && queue.length) {
          retry = setTimeout(() => { retry = undefined; connect(); }, 100);
          retry.unref?.();
        }
      });
    } catch { stats.connectionErrors++; }
  }
  return {
    stats,
    send(record: Metadata) {
      if (stopped) return;
      try {
        const line = `${JSON.stringify(record)}\n`;
        if (logPath) diskWrites = diskWrites.then(() => appendFile(logPath, line, { mode: 0o600 })).catch(() => { stats.diskErrors++; });
        if (!endpoint) return;
        stats.enqueued++;
        if (queue.length >= 256) { queue.shift(); stats.dropped++; }
        queue.push(line);
        flush();
        if (!retry) connect();
      } catch { stats.dropped++; }
    },
    async flushDisk() { await diskWrites; },
    close() { stopped = true; if (retry) clearTimeout(retry); socket?.destroy(); },
  };
}

export function createObserver(api: API, env: Record<string, string | undefined> = process.env) {
  const transport = createTransport(env);
  const producerId = randomUUID();
  let sequence = 0;
  const hookApiKeys = Object.keys(api).sort();
  const eventTypes = [...DOCUMENTED_EVENTS, ...(env.GJC_KEYCHRON_RUNTIME_EVENTS === "1" ? RUNTIME_EVENTS : [])];
  for (const type of eventTypes) {
    api.on(type, (event, context) => {
      try {
        const metadata = safeMetadata(type, event, context);
        transport.send({ schemaVersion: 1, producerId, sequence: ++sequence, eventId: `${producerId}:${sequence}`, observedAt: new Date().toISOString(), pid: process.pid, orcaTerminalHandle: boundedString(env.ORCA_TERMINAL_HANDLE), orcaPaneKey: boundedString(env.ORCA_PANE_KEY), ...metadata, ...(type === "session_start" ? { hookApiKeys, registeredEvents: eventTypes } : {}) });
      } catch {
        // Observation must never block tools, alter output, or interfere with GJC.
      }
      return undefined;
    });
  }
  return transport;
}

export default function observer(api: API): void { createObserver(api); }
