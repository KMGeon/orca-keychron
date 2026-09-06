# GJC bridge final delta review (Fable 5.1 high)

## Final review: no actionable findings

- **Scope**: prior independent review `docs/reviews/gjc-fable-high.md` (its final hash table) plus the exact delta that landed afterwards and the callers that delta touches. Branch `orca-version-check`, `origin/main` merge base and HEAD both `a1e844f3402b6c76dd3014719fc021cf1435a9c7`, so the whole introduced implementation is working-tree scope (modified + untracked).
- **Files**: 49 product/test/build inputs hashed in `docs/reviews/gjc-fable-release-hashes.json`. 20 are byte-identical to the prior Fable final table, 7 changed (listed below), 22 were outside the prior table: 17 tracked files identical to HEAD (not part of the change), 5 shared-runtime test files covered by `docs/reviews/gjc-shared-runtime-fable.md`, plus the new `uv.lock`.
- **Findings**: 0 (critical: 0, high: 0, medium: 0). Filter: introduced, reproducible, actionable functional bugs only; style, nits, pre-existing issues and explicit limits (optical/physical key press, real-LLM compliance) excluded.
- **Prior findings**: both Fable findings and all four Astra findings are closed (evidence below).
- **Ownership**: this reviewer wrote only `docs/reviews/gjc-fable-release.md` and `docs/reviews/gjc-fable-release-hashes.json`. No product/test/build edits, no subworkers, no HID access, no global install, no provider/network requests, no user terminals, no git writes. Task `task_fc5a79866a6b`, dispatch `ctx_2e8cda2a693c`.
- **Reviewer model**: harness reports Claude Fable 5.1 (`claude-fable-5-1`); not independently verified.

## Delta since the prior Fable review (exact changed files)

| File | What changed | Review result |
|---|---|---|
| `src/orca_keychron_gjc/cli.py` | `canonical_launch_id` argparse type (`:84-93`) applied to `clear launch_id` (`:154-157`); `clear_command` prints the typed refusal reason and preservation notice, exit 1 on refusal / not found (`:359-382`); `main()` now maps `OSError` and `RuntimeError` to a one-line `SystemExit` (`:497-507`). | Closes Fable #1 and #2. Invalid or uppercase UUIDs exit 2 with usage text before any socket connect; refusal reason mapping is total because `request_control` only admits the three known reasons. |
| `src/orca_keychron_gjc/gjc_source.py` | `request_control` normalizes `socket.timeout` to builtin `TimeoutError` around connect/send and every `recv` (`:89-103`); strict typed refusal validation (`CLEAR_REFUSAL_REASONS`, `:30-32`, `:113-132`); receiver `_frame` emits `ok:false, cleared:false, error:{code:"clear_refused", reason}` (`:272-279`); new `_clear_disconnected_dead_launch` guard (`:296-320`). | Guard order: launch missing → no-op `cleared:false, ok:true`; `connected` (lease-live) **or** producer still in `_owners` → `connected`; PID outside `1..2^31-1` → `process_death_unconfirmed`; `os.kill(pid, 0)` → `ProcessLookupError`/`ESRCH` clears, any other `OSError` (incl. `EPERM`) / `OverflowError` / `ValueError` → `process_death_unconfirmed`, success → `process_alive`. Runs on the receiver thread, so it is serialized with producer frames; refusal paths never call `tracker.clear`, so no retire, no `_persist`, no slot reassignment. |
| `src/orca_keychron_gjc/gjc_tracker.py` | One-line lease deadline change in `_connected` (`:187`): `0 <= now - received_at < lease` → `received_at <= now < received_at + lease`. Landed during this review (coordinator notice "Tracker correction landed"). | Same semantics with absolute bounds; avoids the floating-point cancellation where `deadline - received_at < lease` while `now < deadline`. Callers: `indicators`, `_display_row` (hence `status` and the clear guard's `connected` check). Covered by `test_fractional_lease_deadline_uses_absolute_bounds`. |
| `pyproject.toml` | Adds `pyobjc-framework-ApplicationServices<12` and `pyobjc-framework-Quartz<12` only for `sys_platform == 'darwin' and python_version < '3.10'`. | On 3.10+ nothing changes (pynput pulls pyobjc 12.x itself). On 3.9 the lock resolves pyobjc-core / ApplicationServices / Quartz 11.1; `uv lock --check --offline` passes; an actual offline 3.9.6 install succeeded (see checks) and `import hid, pynput, Quartz, ApplicationServices` works. |
| `tests/test_gjc_cli.py` | New tests for invalid-UUID exit 2, unreachable bridge message, serve collision bounded error, run receiver failure bounded error after cleanup, live-producer refusal (text and `--json`). | Read; behaviour independently reproduced through the real console script below. |
| `tests/test_gjc_source.py` | New tests: live refusal after lease expiry preserves heartbeat, disconnected-but-alive child clears only after exit, ambiguous PID probes (`EPERM`, `EIO`, `OverflowError`, `ValueError`) refuse without mutation, unrepresentable PID never probed, strict client rejection of 11 malformed refusal shapes. | Read; the receiver-side and client-side behaviour matches the contract text in `docs/gjc-bridge-contract.md:64-66`. |
| `tests/test_gjc_tracker.py` | Adds `import math` and `test_fractional_lease_deadline_uses_absolute_bounds`. | Asserts connected one ulp before the deadline, unknown at the deadline, unknown for a clock before `received_at`. |

`docs/gjc-bridge-contract.md` also changed (documentation of the above); not a product input.

`src/orca_keychron_gjc/assets/gjc_hook.ts`, `config.py`, `gjc_protocol.py`, `gjc_install.py`, `autostart.py`, all `src/orca_keychron/*` and the other GJC tests are byte-identical to the prior Fable final table, so the prior review's conclusions on hook/event contract, tracker aggregation, receiver bounds, installer and wheel packaging carry forward unchanged.

## Questions the task asked, with evidence

- **Live/ambiguous refusal does not retire the producer or move slots.** Refusal branches in `_clear_disconnected_dead_launch` return before `tracker.clear`; `tracker.clear` is the only path that writes `_retired` for a control. Reproduced end-to-end (console script, both interpreters): after `connected` and `process_alive` refusals the registry bytes are unchanged, `status --json` slots are identical, and a later heartbeat (new connection, same producer, higher sequence) is accepted and shows `done` in the same slot.
- **Real dead-process reclamation works.** A real child Python process registered as the launch PID: while alive and disconnected → `process_alive`, exit 1; after `stdin` close and `wait()` → `Cleared GJC launch`, exit 0; the launch disappears from status, the remaining launch keeps its slot, and a resurrected snapshot for the retired launch id is ignored (tombstone holds). Also `test_disconnected_owned_child_only_clears_after_exit`.
- **No control-parser compatibility hole.** `_control` (`gjc_source.py:61-72`) is byte-identical to the prior review: exact key set, `version` must be `int` 1, `type` must be `control`, `command` in `{status, clear}`, `launchId` canonical UUID only for `clear`. Producer connections still cannot send controls (`:269-270`), one control per connection (`:335-338`). The response validator requires the exact field set per success/refusal, and refusal is only accepted for `clear` with `cleared:false`, `code == "clear_refused"` and a known reason. The hook (`gjc_hook.ts`, unchanged) never sends controls, and `request_control` is the only client in the tree.
- **Python 3.9 handles the exceptions.** Ran the GJC test suite (179 tests) and the shared-runtime tests (72) under a real CPython 3.9.6 offline venv built from `uv.lock`: all pass, including `test_control_timeout_is_bounded` asserting `type(raised.value) is TimeoutError` (on 3.9 `socket.timeout` is not `TimeoutError`, so the normalization is exercised). `ast.parse(..., feature_version=(3, 9))` accepts every `src/**` and `tests/**` file; grep for 3.10+ stdlib APIs found none; all annotation-only unions sit under `from __future__ import annotations`.
- **Dependencies remain supported.** `uv lock --check --offline` resolves; lock pins pyobjc 11.1 for `<3.10` and 12.2.2 for `>=3.10`; `hidapi 0.15.0`, `pynput 1.7.8` install on 3.9.6 offline. Wheel packaging lines (`package-data`, entry points) are unchanged from the prior review where the wheel was inspected.

## Prior findings: closure evidence

| Finding | Status | Evidence |
|---|---|---|
| Fable #1 `clear` reports invalid launch id as unreachable | **Closed** | `canonical_launch_id` rejects at argparse (`cli.py:84-93`); console script: `clear not-a-uuid` and an uppercase UUID both exit 2 with "launch ID must be a canonical UUID", bridge untouched. |
| Fable #2 receiver `RuntimeError` surfaces as traceback | **Closed** | `main()` maps `OSError`/`RuntimeError` (`cli.py:499-507`). Console script: second `serve` on the same socket → exit 1, "Another GJC receiver already owns this socket", no traceback, live bridge still answers; second `serve` on a different socket with the same registry → "already owns this registry", no stray socket left. `test_run_receiver_failure_is_a_bounded_cli_error_after_cleanup` covers the `run` path with device restore. |
| Astra #1 fresh readonly facade / root switch | **Closed** (carried) | `gjc_hook.ts` and `tests/gjc_hook.test.ts` unchanged since `gjc-astra-final.md`; runtime `/new`, `/resume`, `/exit` QA at `experiments/gjc-product-qa/root-switch/REPORT.md` per task brief. |
| Astra #2 config directory permissions | **Closed** (carried) | `config.py` unchanged since the Astra final audit. |
| Astra #3 distinct sockets sharing one registry | **Closed** | Registry sidecar lock unchanged (`gjc_source.py:189-198`); reproduced via console script above. |
| Astra #4 `serve` ignores saved socket | **Closed** (carried) | `_add_orca_option(serve, saved=True)` and `serve_command` config resolution unchanged (`cli.py:147, 297-307`). |

## Checks run (focused, bounded)

CWD `<workspace>`. Temp sockets/registries under `/tmp/g-e2e-*`, `/tmp/gjc-*` only; child processes were short-lived Python subprocesses.

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_gjc_source.py tests/test_gjc_cli.py tests/test_gjc_protocol.py tests/test_gjc_tracker.py` (3.13.5) | 126 passed |
| `.venv/bin/python -m pytest -q tests/test_gjc_tracker.py tests/test_gjc_source.py` after the tracker deadline delta landed (3.13.5 and 3.9.6) | 73 passed / 73 passed |
| `venv39/bin/python -m pytest -q -p no:cacheprovider tests/test_gjc_*.py` (CPython 3.9.6, offline venv from `uv.lock`) | 179 passed |
| shared-runtime tests `test_device_lock, test_digit_hold, test_indicator, test_keychron_hid, test_rendering` (3.13.5 / 3.9.6) | 72 passed / 72 passed |
| `uv venv --python /usr/bin/python3 --offline` + `uv pip install --offline pytest -e .` | Success: hidapi 0.15.0, pynput 1.7.8, pyobjc-core 11.1, Quartz 11.1 |
| `uv lock --check --offline` | Resolved 29 packages, lock up to date |
| `.venv/bin/ruff check --no-cache src tests` | All checks passed |
| `ast.parse(feature_version=(3, 9))` over `src/**/*.py`, `tests/**/*.py` | No syntax above 3.9 |
| Console-script E2E (`orca-keychron-gjc serve/status/clear` as real subprocesses, real producer sockets, real child PID), run with both `.venv/bin` (3.13.5) and `venv39/bin` (3.9.6) | All steps passed on both: invalid/uppercase UUID exit 2; serve socket/registry collisions concise; connected refusal; EOF + alive refusal; slots preserved; heartbeat after refusal; dead PID cleared; not-found exit 1; tombstone holds; unreachable message; serve exits 0 on SIGTERM and unlinks its socket |

Not repeated here: full suite and wheel build (final validator), hardware ACK/restore and target navigation (verified separately per task brief), bun hook tests (hook and test file unchanged since the prior run of 21 passing).

## Not flagged (design choices / below the bar / carried from prior)

- A zombie (exited, unreaped) GJC process answers `os.kill(pid, 0)` and is refused as `process_alive`; PID reuse likewise refuses. Both are the intended conservative "positively dead" policy (contract `:64`), not bugs.
- `clear_command` still folds a malformed server response (`GjcProtocolError`, a `ValueError`) into the "not reachable" message. Only reachable with a non-package server; same behaviour as in the prior review, below the bar.
- Prior "not flagged" items (per-heartbeat `_persist`, unbounded `_retired` until 65536, `PI_CODING_AGENT_DIR` fallback, `maintenance` stop reason, `overflow` label past 12 LEDs) are unchanged and remain unflagged.

## Coverage statement

Coverage = prior Fable final hash table (20 files byte-identical, conclusions carried) + full read of the 3 changed product files and 3 changed test files + impacted callers (`Indicator.run` start/stop path, `_serve`, `main()`, `GjcTracker.status/indicators/clear/disconnect`, `_control`, `request_control`) + `pyproject.toml`/`uv.lock` dependency resolution on a real 3.9 interpreter. The tracker deadline correction that landed mid-review is included; `gjc_tracker.py` was re-read after the coordinator notice and the machine hash file reflects the settled bytes. Coordinator can detect drift by re-hashing against `docs/reviews/gjc-fable-release-hashes.json` (`vs_prior` marks each file as `same`/`changed` relative to the prior Fable table, or `not_in_prior_table`).
