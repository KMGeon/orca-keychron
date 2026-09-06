# Parent-routed child decisions: Orca QA report

Date: 2026-09-06 KST

Verdict: **PASS** for the fixture-defined, same-process parent-routed decision flow on installed GJC 0.16.4.

## Scope and runtime

- QA-only. No GJC core, global auth, global hooks, or production settings were changed.
- Fixture server was live as PID `27873` at `http://127.0.0.1:51394/v1`; all three interactive runs received deterministic model responses from it.
- The model was the local deterministic `parent-decisions/fixture`, not a real LLM. This is runtime/protocol evidence, not proof of real-model compliance or prompt-only enforcement.
- Process-death recovery was not attempted: the fixture README explicitly limits the experiment to same-process resume and lists restart/durability as separate concerns.

## Results

| Case | Parent UI input | Result |
| --- | --- | --- |
| `single_tui` | `Continue with A` | Parent `ask` returned, actual child ID was used for resume, child consumed `req_1`, all three validation flags were true, and completion was true. |
| `two_tui` | `req_1 = Continue with A`; `req_2 = Continue with B` | Both decisions were independently correlated. `req_1` was consumed before the parent requested `req_2`, proving the first answer did not clear or satisfy the second request. Both children then completed and aggregate completion was true. |
| `malicious_tui` | `Continue with A` after the parent-routed prompt | Direct child `ask` failed natively with `Tool ask not found`; the child then yielded structured decision data, the parent asked, resumed the actual child, and the child consumed the correlated answer. |

## Evidence chain

1. `runtime-events.jsonl` records the real Orca terminal identity, parent `ask` calls with `hasUI: true`, successful parent `ask` completion, and parent `agent_end` with `stopReason: completed`.
2. `provider-verdicts.jsonl` records the fixture's bounded validation events. Each resume used the actual child ID, each child reported `correlation_valid`, `answer_valid`, and `checkpoint_valid` as true, and each case ended with `all_decisions_consumed: true`.
3. In `two_tui`, the ordered events are `req_1 child_answer_consumed` -> `req_1 parent_completion_checked` -> `req_2 parent_question_requested`. The second resume payload independently contains `req_2`, `Continue with B`, and `checkpoint-req_2`.
4. In `malicious_tui`, the native child session recorded an error tool result whose text is exactly `Tool ask not found`; the observer also recorded the child `ask` execution ending with `isError: true`.
5. `synthetic-ui-evidence.md` records the rendered-frame observations and the exact harmless key sequences used. Where the narrow pane repainted as only a spinner, the verdict relies on the correlated provider event and native session payload rather than an invented screen state.

## Limits

- This validates the installed, unmodified GJC 0.16.4 runtime against a local fake model and synthetic decisions only.
- It does not validate a real LLM, process restart, durable decision storage, LED output, provider accuracy, or physical Keychron interaction.
- Provider metadata intentionally omits selected answer values; the synthetic child session's non-secret resume payloads were used to confirm A/B selections.

## Cleanup

- Closed only the three owned fixture terminals; each Orca close returned `ptyKilled: true`.
- Stopped fixture server PID `27873` and fixture broker PIDs `35241`, `51319`, and `52851`.
- Final `kill -0` checks reported all seven fixture PIDs (three TUI processes, three brokers, one server) as gone.
