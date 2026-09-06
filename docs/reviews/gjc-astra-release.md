# GJC Astra release delta review

## Final review: no actionable findings

- **Scope**: `origin/main…HEAD` plus uncommitted/untracked implementation and tests, carried forward from `docs/reviews/gjc-astra-final.md` and its independent full review `gjc-astra-high.md`; merge base and HEAD `a1e844f3402b6c76dd3014719fc021cf1435a9c7` (no committed branch delta).
- **Files**: 33 prior review inputs = **25 byte-identical + 8 changed**. The requested expanded SHA256 inventory covers **49 files**; its additional 16 legacy Python files are byte-identical to HEAD/base. No new implementation/test path outside this inventory was found in Git scope discovery.
- **Findings**: **0** (critical: 0, high: 0, medium: 0). Introduced actionable functional bugs only; style, speculative impact and pre-existing behavior excluded. All four Astra and both Fable findings remain closed.
- **Validation**: final tracker/source/CLI checks passed **103/103 on Python 3.9.6 and 103/103 on Python 3.13.5** after the authorized deadline correction. An initial Python 3.9 run exposed a lease-boundary assertion failure; its reproduction and closure are recorded below.
- **Ownership**: task `task_98bbf3398ed2`, dispatch `ctx_608d44e9089a`; only this report and `gjc-astra-release-hashes.json` are workspace writes. No product/test/build edits, subworkers, HID, global install, provider requests, user-terminal control, git writes, PR or external review publication.

Review completed 2026-09-06 KST using the requested Astra/high session. Final review bytes equal the initial snapshot for 47 inputs; the two subsequently authorized tracker/test inputs received the additional exact-diff review described below. The accompanying JSON is a direct, sorted `relative/path -> sha256` mapping of all `src/**/*.py`, `src/orca_keychron_gjc/assets/*`, `tests/**/*.py`, `tests/gjc_hook.test.ts`, `pyproject.toml`, and `uv.lock`, excluding `__pycache__`. Hash equality carries prior coverage forward; it does not imply a new full review of unchanged legacy code.

## Changed inputs and impacted boundaries

| Input | Review coverage and result |
|---|---|
| `src/orca_keychron_gjc/cli.py` | Read current file and impacted parser/handlers. Canonical UUID validation at 84–93 runs during `parse_args` before connection. `clear_command` at 359–382 distinguishes typed refusal from absent launch and transport error, returns 1 for refused/not found and 0 only for confirmed clear; JSON preserves the validated response. `main` at 497–507 translates expected `OSError`/`RuntimeError` to concise `SystemExit`. Saved serve config resolution is retained. |
| `src/orca_keychron_gjc/gjc_source.py` | Read current receiver and client paths. `request_control` at 89–102 converts actual Python 3.9 `socket.timeout` on connect/send/recv to builtin `TimeoutError`. Response union validation at 113–149 permits only the typed clear refusal and preserves exact successful response/display validation. `_frame` at 266–295 serializes clear with snapshot application. `_clear_disconnected_dead_launch` at 296–320 checks live ownership as well as display connection, rejects ambiguous PID evidence, and calls `tracker.clear` only after positive absence. Inspected tracker `apply`, `disconnect`, `clear`, slot assignment, persistence and retirement callers; their bodies are unchanged. The later `_connected` correction is covered separately below. |
| `tests/test_gjc_cli.py` | Inspected canonical-ID validation, unavailable endpoint, real duplicate receiver, shared Indicator cleanup on runtime failure, saved config, and text/JSON clear rejection tests. These exercise actual parser/handler paths; runtime-failure hardware is a fake device. |
| `tests/test_gjc_source.py` | Inspected changed real-socket clear cases and exited-child fixtures, refusal preservation after lease expiry, alive-child refusal then natural child exit/reaping, EPERM/EIO/overflow/value ambiguity, invalid local PID no-probe, strict malformed rejection responses, restart/crash lock ownership and timeout assertions. No HID/global configuration is used. |
| `src/orca_keychron_gjc/gjc_tracker.py`, `tests/test_gjc_tracker.py` | Coordinator authorized one additional delta after the initial gate failure: line 187 now compares `received_at <= now < received_at + lease_seconds`. Exact diff against the captured initial bytes contains only this expression, a `math` import, and one deterministic fractional-clock regression at test lines 71–85. Examined `indicators`, `_display_row`, and source safe-clear callers: backwards clocks remain unknown, exact deadline expires, slots remain assigned, and live socket ownership still refuses clear after expiry. Both runtimes pass all 103 tracker/source/CLI cases. |
| `pyproject.toml`, `uv.lock` | Conditional ApplicationServices/Quartz `<12` applies only to Darwin with Python `<3.10`. Existing `pynput>=1.7.7,<1.8` remains. Lock graph selects PyObjC 11.1 and cp39 universal2 wheels for Python 3.9, 12.2.2 for Python >=3.10; both framework dependencies constrain their transitive Core/Cocoa/CoreText compatibly. Local installed metadata and `pip check` confirm compatibility; offline lock check passes. |

The 25 unchanged prior-scope inputs include the native hook and prompt assets, protocol, config, installer, autostart, all six changed/introduced shared-runtime modules, and their unchanged tests. The full prior review is not repeated. Changed source files were re-read in full; dependent unchanged functions were inspected for actual caller effects.

## Safe-clear and parser evidence

The independently executed source tests prove:

1. **Connected producer, including expired display lease**: `ok=false`, `cleared=false`, reason `connected`; registry bytes and retirement map are unchanged. A subsequent heartbeat on the same socket advances to `done` in the original slot. With overflow present, rejected clear leaves overflow and slot allocation intact.
2. **Disconnected alive/ambiguous PID**: owned live child yields `process_alive`; EPERM, EIO, `OverflowError`, `ValueError` and unrepresentable PID yield `process_death_unconfirmed`. Refusal preserves registry and tombstones. No ambiguous branch invokes `tracker.clear`.
3. **Disconnected positively dead PID**: after the owned child naturally exits and is reaped, the request succeeds, retires exactly that launch/producer and releases its slot. Separate multi-launch coverage proves overflow promotion occurs only after successful clear. Missing launch remains a non-mutating successful response with `cleared=false`.
4. **Strict wire parsing**: malformed keys/types, boolean-as-number substitutions, success plus refusal fields, `cleared=true` refusal, missing/wrong error code, unhashable/unknown/extra reason fields and invalid display overflow are rejected. Existing success status and success-clear shapes still work over actual sockets. Controls on producer connections remain forbidden; queued frames cannot revive retired identities.

This is local-process liveness evidence. The implementation deliberately refuses a reused/alive PID rather than guessing death; its conservative refusal is not a defect under the specified contract. Explicit producer `closed=true` retains its existing shutdown semantics.

## Previous findings: closure verification

| Prior finding | Final status and evidence |
|---|---|
| Astra #1 root session switch/fresh readonly facade | **Closed, carried forward**: hook and native fixture SHA256 exactly match the prior final review. Read `experiments/gjc-product-qa/root-switch/REPORT.md`: independent actual GJC 0.16.4 `/new`, `/resume`, `/exit` fixture-runtime evidence now exists with the identical installed hook. That is supplied runtime QA, not a new run by this reviewer. |
| Astra #2 config-created directory permissions | **Closed, carried forward**: config and tests unchanged; private `orca-keychron/gjc` leaf remains at `config.py:28–35`. Prior real private config/source round-trip evidence remains applicable. |
| Astra #3 distinct sockets writing one registry | **Closed**: lock acquisition before tracker reload remains at source 189–201. Focused source tests passed distinct-endpoint contention, persistence/retirement preservation, reload, failure and crash ownership scenarios in both Python runtimes. |
| Astra #4 serve ignoring saved custom socket | **Closed**: saved endpoint/command resolution retained; `test_serve_uses_saved_custom_socket_and_orca_command` passes on Python 3.13 and 3.9. |
| Fable #1 malformed clear ID reported as unreachable | **Closed**: invalid ID exits 2 with canonical UUID guidance before contacting the bridge. Independently invoked real Python 3.9 `-m orca_keychron_gjc clear not-a-uuid --socket <owned temporary endpoint>` and verified the existing receiver still answers. |
| Fable #2 receiver failures print traceback | **Closed**: independently invoked second real Python 3.9 `serve` against an owned temporary receiver; exit 1, concise ownership message, no `Traceback`, original receiver still answers. Focused shared-Indicator fixture proves source stop, lighting restore and device close before concise runtime error propagation. |

## Commands and observed results

CWD: `<workspace>`. Existing environments only; bytecode and pytest cache disabled.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_gjc_cli.py tests/test_gjc_source.py
PYTHONDONTWRITEBYTECODE=1 /tmp/gjc-validation.K3OypM/py39-fixed/bin/python -m pytest -q -p no:cacheprovider tests/test_gjc_cli.py tests/test_gjc_source.py
PYTHONDONTWRITEBYTECODE=1 /tmp/gjc-validation.K3OypM/py39-fixed/bin/python -m pytest -q -p no:cacheprovider tests/test_gjc_cli.py tests/test_gjc_source.py -k 'clear or ambiguous or unrepresentable or control or collision or receiver_failure or saved_custom'
PYTHONDONTWRITEBYTECODE=1 /tmp/gjc-validation.K3OypM/py39-fixed/bin/python -m pip check
uv lock --check --offline
git diff --check
# After the exact-deadline correction:
PYTHONDONTWRITEBYTECODE=1 /tmp/gjc-validation.K3OypM/py39-fixed/bin/python -m pytest -q -p no:cacheprovider tests/test_gjc_tracker.py tests/test_gjc_source.py tests/test_gjc_cli.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_gjc_tracker.py tests/test_gjc_source.py tests/test_gjc_cli.py
```

| Check | Observed result |
|---|---|
| Final Python 3.9.6 tracker/source/CLI | **103 passed in 6.84s** after the correction. |
| Final Python 3.13.5 tracker/source/CLI | **103 passed in 6.93s** after the correction. |
| Initial Python 3.13.5 CLI/source set | **83 passed in 6.89s**. |
| Python 3.9.6 CLI/source initial set | **82 passed, 1 failed in 7.66s**: lease boundary assertion before the correction, detailed below. |
| Python 3.9.6 delta/impacted-caller selection | **37 passed, 46 deselected in 2.63s**. |
| Python 3.9.6 isolated lease assertion with read-only runtime instrumentation | **1 passed in 0.05s**; captured boundary elapsed `8.0`, result false. |
| Real Python 3.9 CLI subprocess checks | Invalid UUID exits 2; duplicate serve exits 1; both have expected messages without traceback and preserve the owned live receiver. |
| Python 3.9 timeout phase injection | Connect, sendall and recv each raise the actual distinct `socket.timeout` class; each emerges as exact builtin `TimeoutError`, retaining `socket.timeout` as its cause. Actual bounded recv timeout is also covered in both runtime test sets. |
| Dependency and lock checks | `pip check`: **No broken requirements found**; `uv lock --check --offline`: **Resolved 29 packages**, exit 0. |
| Whitespace and drift | `git diff --check`: exit 0; 47 inputs unchanged from initial capture; the two authorized tracker/test changes match the reviewed correction hashes. |

The existing isolated Python 3.9 environment reports PyObjC Core/ApplicationServices/Quartz/Cocoa/CoreText **11.1**, with framework `Requires-Python >=3.9` (Core `>=3.8`) and pynput **1.7.8** requiring both frameworks `>=8.0`. Wheel-installed product metadata includes exactly the two conditional `<12` constraints. I read the validator's `pip-install-final.log` successful install and `pip-check-final.log`, and independently reran metadata inspection plus `pip check`; I did not reinstall packages or run a new build. Full tests/build remain the separate final validator's responsibility.

### Initial Python 3.9 gate failure: detected and closed

Location: `tests/test_gjc_source.py:268` asserts that `indicators(received + 8)` has expired. The initial `GjcTracker._connected` (`gjc_tracker.py:184–188`, SHA `30ee0d94db8f2f34af7a56683222acef9fffbca110cfa9bbcd293ad892a758f8`) tests `now - received_at < lease_seconds`. Actual Python 3.9 macOS monotonic values start near zero in the process; floating-point addition/subtraction can yield `7.999999999999999` for the constructed nominal eight-second boundary. The isolated test passed, and this deterministic in-memory reproduction confirmed the condition without editing files:

```python
tracker = GjcTracker(2)
tracker.apply(parse_snapshot(frame('done')), now=0.000001)
assert tracker.indicators(0.000001 + 8)[0].state == 'done'
```

Observed elapsed: `(0.000001 + 8) - 0.000001 == 7.999999999999999`; at `8.000001` seconds elapsed, the state is `unknown`. The failure is an exact-boundary numerical assertion, not a changed guard, Python exception regression, or practically delayed expiry. Although these bytes matched the prior review, the tracker is new within the full working-tree feature scope. The coordinator therefore authorized Sol to resolve this test-gate issue during this review. The final expression compares the absolute deadline directly, and the new regression uses `received_at=0.001` with `math.nextafter` to prove active immediately before expiry, unknown exactly at expiry, unknown for backwards time, and slot retention. No tolerance, sleep, or weakening of the original source assertion was added. Independent final runs pass 103 tests on each runtime. The initial failed run remains recorded above; this reviewer made no product/test edits. Coordinator was notified early of the failure, exact reproduction, and correction review.

## Proof limits and release handoff

No new full test suite, wheel build, hardware ACK/restore, navigation interaction, optical/physical keypress, real-model compliance, global installation or deployment was performed here. Supplied root-switch runtime QA and separately verified hardware ACK/restore/navigation remain separate evidence; optical output, physical keypress and real LLM compliance are explicit limits, not introduced bugs. No external review publication was attempted.

Next gate action: compare `gjc-astra-release-hashes.json` to the validator/release inputs; any changed byte or missing/new inventory path requires a corresponding delta review. Review is clean under the requested introduced-functional-bug policy, with the detected test-gate issue fixed and its historical failure retained.

Final inventory captured: 2026-09-05T19:05:22.803608+00:00.
