# GJC native hook observation experiment

This directory contains a **read-only exporter prototype**, not a production Keychron integration. It uses GJC's existing native hook loader and does not modify GJC core or register question/approval responders.

The source investigation targets GJC **0.16.4**, commit `f50b17a7fa9faab5935cbf2c358794597b1bd760`.

The installed GJC 0.16.4 experiments are complete: see the [23-scenario report](../../docs/gjc-hook-experiment-results.md), [reproduction instructions](REPRODUCE.md) and [captured case index](evidence/case-index.json). The combined exporter and proposed-policy suite has 27 passing tests / 83 assertions. Live results include confirmed coverage gaps; this is not full approval or hardware support.

## Evidence boundary

`observer.test.ts` uses a **mock HookAPI** and real local filesystem/Unix/TCP transport. Its passing results prove exporter behavior and transport mechanics only. They do **not** prove that GJC emits every lifecycle event, discovers every child session, reports every approval, or drives a physical keyboard. Live GJC runs and their results are recorded separately.

**The socket is best effort, with no acknowledgement or state snapshot.** A disconnect after a successful socket write can lose an in-flight record. Reconnection cannot reconstruct missed GJC events. The disconnected queue is limited to 256 records and drops the oldest record on overflow; `stats.dropped` exposes that loss to the test. The optional JSONL file is an experiment trace, not an automatically replayed durable queue. A receiver must not interpret a missing event or disconnected source as successful completion. Shipping reliability requires an explicit recovery design beyond this prototype.

## Isolated installation

Copy `observer.ts` into a disposable experiment project's `.gjc/hooks/pre/*.ts`, where `*` is the **literal filename basename**. Quote the destination in shell commands:

```sh
mkdir -p /tmp/my-gjc-experiment/.gjc/hooks/pre
cp experiments/gjc-hooks/observer.ts '/tmp/my-gjc-experiment/.gjc/hooks/pre/*.ts'
```

Native directory discovery interprets the basename as an exact tool matcher. Naming it `observer.ts` would filter `tool_call` to a nonexistent tool named `observer`. The wildcard allows all tool names. A single factory registers both lifecycle and tool handlers. Do not install a second copy into `post/`, as that would duplicate lifecycle and other registrations.

Start GJC from the disposable project with either or both optional outputs:

```sh
GJC_KEYCHRON_EVENT_LOG=/tmp/my-gjc-experiment/events.jsonl \
GJC_KEYCHRON_SOCKET=/tmp/my-gjc-experiment/events.sock \
gjc
```

Alternatively, `GJC_KEYCHRON_PORT=12345` connects only to `127.0.0.1`. The receiver must accept newline-delimited JSON. If both socket and port are set, the Unix socket takes precedence. The log's parent directory must already exist.

`GJC_KEYCHRON_RUNTIME_EVENTS=1` additionally registers `tool_execution_start`, `tool_execution_end`, `agent_failed`, and `message_end`. These event names are forwarded by the inspected 0.16.4 native adapter to `ExtensionRunner` and emitted by `AgentSession`, but are absent from the legacy `HookAPI` TypeScript overloads. They are intentionally opt-in and version-sensitive; default operation uses the documented HookAPI events only. Source inspection alone is not proof of delivery in every runtime path.

## Exported information and behavior

Each record carries an exporter instance ID, sequence, unique event ID, timestamp, PID, current session ID, public `SessionHeader.parentSession` when present, and the allowlisted Orca terminal/pane identifiers. `parentSession` is forwarded as supplied; it may be a session path and is **not assumed to be a reliable parent-child ID for every execution mode**.

Tool records contain tool name, tool-call ID, and error booleans. Lifecycle records preserve pause/cancel/maintenance/retry metadata. Loop-end records retain assistant stop reasons and error-presence flags, because an outer `completed` reason by itself is not a success guarantee. `session_start` also records the supplied HookAPI property names and registered event names.

No prompts, question text, tool input, tool output, answer content, raw error messages, credentials, or model tokens are exported. The factory and handlers return `undefined`. Handler exceptions are swallowed; socket/file failures do not block tools or change their results. There is no SDK command, injected message, block result, output mutation, question responder, or model call.

The exporter records occurrences. It does not declare that `tool_call` for `ask` means a person is currently waiting, infer a child relationship from Orca environment variables, decide completion, or compute LED state. Those interpretations require the separately tested GJC semantics.

## Reproduce exporter tests

```sh
bun test experiments/gjc-hooks/observer.test.ts
```

The recorded run in `mock-tests.txt` has **12 passing tests, 55 assertions**. Cases cover documented/runtime registration, unchanged tool returns, redaction, interleaved sessions/parent metadata, duplicate callback and wire-replay identities, `completed` plus assistant error/abort, maintenance/retries/cancellation/shutdown, failed destinations, Unix/TCP push, late receiver startup, receiver restart, and bounded queue overflow. All GJC emission inputs in this suite are explicitly mocked.

## Source pointers

- `docs/hooks.md`: native directory hook contracts and lifecycle scope.
- `packages/coding-agent/src/discovery/builtin.ts`: `loadHooks`, filename-to-tool matcher.
- `packages/coding-agent/src/extensibility/hooks/loader.ts`: factory import, HookAPI creation, public context adaptation, and event registration forwarding.
- `packages/coding-agent/src/extensibility/hooks/types.ts`: documented HookAPI events and context.
- `packages/coding-agent/src/session/agent-session.ts`: forwarding of runtime `tool_execution_*`, `message_end`, and `agent_failed` events.
- `packages/coding-agent/src/session/session-manager.ts`: public read-only session ID and header access.
