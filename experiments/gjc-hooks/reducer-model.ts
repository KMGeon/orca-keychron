/** EXPERIMENT / RECOMMENDED POLICY ORACLE, not product code.
 * Pure functions over observer.ts metadata; no GJC calls or hardware effects.
 * Orange here means an observed ask call remains open. Whether it is actually
 * actionable/visible requires separate UI evidence; this does not detect every
 * approval or prove child-ask coverage. Membership is supplied explicitly.
 */
export interface Observation {
  type: string;
  producerId: string;
  sessionId: string;
  sequence: number;
  eventId?: string;
  toolCallId?: string;
  toolName?: string;
  isError?: boolean;
  hasError?: boolean;
  stopReason?: string;
  maintenanceOutcome?: string;
  success?: boolean;
  hasQueuedMessages?: boolean;
  assistantOutcomes?: { stopReason?: string; hasError?: boolean }[];
  [key: string]: unknown;
}
export type Status = "idle" | "running" | "complete" | "failed" | "paused" | "cancelled" | "incomplete";
export interface SessionState {
  producerId: string;
  sessionId: string;
  status: Status;
  tools: Record<string, { ask: boolean }>;
  finishedTools: string[];
  toolHadError: boolean;
}
export interface Model {
  sessions: Record<string, SessionState>;
  producers: Record<string, { lastSequence: number; unknown: boolean }>;
  slots: Record<string, string[]>;
}
export function identity(sessionId: string, producerId: string): string { return JSON.stringify([sessionId, producerId]); }
export function emptyModel(): Model { return { sessions: {}, producers: {}, slots: {} }; }
export function assignSlot(model: Model, slot: string, members: { sessionId: string; producerId: string }[]): Model {
  const next = structuredClone(model);
  next.slots[slot] = [...new Set(members.map(member => identity(member.sessionId, member.producerId)))];
  return next;
}
export function producerLost(model: Model, producerId: string): Model {
  const next = structuredClone(model);
  const producer = next.producers[producerId] ?? { lastSequence: 0, unknown: false };
  next.producers[producerId] = { ...producer, unknown: true };
  return next;
}
export function reduceObservation(model: Model, event: Observation): Model {
  const next = structuredClone(model);
  const producer = next.producers[event.producerId] ?? { lastSequence: 0, unknown: false };
  next.producers[event.producerId] = producer;
  // Sequence is per exporter instance, including when its active session changes.
  if (event.sequence <= producer.lastSequence) return next;
  if (event.sequence !== producer.lastSequence + 1) producer.unknown = true;
  producer.lastSequence = event.sequence;
  const key = identity(event.sessionId, event.producerId);
  const session = next.sessions[key] ?? { producerId: event.producerId, sessionId: event.sessionId, status: "idle", tools: {}, finishedTools: [], toolHadError: false };
  next.sessions[key] = session;
  if (event.type === "before_agent_start" || event.type === "agent_start") {
    if (session.status !== "running") { session.tools = {}; session.finishedTools = []; session.toolHadError = false; }
    session.status = "running";
  }
  if (["tool_call", "tool_execution_start"].includes(event.type) && event.toolCallId && !session.finishedTools.includes(event.toolCallId)) {
    session.tools[event.toolCallId] = { ask: event.toolName === "ask" };
  }
  if (["tool_result", "tool_execution_end"].includes(event.type) && event.toolCallId) {
    delete session.tools[event.toolCallId];
    if (!session.finishedTools.includes(event.toolCallId)) session.finishedTools.push(event.toolCallId);
    session.toolHadError ||= event.isError === true;
  }
  if (["auto_retry_start", "auto_compaction_start"].includes(event.type)) session.status = "running";
  if (event.type === "auto_retry_end") session.status = event.success === false ? "failed" : "running";
  if (event.type === "agent_failed") session.status = "failed";
  if (event.type === "agent_end") {
    const final = event.assistantOutcomes?.at(-1);
    if (event.stopReason === "maintenance" && ["pruned", "compacted", "promoted"].includes(event.maintenanceOutcome ?? "")) session.status = "running";
    else if (event.stopReason === "paused") session.status = "paused";
    else if (event.stopReason === "cancelled" || final?.stopReason === "aborted") session.status = "cancelled";
    else if (final?.hasError || final?.stopReason === "error" || event.hasError || event.maintenanceOutcome === "failed") session.status = "failed";
    else if (event.stopReason === "completed" && final?.stopReason === "stop" && !Object.keys(session.tools).length) session.status = event.hasQueuedMessages ? "running" : "complete";
    else session.status = "incomplete";
    if (["paused", "cancelled"].includes(session.status)) session.tools = {};
  }
  if (event.type === "session_shutdown" && session.status === "running") session.status = "incomplete";
  return next;
}
export function slotState(model: Model, slot: string) {
  const keys = model.slots[slot] ?? [];
  const members = keys.map(key => model.sessions[key]);
  const pendingAsks = members.reduce((count, member) => count + Object.values(member?.tools ?? {}).filter(tool => tool.ask).length, 0);
  const running = members.filter(member => member?.status === "running").length;
  const unknown = !keys.length || members.some(member => !member || model.producers[member.producerId]?.unknown);
  // Unknown is a data-validity guard, not an urgency category. Never show success from a broken stream.
  if (unknown) return { state: "unknown", color: "off", pendingAsks, running };
  if (pendingAsks) return { state: "attention", color: "orange", pendingAsks, running };
  if (members.some(member => member.status === "failed")) return { state: "failed", color: "red", pendingAsks, running };
  if (running) return { state: "running", color: "yellow", pendingAsks, running };
  if (members.every(member => member.status === "complete")) return { state: "complete", color: "green", pendingAsks, running };
  return { state: members.some(member => member.status === "incomplete") ? "incomplete" : "idle", color: "cyan", pendingAsks, running };
}
