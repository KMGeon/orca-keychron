# GJC shared runtime second audit

Date: 2026-09-06 Asia/Seoul

## Outcome

Ten requirement-derived cases were added. Three owned product defects reproduced on the
pre-fix implementation and are fixed with red/green evidence. The focused owned regression
suite passes 112 tests; no real HID device, keyboard input, model/provider account, global
service, upstream GJC modification, Git write, or unrelated terminal was used.

## Requirement coverage

| Audit ID | Contract source | Added evidence | Result |
|---|---|---|---|
| GJC-STATE-PRIORITY | `gjc-bridge-contract.md` status interpretation | Actual AF_UNIX snapshot with a pending human decision renders ORANGE; incomplete `done` renders UNKNOWN, complete `done` renders GREEN, disconnect returns to UNKNOWN | Pass |
| GJC-NAV-ACTION | development ticket goal and state/rendering sections | The actual `GjcStatusSource` target pane reaches `Indicator`, `HoldSelection`, renderer, fake HID, and `OrcaWorktreeTabNavigator` | Pass |
| GJC-LIFETIME-OVERFLOW | launch lifetime and receiver/registry sections | Three real producer sockets with two slots keep `[0, 1, overflow]`; explicit `closed:true` releases slot 1 and promotes only overflow without moving slot 0 | Pass |
| GJC-HID-OWNERSHIP | cooperative HID section | A short USB write is fatal; Indicator restores lighting, stops source/listener, closes HID, and a new `DeviceOwnershipLock` acquires immediately | Fixed |
| GJC-CLI-CONFIG | socket/config and acceptance sections | Saved socket reaches status, clear, dry-run install, and doctor; partial doctor output keeps GJC/config/install/bridge/autostart dimensions distinct | Pass |

The input boundary additionally covers macOS repeated keydown before keyup, second action-target
selection only after keyup, unmapped key passthrough, extra-modifier passthrough, and native
listener initialization failure cleanup. The CLI output boundary distinguishes a real overflow
entry from an assigned slot beyond the twelve shortcut labels.

## Proven defects and fixes

1. `src/orca_keychron/digit_hold.py`: `DigitHoldListener.start()` stored the native listener only
   after `wait()`. If `start()` succeeded and `wait()` failed, `stop()` had no object to stop.
   The listener is now retained before startup and stopped/cleared on every startup failure.
2. `src/orca_keychron/keychron_hid.py`: `_write()` ignored hidapi's transferred byte count. A
   short report could be treated as a rendered frame and suppress subsequent retry. A reported
   non-complete write now raises `KeychronError`; `None` remains accepted for compatible dummy
   backends.
3. `src/orca_keychron_gjc/cli.py`: human status output called every assigned slot at index 12+
   `overflow`. It now prints `slot 13`, `slot 14`, and so on; only `slot is None` is overflow.

Exact red output is in `docs/testing/gjc-shared-runtime-second-audit-red.txt`; exact green,
focused-suite, Ruff, and whitespace-check output is in
`docs/testing/gjc-shared-runtime-second-audit-green.txt`.

## Cases added

| File | Cases |
|---|---:|
| `tests/test_digit_hold.py` | 3 |
| `tests/test_gjc_cli_faults.py` | 3 |
| `tests/test_keychron_hid_faults.py` | 2 |
| `tests/test_gjc_runtime_integration.py` | 2 |
| Total | 10 |

## Owned hashes

```text
8186e3e6bc373f7f00a71a10c8890462d8e3bee40e8ef5916fe9447c99c5666b  src/orca_keychron/digit_hold.py
beb4a0ed9342af12d6ef11ae764f39c0cf7d5677c45ca7b0dd397216f873ef7d  src/orca_keychron/keychron_hid.py
2e0a69ee9a44e8184d275713a7aef1582f8110bc7e62b091db456da5488e99ca  src/orca_keychron_gjc/cli.py
9e98ae473249873d77d8a063e562ef4cdfa41326b360f948a2eb6823dfe37bde  tests/test_digit_hold.py
a45b003aab2fca030aa1a19033f6af07ef5ba347231a65f6473b694b661c00d2  tests/test_gjc_cli_faults.py
d4c910f0be59f707f48182d5e9085ec893814e0186bf4f8bed10ed76c53923a9  tests/test_keychron_hid_faults.py
15e3b972993c03be0c7ad0cdc5ce536d53811eddbe1a1baccf61baf23f0dc27a  tests/test_gjc_runtime_integration.py
```

## Unresolved validation limits

- No physical keyboard, real USB/HID write, actual Option+number input, or visual color judgment.
- No provider/model account and no claim that model instructions enforce `read`/`yield` limits.
- No live Python 3.9 interpreter was available; Ruff passed with `target-version = py39`, and the
  changes use syntax/imports compatible with the repository's existing Python 3.9 boundary.
- The coordinator-owned real CLI subprocess integration suite was intentionally not duplicated.
- Cooperative locking still excludes only processes that use the same lock, as the contract says.
