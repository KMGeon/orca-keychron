# Parent-routed child decision experiment

This fixture drives the **installed, unmodified GJC 0.16.4 runtime** with a
deterministic loopback model. It tests native child yield, parent tool results,
parent question UI, and same-process child resume. It does **not** test a real
LLM's willingness or ability to follow the decision protocol. A successful run
must not be presented as proof that prompt-only controls enforce the protocol.

The named child has explicit native tools `[read, yield]` and no `spawns`.
It cannot call `ask`. A request for a person is returned as successful
structured data:

```json
{
  "status": "needs_user_decision",
  "request_id": "req_1",
  "question": "[req_1] Choose how the child should continue.",
  "options": ["Continue with A", "Continue with B"],
  "checkpoint": "checkpoint-req_1"
}
```

The fixture parent extracts the **actual** child ID from GJC's task result,
awaits that child, reads its `agent://` output, validates the payload, then calls
parent `ask`. After a real selection it sends the request ID, selected answer,
and checkpoint through `subagent resume` with a nonempty message. The child
validates those fields and returns `answer_consumed: true`. Parent rereads the
resumed child's output before declaring the experiment complete.

The explicit `read agent://...` is deliberate: full subagent inspection may
still contain a task receipt or synopsis, rather than the entire structured
child result. Preview text is never treated as the authoritative decision.

## Reproduce

All commands are run from the repository root. Runtime files default to
`/tmp/gjc-parent-decisions`; nothing is installed globally.

1. Start the loopback model:

   ```sh
   python3 experiments/gjc-parent-decisions/fixture.py serve
   ```

2. Prepare a fresh isolated profile:

   ```sh
   python3 experiments/gjc-parent-decisions/fixture.py prepare --name single_tui --scenario single
   ```

3. Launch the printed command in an Orca terminal. For the example above:

   ```sh
   python3 experiments/gjc-parent-decisions/fixture.py launch --case /tmp/gjc-parent-decisions/cases/single_tui
   ```

4. Choose either displayed option in the real parent question UI. Check
   `provider-metadata.jsonl` for `child_answer_consumed` with all three validity
   flags true, followed by `experiment_complete` with
   `all_decisions_consumed: true`.

Choose `--scenario two` for two concurrent child decisions and two sequential
parent questions. Their request IDs are `req_1` and `req_2`; neither answer is
reused for the other child. Choose `--scenario malicious` to make the child
attempt a direct `ask` first. That call must return `Tool ask not found` before
the child proceeds through structured yield and the parent's question.

The optional `print` operation is a bounded diagnostic; it cannot supply a real
interactive parent answer. It captures stdout/stderr and timeout state under
the case folder, with stdin explicitly disconnected. Each profile is created
once; reuse an existing case only to inspect it, and use a new name to rerun.

## Evidence and limits

- Native hook evidence is written to each case's `events.jsonl`, using the
  existing `../gjc-hooks/observer.ts` loader. Actual launch-time Orca identity is
  captured in `terminal-identity.json`.
- Provider logs retain event names, fixed synthetic request IDs, tool names,
  and validation booleans. They never retain prompts, question answer values,
  tool arguments, request headers, or credentials.
- `parent_child_resume_requested.actual_child_id_used` proves the resume
  target came from the actual task result. `child_answer_consumed` validates
  correlation, allowed answer, and checkpoint separately. Completion requires
  rereading the child's result, not just accepting the resume command.
- GJC native schema handling can become permissive after repeated invalid
  yields. This fixture validates exact decision payloads independently, before
  asking or resuming. Production validation belongs in trusted code.
- Resume is tested within the same running GJC process. Process restart,
  durable decisions, LED output, provider accuracy, and physical Keychron
  interaction are separate concerns.

No GJC core, user authentication store, global hooks, or production settings
are modified. Auto-import is declined in the isolated profile; the only model
endpoint is 127.0.0.1.
