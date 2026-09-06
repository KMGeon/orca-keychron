# GJC 0.16.4 product integration QA

Verdict: **PASS** on the final clean runtime `/tmp/gjc-product-qa-final-c30205c0352c`. No product defect was found in the bounded cases. The machine-readable evidence summary is [`evidence/verdicts.json`](evidence/verdicts.json).

## Boundary and provenance

- Installed the actual product hook from `src/orca_keychron_gjc/assets/gjc_hook.ts` into explicit temporary `agent_dir` values. The installed SHA-256 `d1f41261...6211b` matched the product source.
- Ran unmodified installed GJC `0.16.4` directly in Orca-owned fixture terminals; no wrapper was necessary for hook discovery or registration.
- Started actual `GjcStatusSource` with a temporary socket and registry. The harness monkeypatch only observed successfully parsed snapshots and retained the product wire fields; it did not replace protocol parsing, tracking, or rendering.
- The provider bound to loopback and used only the synthetic `product-qa/fixture` model. No real model, global GJC profile, global product config, Keychron HID, user terminal, commit, or product source/test edit was used.
- Product source hashes were recorded before and after the final run and were identical; all hashes are in `evidence/verdicts.json`.

## Executed cases

| Case | Actual evidence | Result |
|---|---|---|
| Ordinary launch and slots | Two direct GJC launches registered as `5aa5803c...` slot 0 and `02c2cca1...` slot 1, both `done` | PASS |
| Receiver restart | With generation 1 stopped, registry reported the same slots as `unknown`/disconnected; generation 2 received new snapshots and restored both to `done`/connected without renumbering | PASS |
| Producer disconnect | Exact owned PID for slot 0 was killed after command verification; slot 0 became `unknown`/disconnected while slot 1 stayed `done`/connected | PASS |
| Root outcomes | Actual wire states remained distinct: success `done`, synthetic provider failure `failed`, and Ctrl-C interruption `cancelled`; cancelled aggregate conservatively rendered `unknown` | PASS |
| 10 working + pending human | Launch `f8923a9d...`, slot 5, wire sequence 123 had 10 `working`, 1 `waiting` with one pending decision, and 1 completed fanout session; one launch held all 12 sessions | PASS |
| Orange renderer | The same launch aggregated to `waiting`, `agentCount=12`, `pendingRequests=1`; product `render_zone` returned `[21,255,255]` and `isOrange=true` | PASS |
| Two decisions | `req_1` used its actual child ID and validated correlation, answer, and checkpoint; while `req_2` remained, the launch stayed `waiting` with pending count 2. `req_2` then validated independently, both children consumed their answers, and the launch finished `done` with zero pending | PASS |
| Duplicate discovery | The same product hook was installed in isolated user and project locations; the direct launch emitted exactly one unique launch/group | PASS |

## Content-free evidence

The final wire log contained 662 parsed snapshot observations across receiver generations 1 and 2. Recorded session fields were only `sessionId`, `role`, `state`, `pendingAsks`, and `pendingDecisions`; no prompt, tool, answer, or message content was copied into the evidence. Provider metadata recorded only scenario/event booleans and validation results, including both `actual_child_id_used=true` resume events and both `correlation_valid=true`, `answer_valid=true`, `checkpoint_valid=true` consumption events.

## Reproduction and cleanup

Use [`README.md`](README.md) with a fresh `/tmp/gjc-product-qa-<run>` runtime. `harness.py prepare` creates immutable per-case command/environment records, and `status`/`colors` query the actual receiver and renderer without hardware.

All terminals created for both the exploratory and final runtimes were closed by exact handle. All orphaned fixture brokers were identified by their exact temporary `agent_dir` command and stopped; `lsof` confirmed no listener remained on either owned Unix socket or provider port. Runtime directories were retained only as local synthetic evidence.

## Limits

This proves product hook installation/discovery, native lifecycle emission, content-free socket transport, receiver restart recovery, registry slot stability, child aggregation, decision correlation, and renderer mapping against a deterministic local provider. It does not prove real-model compliance, physical Keychron behavior, global installation/autostart, or compatibility beyond GJC 0.16.4.

## Root switch regression addendum

The omitted real-runtime `/new`, same-process `/resume`, and graceful `/exit` regression now passes on unmodified GJC 0.16.4. See [`root-switch/REPORT.md`](root-switch/REPORT.md) and its metadata-only [`root-switch/evidence.json`](root-switch/evidence.json); no prior evidence was changed.
