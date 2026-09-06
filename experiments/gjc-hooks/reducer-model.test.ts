/** Recommended LED policy tests. Synthetic counterexamples unless explicitly
 * labelled captured TUI replay. Passing does not prove child/approval coverage. */
import { test, expect } from "bun:test";
import { assignSlot, emptyModel, identity, producerLost, reduceObservation, slotState, type Observation } from "./reducer-model";

function fixture() {
  let model = emptyModel(); const sequence: Record<string, number> = {};
  return {
    get model() { return model; },
    send(type: string, details: Partial<Observation> = {}, sessionId = "s", producerId = "p") {
      const event = { type, sessionId, producerId, sequence: (sequence[producerId] ?? 0) + 1, ...details } as Observation;
      sequence[producerId] = event.sequence; model = reduceObservation(model, event); return event;
    },
    replay(event: Observation) { model = reduceObservation(model, event); },
    bind(slot = "1", members = [{ sessionId: "s", producerId: "p" }]) { model = assignSlot(model, slot, members); },
    lost(producerId = "p") { model = producerLost(model, producerId); },
    state(slot = "1") { return slotState(model, slot); },
  };
}
const success = { stopReason: "completed", assistantOutcomes: [{ stopReason: "stop", hasError: false }] };

test("RECOMMENDED: one observed pending ask outranks ten running members", () => {
  const f=fixture(); const members=Array.from({length:11},(_,i)=>({sessionId:`s${i}`,producerId:`p${i}`})); f.bind("1",members);
  for(const m of members)f.send("agent_start",{},m.sessionId,m.producerId);
  f.send("tool_call",{toolName:"ask",toolCallId:"q"},"s10","p10");expect(f.state()).toMatchObject({color:"orange",pendingAsks:1,running:11});
});
test("RECOMMENDED: resolving one of two asks leaves orange",()=>{
  const f=fixture();f.bind();f.send("agent_start");for(const toolCallId of ["a","b"])f.send("tool_call",{toolName:"ask",toolCallId});f.send("tool_result",{toolCallId:"a",isError:false});expect(f.state()).toMatchObject({color:"orange",pendingAsks:1});
});
test("RECOMMENDED: tool/runtime pairs and replay do not double count or reopen",()=>{
  const f=fixture();f.bind();f.send("agent_start");const start=f.send("tool_execution_start",{toolName:"ask",toolCallId:"q"});f.send("tool_call",{toolName:"ask",toolCallId:"q"});f.replay(start);expect(f.state().pendingAsks).toBe(1);f.send("tool_result",{toolCallId:"q"});f.send("tool_execution_end",{toolCallId:"q"});f.send("tool_call",{toolName:"ask",toolCallId:"q"});expect(f.state().pendingAsks).toBe(0);
});
test("RECOMMENDED: same toolCallId in different producers/sessions is independent",()=>{
  const f=fixture();f.bind("1",[{sessionId:"a",producerId:"pa"},{sessionId:"b",producerId:"pb"}]);for(const [s,p] of [["a","pa"],["b","pb"]])f.send("tool_call",{toolName:"ask",toolCallId:"shared"},s,p);f.send("tool_result",{toolCallId:"shared"},"a","pa");expect(f.state().pendingAsks).toBe(1);
});
test("RECOMMENDED: recovered tool failure followed by successful final response is green",()=>{
  const f=fixture();f.bind();f.send("agent_start");f.send("tool_call",{toolName:"read",toolCallId:"r"});f.send("tool_result",{toolCallId:"r",isError:true});expect(f.state().color).toBe("yellow");f.send("agent_end",success);expect(f.state().color).toBe("green");
});
test("RECOMMENDED: completed with final assistant error is red",()=>{
  const f=fixture();f.bind();f.send("agent_start");f.send("agent_end",{stopReason:"completed",assistantOutcomes:[{stopReason:"error",hasError:true}]});expect(f.state().color).toBe("red");
});
test("RECOMMENDED: completed with only toolUse plus aborted/error tool is not green",()=>{
  const f=fixture();f.bind();f.send("agent_start");f.send("tool_execution_start",{toolName:"bash",toolCallId:"b"});f.send("tool_execution_end",{toolCallId:"b",isError:true});f.send("agent_end",{stopReason:"completed",assistantOutcomes:[{stopReason:"toolUse",hasError:false}]});expect(f.state()).toMatchObject({state:"incomplete",color:"cyan"});
});
test("RECOMMENDED: sequence gap remains unknown even if later success arrives",()=>{
  const f=fixture();f.bind();f.send("session_start");f.send("agent_end",{...success,sequence:7});expect(f.state()).toMatchObject({state:"unknown",color:"off"});f.send("agent_end",success);expect(f.state().color).toBe("off");
});
test("RECOMMENDED: producer crash cannot retain green; replacement requires explicit membership",()=>{
  const f=fixture();f.bind();f.send("agent_end",success);expect(f.state().color).toBe("green");f.lost();expect(f.state().state).toBe("unknown");f.send("agent_end",success,"s","new-p");expect(f.state().state).toBe("unknown");f.bind("1",[{sessionId:"s",producerId:"new-p"}]);expect(f.state().color).toBe("green");
});
test("RECOMMENDED: parentSession/cwd/Orca hints never add slot members",()=>{
  const f=fixture();f.bind();f.send("agent_end",success);f.send("tool_call",{toolName:"ask",toolCallId:"q",parentSession:"s",orcaTerminalHandle:"same"},"child","child-p");expect(f.state().color).toBe("green");f.bind("1",[{sessionId:"s",producerId:"p"},{sessionId:"child",producerId:"child-p"}]);expect(f.state().color).toBe("orange");
});
test("RECOMMENDED: observed pending ask outranks failure; resolving exposes failure",()=>{
  const f=fixture();f.bind("1",[{sessionId:"s",producerId:"p"},{sessionId:"f",producerId:"pf"}]);f.send("tool_call",{toolName:"ask",toolCallId:"q"});f.send("agent_failed",{},"f","pf");expect(f.state().color).toBe("orange");f.send("tool_result",{toolCallId:"q"});expect(f.state().color).toBe("red");
});
test("RECOMMENDED: maintenance/checkpoints and queued work are not completion",()=>{
  const f=fixture();f.bind();f.send("agent_start");f.send("agent_end",{stopReason:"maintenance",maintenanceOutcome:"compacted"});expect(f.state().color).toBe("yellow");f.send("agent_end",{...success,hasQueuedMessages:true});expect(f.state().color).toBe("yellow");f.send("agent_end",{stopReason:"paused"});expect(f.state().color).not.toBe("green");
});
test("RECOMMENDED: reducer does not mutate previous input state",()=>{
  const previous=emptyModel();const next=reduceObservation(previous,{type:"agent_start",sessionId:"s",producerId:"p",sequence:1});expect(Object.keys(previous.sessions)).toHaveLength(0);expect(next.sessions[identity("s","p")].status).toBe("running");
});
test("CAPTURED TUI metadata replay: 2 asks, one resolved, other aborted, outer completed is not green",()=>{
  // Exact metadata subset from actual installed-GJC case tui_v2 seq34..51.
  // Original sequence values preserved; earlier lifecycle establishes continuity.
  // This replay checks our policy, not a second GJC run or hidden child coverage.
  const f=fixture();f.bind();for(let sequence=1;sequence<=33;sequence++)f.send("fixture_prior_event",{sequence});
  const rows: Partial<Observation>[]=[
    {sequence:34,type:"before_agent_start"},{sequence:35,type:"agent_start"},{sequence:36,type:"turn_start"},{sequence:37,type:"message_end"},{sequence:38,type:"message_end"},{sequence:39,type:"message_end",assistantOutcomes:[{stopReason:"toolUse",hasError:false}]},
    {sequence:40,type:"tool_execution_start",toolName:"ask",toolCallId:"call_50649db38132_0"},{sequence:41,type:"tool_execution_start",toolName:"ask",toolCallId:"call_50649db38132_1"},{sequence:42,type:"tool_call",toolName:"ask",toolCallId:"call_50649db38132_1"},{sequence:43,type:"tool_call",toolName:"ask",toolCallId:"call_50649db38132_0"},
    {sequence:44,type:"tool_result",toolName:"ask",toolCallId:"call_50649db38132_0",isError:false},{sequence:45,type:"tool_execution_end",toolName:"ask",toolCallId:"call_50649db38132_0",isError:false},{sequence:46,type:"message_end"},
    {sequence:47,type:"tool_execution_end",toolName:"ask",toolCallId:"call_50649db38132_1",isError:true},{sequence:48,type:"tool_result",toolName:"ask",toolCallId:"call_50649db38132_1",isError:true},{sequence:49,type:"turn_end",assistantOutcomes:[{stopReason:"toolUse",hasError:false}]},{sequence:50,type:"message_end"},{sequence:51,type:"agent_end",stopReason:"completed",assistantOutcomes:[{stopReason:"toolUse",hasError:false}]},
  ];
  for(const row of rows){f.send(row.type!,row);if(row.sequence===43)expect(f.state().pendingAsks).toBe(2);if(row.sequence===44)expect(f.state()).toMatchObject({color:"orange",pendingAsks:1});}expect(f.state()).toMatchObject({state:"incomplete",color:"cyan",pendingAsks:0});
});
test("RECOMMENDED: per-producer continuity allows session switching without false gaps",()=>{
  const f=fixture();f.bind("1",[{sessionId:"a",producerId:"p"},{sessionId:"b",producerId:"p"}]);f.send("session_start",{},"a");f.send("session_switch",{},"b");f.send("agent_start",{},"b");expect(f.state().state).toBe("running");
});
