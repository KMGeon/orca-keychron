/** All cases in this file use a MOCK HookAPI. They test our exporter/transport,
 * not GJC emission coverage, native discovery, real approvals, or hardware. */
import { test, expect, afterEach } from "bun:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer, type Server, type Socket } from "node:net";
import { createObserver, createTransport, DOCUMENTED_EVENTS, RUNTIME_EVENTS } from "./observer";

const cleanups: (() => void | Promise<void>)[] = [];
afterEach(async () => { for (const cleanup of cleanups.splice(0).reverse()) await cleanup(); });
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
async function waitFor(predicate: () => boolean, timeout = 2000) {
  const start = Date.now();
  while (!predicate()) { if (Date.now() - start > timeout) throw new Error("condition timed out"); await delay(10); }
}
async function directory() { const path = await mkdtemp(join(tmpdir(), "gjc-observer-unit-")); cleanups.push(() => rm(path, { recursive: true, force: true })); return path; }
function mockApi() {
  const handlers = new Map<string, any>();
  const api = { on: (type: string, handler: any) => handlers.set(type, handler) };
  const context = (id: string, parent?: string) => ({ sessionManager: { getSessionId: () => id, getHeader: () => ({ id, parentSession: parent }) }, hasUI: true, isIdle: () => false, hasQueuedMessages: () => false });
  return { api, handlers, context, emit: (type: string, payload: Record<string, unknown>, id = "s1", parent?: string) => handlers.get(type)?.({ type, ...payload }, context(id, parent)) };
}
async function capture(runtime = false, extras: Record<string,string> = {}) {
  const path = join(await directory(), "events.jsonl");
  const mock = mockApi();
  const transport = createObserver(mock.api, { GJC_KEYCHRON_EVENT_LOG: path, ...(runtime ? {GJC_KEYCHRON_RUNTIME_EVENTS:"1"} : {}), ...extras });
  cleanups.push(() => transport.close());
  return { ...mock, transport, async rows() { await transport.flushDisk(); return (await readFile(path,"utf8")).trim().split("\n").map(line => JSON.parse(line)); } };
}
async function listen(path?: string, port = 0) {
  const rows: any[] = []; const sockets = new Set<Socket>();
  const server = createServer(socket => { sockets.add(socket); let buffer=""; socket.on("close",()=>sockets.delete(socket)); socket.on("data",data=> { buffer+=data.toString(); let pos; while((pos=buffer.indexOf("\n"))>=0) {rows.push(JSON.parse(buffer.slice(0,pos)));buffer=buffer.slice(pos+1);} }); });
  await new Promise<void>((resolve,reject) => {server.once("error",reject);path?server.listen(path,resolve):server.listen(port,"127.0.0.1",resolve);});
  cleanups.push(async()=>{ for(const socket of sockets) socket.destroy(); if(server.listening) await new Promise<void>(resolve=>server.close(()=>resolve())); });
  return {server,rows,sockets,port:typeof server.address()==="object"?(server.address() as any)?.port:undefined};
}

test("MOCK: documented lifecycle registration; runtime-only events require opt in", async()=>{
  const a=await capture(); expect([...a.handlers.keys()]).toEqual(DOCUMENTED_EVENTS);
  const b=await capture(true); expect([...b.handlers.keys()]).toEqual([...DOCUMENTED_EVENTS,...RUNTIME_EVENTS]);
});

test("MOCK: handlers preserve tool behavior and capture API metadata", async()=>{
  const c=await capture(); expect(c.emit("session_start",{})).toBeUndefined();
  expect(c.emit("tool_call",{toolName:"ask",toolCallId:"q1",input:{question:"SECRET"}})).toBeUndefined();
  expect(c.emit("tool_result",{toolName:"ask",toolCallId:"q1",isError:false,content:[{text:"SECRET"}]})).toBeUndefined();
  const rows=await c.rows();expect(rows[0].hookApiKeys).toEqual(["on"]);expect(rows[1].toolCallId).toBe("q1");expect(rows[2].isError).toBe(false);expect(JSON.stringify(rows)).not.toContain("SECRET");
});

test("MOCK: interleaved sessions and child identity are never globally overwritten",async()=>{
  const c=await capture(); c.emit("session_start",{},"parent-a");c.emit("tool_call",{toolName:"ask",toolCallId:"same-id"},"child-a","parent-a.jsonl");c.emit("tool_call",{toolName:"ask",toolCallId:"same-id"},"parent-b");c.emit("tool_result",{toolName:"ask",toolCallId:"same-id"},"child-a","parent-a.jsonl");
  const rows=await c.rows();expect(rows.map(row=>row.sessionId)).toEqual(["parent-a","child-a","parent-b","child-a"]);expect(rows[1].parentSession).toBe("parent-a.jsonl");expect(rows[2].parentSession).toBeUndefined();
});

test("MOCK: duplicate source callbacks retain distinct sequence identity for audit",async()=>{
  const c=await capture(); for(let i=0;i<2;i++) c.emit("tool_call",{toolName:"ask",toolCallId:"q1"});const rows=await c.rows();expect(new Set(rows.map(row=>row.eventId)).size).toBe(2);expect(rows.map(row=>row.sequence)).toEqual([1,2]);
  // Consumer key must be sessionId + toolCallId, not a callback count. Wire replay can use eventId.
  const pending=new Map();const seen=new Set();for(const row of [...rows,rows[0]]){if(seen.has(row.eventId))continue;seen.add(row.eventId);pending.set(`${row.sessionId}:${row.toolCallId}`,row);}expect(pending.size).toBe(1);
});

test("MOCK: loop-end completed retains assistant failure/abort evidence",async()=>{
  const c=await capture();c.emit("agent_end",{stopReason:"completed",messages:[{role:"user",content:"SECRET"},{role:"assistant",stopReason:"error",errorMessage:"SECRET"}]});c.emit("agent_end",{stopReason:"completed",messages:[{role:"assistant",stopReason:"aborted"}]});const rows=await c.rows();expect(rows[0].assistantOutcomes).toEqual([{stopReason:"error",hasError:true}]);expect(rows[1].assistantOutcomes[0].stopReason).toBe("aborted");expect(JSON.stringify(rows)).not.toContain("SECRET");
});

test("MOCK: maintenance, retries, cancellation and shutdown preserve distinctions",async()=>{
  const c=await capture();for(const outcome of ["pruned","compacted","promoted","failed","aborted"])c.emit("agent_end",{stopReason:"maintenance",maintenanceOutcome:outcome});c.emit("agent_end",{stopReason:"paused"});c.emit("agent_end",{stopReason:"cancelled"});c.emit("auto_retry_start",{attempt:1,maxAttempts:3,errorMessage:"SECRET"});c.emit("auto_retry_end",{attempt:1,success:true});c.emit("session_shutdown",{});const rows=await c.rows();expect(rows.slice(0,5).map(row=>row.maintenanceOutcome)).toEqual(["pruned","compacted","promoted","failed","aborted"]);expect(rows.slice(5,7).map(row=>row.stopReason)).toEqual(["paused","cancelled"]);expect(rows[7].hasError).toBe(true);expect(rows[8].success).toBe(true);expect(rows.at(-1).type).toBe("session_shutdown");expect(JSON.stringify(rows)).not.toContain("SECRET");
});

test("MOCK: context failure and missing socket/log destination never throw or block",async()=>{
  const mock=mockApi();const root=await directory();const t=createObserver(mock.api,{GJC_KEYCHRON_SOCKET:join(root,"absent.sock"),GJC_KEYCHRON_EVENT_LOG:join(root,"missing-dir","log")});cleanups.push(()=>t.close());const start=performance.now();for(let i=0;i<20;i++)expect(mock.emit("tool_call",{toolName:"read",toolCallId:String(i)})).toBeUndefined();expect(mock.handlers.get("tool_call")({}, {sessionManager:{getHeader(){throw new Error("SECRET")}}})).toBeUndefined();expect(performance.now()-start).toBeLessThan(100);await t.flushDisk();await waitFor(()=>t.stats.connectionErrors>0);expect(t.stats.diskErrors).toBe(20);
});

test("MOCK: Unix socket pushes records immediately in order without polling",async()=>{
  const path=join(await directory(),"events.sock");const server=await listen(path);const t=createTransport({GJC_KEYCHRON_SOCKET:path});cleanups.push(()=>t.close());for(let i=1;i<=10;i++)t.send({sequence:i});await waitFor(()=>server.rows.length===10);expect(server.rows.map(row=>row.sequence)).toEqual([1,2,3,4,5,6,7,8,9,10]);expect(t.stats.dropped).toBe(0);
});

test("MOCK: local TCP pushes the same framing",async()=>{
  const server=await listen();const t=createTransport({GJC_KEYCHRON_PORT:String(server.port)});cleanups.push(()=>t.close());t.send({sessionId:"s-tcp",type:"agent_start"});await waitFor(()=>server.rows.length===1);expect(server.rows[0].sessionId).toBe("s-tcp");
});

test("MOCK: delayed receiver startup reconnects and flushes pending events",async()=>{
  const path=join(await directory(),"late.sock");const t=createTransport({GJC_KEYCHRON_SOCKET:path});cleanups.push(()=>t.close());t.send({sequence:1});t.send({sequence:2});await waitFor(()=>t.stats.connectionErrors>0);const server=await listen(path);await waitFor(()=>server.rows.length===2);expect(server.rows.map(row=>row.sequence)).toEqual([1,2]);
});

test("MOCK: receiver disconnect then new events reconnect; no ACK guarantee claimed",async()=>{
  const path=join(await directory(),"restart.sock");const t=createTransport({GJC_KEYCHRON_SOCKET:path});cleanups.push(()=>t.close());const first=await listen(path);t.send({sequence:1});await waitFor(()=>first.rows.length===1);for(const socket of first.sockets)socket.destroy();await new Promise<void>(resolve=>first.server.close(()=>resolve()));await delay(30);t.send({sequence:2});await waitFor(()=>t.stats.connectionErrors>0);const second=await listen(path);await waitFor(()=>second.rows.length===1);expect(second.rows[0].sequence).toBe(2);
});

test("MOCK: disconnected queue is bounded and exposes event loss",async()=>{
  const path=join(await directory(),"full.sock");const t=createTransport({GJC_KEYCHRON_SOCKET:path});cleanups.push(()=>t.close());for(let sequence=1;sequence<=300;sequence++)t.send({sequence});expect(t.stats.dropped).toBe(44);const server=await listen(path);await waitFor(()=>server.rows.length===256);expect(server.rows[0].sequence).toBe(45);expect(server.rows.at(-1).sequence).toBe(300);
});
