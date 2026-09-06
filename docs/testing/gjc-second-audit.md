# GJC 0.16.4 second test audit

Date: 2026-09-06 (Asia/Seoul). This report covers the requirements-driven second audit of the GJC bridge and the shared Orca/Keychron runtime. It preserves the earlier validation as historical evidence. No commit, pull request, release, global hook/service installation, real provider account call, or physical keyboard/HID operation was performed in this campaign.

**Software/package and supported actual-GJC fixture gates: PASS.** The final frozen product passes 456 Python tests on each of Python 3.9 and 3.13, 44 Bun tests, package installation and static checks. Both actual GJC experiments pass against the same frozen wheel. The final main run uses the corrected temporal assertions; the earlier mixed-time color assertion is not accepted as proof. Explicit unexecuted hardware, model, service and Linux boundaries are listed below.

## Reproducible final inputs and execution gates

The frozen wheel is `orca_keychron-0.1.2.dev1+ga1e844f34.d20260905-py3-none-any.whl`, SHA-256 `134977ddf53a54903f9af9471cac8b511605539529193bb049f5c6a1cb56e48d`. Its local path is recorded in [final-wheel.json](final-wheel.json). Product/build bytes are recorded in [final-product-hashes.json](final-product-hashes.json); test/helper/workflow bytes are recorded in [final-test-input-hashes.json](final-test-input-hashes.json). The latter was refreshed after the last test-only correction. The same product wheel is used for installed-package checks and both actual GJC experiments.

[final-gate-results.json](final-gate-results.json) contains the commands, exit codes, elapsed times and log paths. The gate uses dedicated interpreter environments and an explicit environment allowlist, avoiding concurrent mutation of the checkout's `.venv` and inherited credentials.

| Boundary | Execution and result |
|---|---|
| Python unit, component and integration suite | **456 passed on CPython 3.9.6 and 456 passed on CPython 3.13.5**, zero skips. Every final run sets `GJC_TEST_WHEEL_DIR`; the three installed-distribution cases must execute, not skip. |
| Native hook | Bun 1.4.0, `bun test tests/`: 44 tests, 163 assertions. Includes real Bun child processes and local sockets, plus generated native-event component cases. |
| Distribution | Wheel and sdist build; strict Twine metadata check; fresh full-dependency Python 3.9 installation; `uv pip check`; isolated `-I` imports and help for both packages. The installed-distribution tests also create independent non-editable, offline `--no-deps` venvs and compare every packaged Python/asset byte. |
| Static gates | Ruff 0.16.6 across the repository, `git diff --check`, and actionlint 1.7.7 on both workflows pass. Both workflows build a wheel, set the wheel-test directory, and run Python 3.9/3.13 and native hook checks. |
| Actual GJC | Unmodified `gjc/0.16.4`, isolated profile/project/session paths, actual Orca terminals and a deterministic loopback provider. Main final evidence and restart/successor final evidence both pass; proof boundaries are detailed below. |

The pre-audit baseline was **298 Python tests and 21 Bun tests**. The final suites contain **456 Python tests and 44 Bun tests**: **158 additional Python cases and 23 additional Bun cases**. Running the same Python suite on two interpreters does not double the number of tests added. [final-input-verification.json](final-input-verification.json) verifies that all **29 product/build inputs and 43 test/helper/workflow inputs** remained unchanged across the final gate, and that the wheel digest still matches.

## Coverage measurement

The parent Python process measured **81.76% → 84.57%** combined statement/branch coverage, using the same two source packages. Current statement coverage is **86.83%** and branch coverage is **77.53%**. The raw measurements are [coverage-baseline.json](coverage-baseline.json) and [coverage-final.json](coverage-final.json). The production code grew during the fixes, so both the numerator and denominator changed. These percentages exclude child CLI interpreter coverage and TypeScript execution; they are not a user-visible E2E or requirements-completeness percentage.

## Requirement coverage and defects fixed

[The requirements matrix](gjc-requirements-matrix.md) retains stable R01–R45 identifiers and maps each requirement to exact tests and proof boundaries. A passing aggregate suite is not treated as evidence for every unexecuted user interaction.

| Area | Introduced tests and observed defect corrections | Detailed evidence |
|---|---|---|
| Human priority, identity and event ordering | Exhaustive 1,956 priority subset/order permutations; ten working plus one waiting at every position; closed-child pending retention; stable slots, overflow, tombstones, stale generations and lease edges. Native regressions cover new-root admission at the 256-session cap, retaining pending requests when a nonpending record can be evicted, answer-before-decision races, reused request IDs, malformed yield and retry/cancel ordering. | [State audit](gjc-state-audit.md), [native hook audit](gjc-hook-second-audit.md), [coordinator regressions](gjc-coordinator-regressions.md) |
| Transport and persistence | Actual Unix sockets and subprocesses exercise fragmented/coalesced/malformed frames, client limits, reconnect, competing receivers, control races and storage failure. Fixed unintended UTF-16/32/BOM acceptance, blocking FIFO reads, and modification/removal of foreign paths replacing an owned endpoint. | [Transport audit](transport-audit-report.md), [state audit](gjc-state-audit.md) |
| Installation, configuration and service ownership | Adversarial file types, symlinks, permissions, interrupted transactions, ownership and optimized-interpreter subprocesses. Replaced security-relevant `assert` validation that disappeared under `python -O`; rejected FIFO configuration/manifest files without hanging; strengthened private paths and transaction durability; fixed service inspection/rollback failures and compatible older generated plist handling. Real `launchctl` activation was not performed. | [Owned-boundary audit](gjc-owned-boundaries-second-audit.md) |
| Shared hardware/input runtime | Real source-to-indicator-to-renderer composition with fake HID/navigation; shortcut modifier/release boundaries and resource failure injection. Fixed a listener retained after startup failure, accepted short HID writes, and incorrect labels for assigned slots beyond the number row. | [Shared-runtime audit](gjc-shared-runtime-second-audit.md) |
| CLI and installed product | Thirteen real CLI/package integration cases cover saved custom sockets, live/dead clear authorization, receiver crash/restart, hardware-import tripwires, installed native loader streaming, status privacy, doctor diagnostics and corruption. Plain status now visibly marks incomplete observation while retaining known waiting/failed/working priority. | [CLI/package audit](gjc-cli-package-audit.md), [coordinator regressions](gjc-coordinator-regressions.md) |

The tests include independent wrong-behavior checks: making working outrank waiting, freeing a slot without authorization, clearing both decisions after one answer, and accepting stale historical frames are rejected. Reconstructed pre-fix behavior also fails the added encoding/FIFO/ownership/cap regressions. This is targeted mutation and red/green evidence, not a claim of a repository-wide mutation score.

## Actual GJC runtime scenarios

The main runner is [experiments/gjc-e2e-audit/run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py). Its actual-GJC result is separate from `tests/e2e/test_gjc_e2e_audit.py`, which tests the runner's assertions and helpers using synthetic data. Naming a test directory `e2e` does not itself establish actual GJC execution.

The final main run **passed in 53.336 seconds** using an isolated pip-installed wheel. Its [final evidence JSON](../../experiments/gjc-e2e-audit/evidence/final.json) has SHA-256 `0c376f80a542feb12d212a187c1f4750b87a526b23e5c0e470370de5e0cb2b69`. The runner, imported fixtures, runtime components, wheel, installed hook and before/after product source hashes match the final input inventory. [The actual-runtime report](../../experiments/gjc-e2e-audit/FINAL_REPORT.md) records execution details.

| Actual-runtime case group | Verified result |
|---|---|
| Startup, connection and slots | GJC starts before the receiver; reconnect publishes state. Two independent launches occupy slots 0 and 1. Receiver restart restores those slots as unknown, then real publishers backfill them without reassignment. Killing a producer yields unknown while preserving its slot. |
| Outcomes and duplicate discovery | Actual success/failure/cancel events are observed; loading both user and project hooks creates one publisher and one launch. |
| Ten working plus one waiting | The actual native stream contains sequence 117 with ten working, one waiting and one done session, and one pending request. Replaying that **exact** captured snapshot through the installed tracker and renderer yields waiting/orange. This is explicitly `exact-snapshot-installed-product-replay`, not optical LED or a sampled live renderer observation at that instant. |
| Two child decisions | Both actual child IDs and request IDs are validated. Answering the first leaves the other child decision pending in a newer frame; answering the second resolves both, with each child consuming its own correlated answer/checkpoint. |
| Root lifecycle and cleanup | `/new` and `/resume` preserve publisher identity while changing/restoring root session identity. Explicit root exit closes its launch. All eleven owned terminals close; no owned process or Unix/TCP listener remains, and the private main-run runtime is removed. |

The restart/successor run has passed using payload extracted from the exact frozen wheel. [The report](../../experiments/gjc-successor-audit/REPORT.md) and [preserved final JSON](../../experiments/gjc-successor-audit/evidence/final.json) show launch A's actual child decision and real parent answer, explicit process closure, launch B's native `not_found` response when attempting to resume the predecessor, a distinct successor child, and successful request/checkpoint/answer validation. The fixture explicitly carries the checkpoint and answer across processes. This proves the supported successor workflow composition; it does not implement automatic durable answer recovery or prove a real model will follow the instructions.

## Test-oracle corrections and invalid attempts

The audit also tested its own assumptions. Historical failures remain linked in the component reports; they are not counted as current product failures.

| Invalid assumption | Correction |
|---|---|
| A matching historical waiting frame proves the state after an answer or `/resume`. | Those waits use the newest frame and a sequence fence. The surviving child decision is identified by its actual session ID. A separate root ask is allowed and cannot be mistaken for that child decision. |
| A historical twelve-agent frame and a later orange color for the same launch prove the same observation. | Independent review rejected this oracle. The corrected runner feeds the exact captured native snapshot through the installed tracker/renderer and binds producer, launch, sequence, agent count and pending count. This is explicitly labeled replay, not live same-frame display. A later orange frame with different counts fails the added regression; ten helper/oracle tests pass. |
| A fake monotonic baseline of 100 is portable across Python runtimes. | Apple's CPython 3.9 starts the retained timestamp callable near process zero. The test now seeds from the real baseline and advances by the requested timeout; receiver diagnostics stay enabled. This was a test-clock defect. |
| Interpreter cache files are a doctor-induced configuration mutation; generated pycache belongs in a source hash. | CLI test children disable bytecode writes, preserving the strict non-mutation assertion. Source hashes cover explicit source assets and exclude generated caches, with a regression proving real source edits still change the hash. |
| Temporary workspace setup and distribution directory contents are fixed. | Runtime setup tolerates its already-created private HOME. Twine is given only wheel/sdist archives, excluding the build tool's `.gitignore`. These harness fixes did not change or rebuild the frozen product. |

## Remaining proof boundaries

No new physical key press, optical LED check, live login-service activation, real model/provider-account run or actual Ubuntu runner execution was performed. Historical bounded device/navigation evidence remains in [gjc-hardware-validation.md](../gjc-hardware-validation.md); it must not be relabeled as a new physical E2E pass. [The Linux CI audit](gjc-linux-ci-validation.md) records static portability checks and the unavailable local Docker daemon; its provisional test/lint blockers are superseded by the final passing macOS gates.

The supported product boundaries remain explicit: GJC 0.16.4 only; native observable events cannot cover every approval UI; child questions focus the parent Orca pane rather than directly opening the child answer screen; capped observation exposes incomplete coverage; successor continuation requires the documented explicit checkpoint/answer handoff. Same-user local ownership checks are cooperative protections, not a hostile-user isolation guarantee.

## Repeat commands

Use a new output directory for a new build, a dedicated test environment with the development dependencies, and Bun 1.4.0. Do not overwrite the frozen audit wheel while reproducing its evidence.

```sh
uv build --out-dir /tmp/gjc-second-audit-repeat-dist
GJC_TEST_WHEEL_DIR=/tmp/gjc-second-audit-repeat-dist python -m pytest -q
bun test tests/
python -m ruff check .
python experiments/gjc-e2e-audit/run_audit.py --help
```

Repeat the Python gate with both 3.9 and 3.13. The actual GJC runner needs the installed GJC 0.16.4 binary and an Orca runtime; follow its README for the explicit frozen-wheel argument and isolated-run options. No command above performs global service installation or release publication.
