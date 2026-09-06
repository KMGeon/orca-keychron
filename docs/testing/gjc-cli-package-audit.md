# CLI process and installed distribution audit

The second audit adds thirteen integration cases under `tests/integration/`. Every case uses private temporary paths and owned subprocesses. `tests/integration/conftest.py` closes clients, waits for processes, closes pipes/log files and removes its temporary directories in fixture finalizers.

## Requirements and actual boundaries

| Requirements | Test | Boundary / assertion |
|---|---|---|
| R08, R31, R33, R34, R36 | `test_cli_crash_restart_preserves_slots_then_reclaims_only_dead_launch` | Real CLI receiver process, AF_UNIX producer sockets, registry, SIGKILL and restart. Two launches retain their distinct slots; live and disconnected-but-alive clear are refused; an actual terminated child can be cleared without moving its neighbor. |
| R08 | `test_saved_socket_with_spaces_and_nondefault_zone_works_in_real_cli` | Real CLI `serve` and `status` consume saved custom configuration without socket overrides. No default endpoint is created. |
| R09, R29, R33 | `test_cli_errors_do_not_damage_live_receiver_and_corrupt_registry_is_not_empty` | Invalid clear UUID and competing server produce errors while the first receiver stays usable. Corrupt offline registry fails visibly rather than claiming an empty healthy status. |
| R10 | `test_serve_and_status_never_load_hardware_or_start_external_commands` | Real child interpreter enables an audit hook that records and rejects HID/input imports and external commands. Receiver and status still process a real frame and exit cleanly, without triggering the guard. |
| R07, R11 | `test_wheel_contains_both_commands_and_exact_current_assets` | Wheel installed offline into a fresh non-editable venv with no checkout PYTHONPATH. Both console entrypoints execute; every Python source and managed asset matches exact current bytes; imports resolve inside the new venv. |
| R18, R36, R39 | `test_installed_cli_preserves_human_priority_and_rejects_live_clear` | Installed CLI receiver sees root done, ten working children and one waiting child. Waiting wins; live clear refuses; actual OS death permits clear. |
| R03, R06, R11, R25 | `test_installed_managed_loader_executes_and_streams_to_installed_receiver` | Installed CLI dry-run creates no agent directory; actual install generates a loader imported by Bun; synthetic loader-shaped events cross the real Unix receiver, registry and status CLI. Question/option sentinels are absent from persisted/display data. Explicit shutdown flush removes the launch; uninstall removes the owned loader. |

The first package candidate passed six cases before the receiver-only guard was added; the four CLI process cases then passed. Final frozen-wheel command/results are recorded by the coordinator in `gjc-second-audit.md`.

```bash
uv build --wheel --out-dir /tmp/gjc-wheel
GJC_TEST_WHEEL_DIR=/tmp/gjc-wheel uv run --extra dev pytest -q tests/integration
```

Without `GJC_TEST_WHEEL_DIR`, the three distribution cases explicitly skip. Both pull-request and main-release CI now build a wheel and set this variable for Python 3.9 and 3.13. Bun is required for the installed TypeScript loader case and is installed by those workflows. Native hook tests are also included in CI. A default `pytest` run with skips must not be reported as the installed-package gate.

The thirteenth case, `test_plain_live_status_marks_incomplete_coverage_until_complete_followup`, adds actual receiver-to-plain-CLI coverage for R38/R39: incomplete working retains working but visibly marks incomplete observation; a newer complete frame removes the marker. Its original implementation failed and the marker fix is covered by the coordinator follow-up report.

## Diagnostic CLI extension

`tests/integration/test_gjc_doctor_process.py` adds five passing real CLI cases (three version parameters and two lifecycle/error cases): exact supported version, unsupported version, nonzero version-command exit; absent configuration/hook/bridge without mutation; saved custom endpoint with a healthy installed hook and live receiver; a user-edited hook reported unhealthy while the receiver remains healthy; explicit endpoint override reported unreachable without affecting the real server; corrupt config refused without rewriting it. These cover R01, R08 and R09. The GJC version and launchctl commands are test-owned stubs, so this is CLI composition evidence, not an actual GJC or login-service run. The focused command passed **5 in 3.46s**; Ruff passed.

## Limits

The offline `--no-deps` wheel installation isolates the stdlib transport/CLI payload; dependency resolution is a separate final install check. The installer test uses a version-only GJC stub and synthetic hook callback contexts. Actual GJC discovery, children, questions and lifecycle are covered by the separate actual-GJC E2E runner, not by this test. These cases never open HID, press keys, mutate login services or call a real model/provider account. Parent-process coverage does not automatically trace the child CLI interpreters.
