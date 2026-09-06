# GJC installer, config and autostart second audit

Audit date: 2026-09-06. Dispatch: `task_6d650a53ac47` / `ctx_fb75e13996de`. Scope was limited to the owned GJC installer/config/autostart modules and their tests. Requirements are the stable IDs from `docs/testing/gjc-requirements-matrix.md`.

## Result

The focused audit added 43 executable cases and fixed every locally or coordinator-proven defect in the owned scope. Final focused results are 95/95 on Python 3.13 and Python 3.9.6, plus focused Ruff success. Aggregate historical 298 Python and 21 Bun results were not used as proof for these boundaries.

| IDs | Expected outcome exercised | Result and preservation assertion |
|---|---|---|
| R04-R06 | Ownership, unsafe paths, private modes, immutable release conflicts, exact dry-run and transactional recovery | Fixed explicit manifest/journal validation under `python -O`; FIFO reads are nonblocking; wrong pins/schema/modes/conflicts are refused; user bytes and recovery journal remain present on refusal. |
| R05 | Write/replace/fsync ordering, journal recovery, mode and umask boundaries | Fixed private directory creation independent of umask, directory fsync after replace/unlink, recoverable fsync fault, replace rollback, modified-file refusal and exact 0600 restore modes. |
| R07 | Config corruption, permissions, private directory, partial save failure, spaces and byte-length boundary | Fixed nonblocking FIFO rejection, exact 0700 runtime requirement and ancestor-symlink refusal; existing valid config remains byte-identical across pre-replace/fsync failures. |
| R12 | Owned LaunchAgent definition, absolute interpreter, working/log paths, current+legacy conflicts, rollback and partial uninstall | Fixed fail-closed `launchctl print`, semantic definition ownership, private runtime/log dirs, log symlink refusal, directory-fsync rollback and surfaced rollback bootout failure. Existing Orca/GJC plists and loaded-state fixtures remain unchanged on refusal. |

## Added acceptance cases

1. Installer: real temporary filesystem install/rerun/uninstall, umask `000`/`777`, public managed bytes, exact manifest keys/version pin, 103/104-byte Unicode sockets, preexisting release conflict, journal corruption/recovery, injected replace and directory-fsync faults, dry-run disk snapshots, `python -O`, and FIFO timeout.
2. Config: private corrupt JSON, injected permission/open/replace/file-fsync failures, config and command paths containing spaces, Unicode socket byte length, nonprivate directory, product-ancestor symlink, and FIFO timeout.
3. Autostart: absolute interpreter, owned WorkingDirectory/log destinations, directory and log-file symlinks, current/legacy installed+loaded combinations, inspection ambiguity, modified definition preservation, compatibility upgrade/uninstall for the earlier safe generated shape without WorkingDirectory, bootstrap/bootout rollback, LaunchAgent directory-fsync recovery, and uninstall unlink failure.

## Fixed defects

1. `gjc_install.py` used optimization-removable `assert` statements for ownership validation. With `python -O`, malformed or foreign manifest/journal data could drive managed deletion. Validation is now explicit, exact and independent of optimization mode.
2. Installer/config reads could block indefinitely on a FIFO. Owned metadata/config opens now use `O_NONBLOCK`, then require a bounded regular user-owned file before parsing.
3. Installer persistence and privacy were incomplete: intermediate directories followed umask, managed file modes were ignored, manifest version/schema were under-validated, and directory entries were not fsynced. New directories are explicitly 0700, managed files/journals/locks enforce private ownership modes, and replace/unlink durability has injected-failure recovery coverage.
4. GJC autostart treated any nonzero `launchctl print` as absent, permitting an inspection-error loophole around the current/legacy Orca conflict promise. Only the known not-found exit is absence; other results are explicit failures before writes or service changes.
5. Autostart accepted relative interpreters and modified log/working paths, created loose log directories, and could hide rollback failure or retain a newly replaced plist after directory-fsync failure. The definition and directories now have explicit ownership boundaries and rollback preserves the original bytes/state or reports the exact secondary failure; the previous safe generated definition without WorkingDirectory remains upgradeable and uninstallable.

## Red and green evidence

- Local RED: `docs/testing/gjc-owned-boundaries-second-audit-red.txt` records the pre-fix command and `16 failed, 21 passed` result. The optimized-mode and FIFO red oracles were separately supplied by coordinator messages and converted to bounded regression cases.
- GREEN: `docs/testing/gjc-owned-boundaries-second-audit-green.txt` records Python 3.13 `95 passed`, Python 3.9.6 `95 passed`, Python 3.9 import success and focused Ruff success.

## Owned final hashes

```text
6e521d390dcfabf06e2bb476dac6c7c88b67d6cba869099a4d576fda0850c961  src/orca_keychron_gjc/gjc_install.py
a1a9db7a89e487f4113f1ceaccf4bcc9bf387b4a8f5024bbe0b26267253032af  src/orca_keychron_gjc/config.py
ea3c3c8c1adbbd1262193742cf3aee49232fa33a0c8732d97b101e32349ac25c  src/orca_keychron_gjc/autostart.py
77e3217f99a9df689aba6d3b84977480fb61942c8cb54ea2428305fd3a3c7635  tests/test_gjc_install.py
5286955f958ced4390f887cd543a66f7138ce840d509a1bf7a46385981a3ed5b  tests/test_gjc_install_faults.py
4549fbe9da1a018fb9cc944d2f1d9605cc883fef653e60e8d74466f6afed4f3c  tests/test_gjc_config.py
7f36d5490ec5cf601eb2282f689acfabd87c8307d1f17ed6b3bd5a3a7190289a  tests/test_gjc_autostart.py
4ffe0aa826bc220f06aa9cced0a28dc3560319337f35fa766a00799d6137d56f  tests/test_gjc_autostart_faults.py
```

## Unresolved limitations

- No real `launchctl` write or login-service activation was performed; service behavior is exercised with stateful fakes and preserved filesystem bytes only.
- Injected fsync/replace failures prove recoverability at named call boundaries, not power-loss behavior on every filesystem or hostile same-user TOCTOU replacement during mutations.
- The documented base Orca-to-GJC autostart asymmetry remains accepted scope. This audit only closes the GJC installer loophole for installed, loaded and inspection-ambiguous current/legacy Orca services.
- GJC 0.16.4 exact-version gating remains at the CLI boundary; no upstream code, provider/model account, global service, real HID device or physical keyboard was used.
