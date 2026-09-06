# Shared runtime review (first pass): no actionable findings

- **Scope**: `main` (merge base `a1e844f`) …HEAD + uncommitted. HEAD equals the merge base, so the entire scope is the working tree.
- **Files reviewed**: `src/orca_keychron/{indicator,models,rendering,digit_hold,keychron_hid,device_lock}.py`, `tests/{test_indicator,test_rendering,test_digit_hold,test_keychron_hid,test_device_lock}.py` (6 source, 5 test)
- **Callers inspected**: `src/orca_keychron/cli.py` (probe/run/setup/preview/main), `orca_navigation.py`, `orca_status.py`, `worktree_tracker.py`, `config.py`, `src/orca_keychron_gjc/cli.py` (setup/run/_serve/main), `gjc_source.py` (start/stop/indicators/_cleanup), `gjc_tracker.py` (GjcIndicator/indicators)
- **Filter**: introduced bugs only (style/nits/pre-existing/speculative ignored), per `~/.agents/skills/f-review/SKILL.md`
- **Reviewer model**: the runtime system prompt identifies this session as Claude Fable 5.1 (`claude-fable-5-1`). This is the value reported by the harness, not independently verified.
- **Date**: 2026-09-06

No issues met the bar for flagging. Ship-check clean under this policy for the shared runtime files.

## Verification performed

- Ran `uv run --no-sync pytest` over `test_digit_hold, test_indicator, test_keychron_hid, test_rendering, test_device_lock, test_worktree_tracker, test_orca_navigation, test_orca_status, test_cli`: **104 passed** in 1.26s. This covers and exceeds the "72 focused tests" reported by the production worker; that claim is consistent with what I observed.
- `ruff check` on the six source files and five test files: all checks passed.
- Tests never touch real HID or global config: `test_keychron_hid.py` has an autouse fixture patching `device_lock._default_lock_path` to `tmp_path`, `test_device_lock.py` patches the same in-process and in spawned children, and HID is a `FakeHid` backend throughout.

## Areas the coordinator asked about, with what was checked

1. **Lifecycle cleanup / lighting restoration** (`indicator.py:184-203`). Order is listener.stop → restore_lighting (if configured) → device.close → source.stop (only if `start()` was reached) → poll executor shutdown. Each step is in its own `try/finally`, so a failing `source.stop()` or a hanging receiver join cannot skip lighting restore or the HID close. `test_gjc_runtime_failure_always_closes_source_and_device` exercises start/indicators/stop failures and asserts `device.closed` before `stop()` runs. In orca mode the cleanup is byte-for-byte the HEAD sequence plus the guarded `source.stop()` no-op.
2. **Cross-process HID locking** (`device_lock.py`, `keychron_hid.py:67-108`). Lock is acquired before `load_hid()` and enumeration, released in `close()` via `finally`, and released on every constructor failure path through the `except BaseException` block. `flock` on a private `~/.orca-keychron/device.lock`; the file is never unlinked so contenders share the inode. The lock directory is distinct from the config directory (`~/Library/Application Support/orca-keychron` on macOS, `$XDG_CONFIG_HOME/orca-keychron` elsewhere), so existing installs with a 0o755 config dir are not rejected. Real two-process contention, SIGKILL release, symlink/hardlink/FIFO/foreign-owner rejection, and post-flock inode replacement are all covered by `test_device_lock.py` and pass on this macOS host. Every in-repo `KeychronDevice(...)` call site (orca cli ×3, gjc cli ×1, `Indicator.run`) opens at most one device per process and closes it in `finally`.
3. **Generic `DisplayIndicator` compatibility** (`models.py:9-24`). `HoldSelection.set_indicators` uses only `slot`/`target_pane_keys`; `render_zone` uses only `slot`/`state`; the `Indicator` log signature uses `slot/state/identity_label/agent_count`. `WorktreeIndicator` gains `identity_label`; `GjcIndicator` (`gjc_tracker.py:25-36`) provides all five members. `set_worktrees` is retained as an alias, and `Indicator(...)` only adds a trailing keyword argument, so `cli.run_command` is unchanged.
4. **Navigation target correctness**. Orca path unchanged (`tracker.update` → `set_indicators` → `pop_ready` → `OrcaWorktreeTabNavigator.open`). GJC path: `GjcTracker.indicators` emits `(root.pane_key,)` per slot, and the navigator still matches `tabId:leafId` against `orca terminal list --json` with `connected is True`. The new `_ready` invalidation in `set_indicators` (`digit_hold.py:64-67`) mirrors the pre-existing held-path guard in `pop_ready` and only drops a press whose target pane vanished before dispatch.
5. **Existing Orca behavior regressions**. Orca-mode loop body is semantically identical to HEAD: the snapshot future is consumed on the main thread, `set_worktrees([])` plus `source_available=False` on `OrcaStatusError`, one in-flight request at most, 10s health check, OFF zone when unavailable. The signature/print block moved after the poll-submit but is gated on `refreshed`, which is only true after a successful tracker update in orca mode. `render_zone` adds a `slot < 0` guard and three GJC-only colors; all previously handled states map to the same colors.

## Things deliberately not flagged

- `KeychronDevice.__init__` now lets an `OSError` from a candidate handle's `close()` propagate instead of suppressing it. This is explicit (comment at `keychron_hid.py:91-92`, test `test_no_responding_interface_releases_lock[close]` expects `OSError`), and neither `hidapi` backend raises from `close()` in practice.
- In GJC mode a dead receiver thread surfaces as an uncaught `RuntimeError` from `source.indicators()`; the message instructs a restart and the cleanup chain still restores lighting. Design choice, not a defect.
- `device_lock.py` imports `fcntl` at module import, which would break `keychron_hid` on Windows. `pyproject.toml` declares only `Operating System :: MacOS` and the rest of the runtime already depends on macOS/Linux-only pieces, so this is out of the supported matrix.
- `PAUSED`/`CANCELLED` colors in `rendering.py` are unreachable from the current `GjcTracker` aggregation (those states fold into `unknown`). Dead branches, not a bug.
- Nothing in the new GJC package was reviewed for introduced bugs beyond what the shared runtime calls; that is the separate final GJC review.
