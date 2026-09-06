# Native GJC child and retry experiments

Actual installed GJC 0.16.4 invoked with isolated agent dirs, loopback mock model,
and project native hooks. No GJC core edits. No hardware or physical LED claims.

Evidence index: `/tmp/gjc-keychron-live-experiments/worker-results.json` (21 runs).
Metadata-only interpretation: `worker-metadata-summary.json` in the same folder.
All 21 disk-vs-TCP event ID sets match. No run hit its subprocess timeout.
`worker-process-check.json` found no remaining worker case process after the
first 20 runs; the final fallback run also exited normally.

## Confirmed useful cases

| Case directory under `/tmp/gjc-keychron-live-experiments/cases/` | Actual result |
| --- | --- |
| worker_task_wait_configured | One real child, 2 sessions, 61 pushed events, root and child complete |
| worker_task_pair_configured | Two real children, 3 sessions, 96 pushed events |
| worker_task_fail_configured | Child receives fixed HTTP 400 and fails; parent finishes with completed. Child status must remain independent. |
| worker_task_nested_clean | Custom project agents produce real root → child → grandchild, 3 sessions, 60 pushed events, no tool errors, exit 0 |
| worker_task_wait_ask_clean | Custom child actually calls ask and stays pending; parent await times out and parent finishes; 36 events, exit 1 after 16.379 seconds due SessionDisposalIncompleteError |
| worker_task_wait_mixed_custom | Three children: ask pending, slow model working, one completed; parent await sees running/running/completed. 61 events. Exit 1 after 16.27 seconds due same disposal error. |
| worker_transient_error_fallback | First HTTP 503, managed retry, successful result; auto_retry_start and auto_retry_end success events, 12/12 pushed events, exit 0 in 1.068 seconds |

The `_clean` cases explicitly set subprocess stdin to DEVNULL. Earlier Python
heredoc runners inherited the harmless harness source through stdin, which GJC
prepended to the user message. Clean reruns reproduce nested and pending-child
results with only the intended 22-character scenario prompt. Do not present
initial runs as pure single-marker prompt tests.

## Fixture boundaries and exclusions

The first six worker task runs were invalid task fixtures: `isolated: false`
was present while default task isolation mode was `none`. GJC rejects the
presence of this field even when false. These prove admission failure and
root-completion behavior, not child execution. Configured reruns used
`task.isolation.mode: auto` with explicit `isolated: false`, so no actual
isolated workspace was made.

Bundled executor child sessions did not have ask/task/subagent active. Calls
returned `Tool ask not found`, `Tool task not found`, and `Tool subagent not
found`. Those attempted questions/nesting must not be counted as executed.
Custom project-only executor and lab-leaf definitions explicitly list tools
and enable spawning. These are supported local agent configuration, not core
patches. The enhanced provider omits `isolated`, uses distinct agent names to
respect self-recursion guards, and emits the real hidden yield tool so children
finish without three model reminder turns.

## Identity and aggregation findings

`getHeader().parentSession` was absent for all observed child and grandchild
sessions, both in hook metadata and persisted session headers. Parent/child
association cannot rely on that field. Child session files are stored below
the parent's session artifact directory, but parsing that path would be an
implementation-specific association, not an explicit event-contract parent ID.

Real child ask has `tool_call` and runtime `tool_execution_start`, without
matching result/end while pending. Parent `agent_end completed` can arrive
while that child question remains unresolved. Root completion must not clear
pending orange state. Native hooks observe the blocked child; they do not by
themselves provide an actionable answer UI. Root agent performed separate TUI
checks; this report claims only the print-mode evidence above.

## Retry interpretation and working fixture

Ordinary single-model loopback HTTP 503 did not emit session auto_retry events,
in worker clean print runs and root `tui_retry`. This is explainable by source:
`agent-session.ts:20633` classifies availability errors on a local model endpoint
as `local_unavailable`; the matcher at line 20556 explicitly includes 503 and
server_error, and isRetryableError does not accept that class. It is not proof
of broken hook registration. `retry.requestMaxRetries` controls provider HTTP
request attempts only, separate from the session retry budget.

Working retry case uses a documented managed profile with two loopback model
selectors. Remove modelBindings in that case's models.yml, then add:

```yaml
profiles:
  lab-retry:
    required_providers: []
    model_mapping:
      default:
        - keychron-lab/lab-transient_error
        - keychron-lab/lab-success
```

Invoke `--mpreset lab-retry` without `--model`; config.yml:

```yaml
retry:
  enabled: true
  maxRetries: 2
  baseDelayMs: 20
  requestMaxRetries: 0
fallback:
  maxAttempts: 2
```

Both selectors target `http://127.0.0.1:64329/v1`. A unique prompt hash receives
one 503 then success. Native auto_retry_start and auto_retry_end(success=true)
were received through the hook TCP stream.

## Running fixture servers

Primary server 64329 (PID 96091) remains available for root tests.
Enhanced server 49580 (PID 5363) remains available for root child TUI tests.
Do not restart either while the root is using it.

No global hook, production config, repository product source or GJC core was
modified by this worker.
