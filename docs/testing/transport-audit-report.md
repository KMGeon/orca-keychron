# Second transport/source audit — 2026-09-06

Scope: `src/orca_keychron_gjc/gjc_source.py`, existing `tests/test_gjc_source.py` (read and executed, unchanged), and new `tests/test_gjc_transport_faults.py`. The shared checkout and all other owners' files were preserved. No upstream GJC changes, git/PR writes, provider accounts, HID calls, global services, or unrelated terminals were used.

## Outcome

Added **30 parametrized cases**; **83 focused tests passed** (30 new + 53 existing) on Python 3.13.5. Ruff passed for all three owned paths. A separate real AF_UNIX smoke ran on **system Python 3.9.6**, covering rejection, continuation, status, socket chmod, cleanup, and persisted restart. This is not the full pytest suite on Python 3.9: its system environment has no pytest.

Two source defects were fixed, with six clean regression failures against the preserved original source:

1. `json.loads(bytes)` autodetected UTF-16/32. A non-UTF-8 producer frame could mutate the registry, and a non-UTF-8 control reply could pass validation. `_decode` now decodes strict UTF-8 before parsing JSON, matching the JSON Lines transport. Tests cover both encodings on both directions and normal producer continuation after rejection.
2. `start()` adopted whatever leaf existed after `bind()`: a replacement regular file or symlink could be chmoded and later removed by cleanup. The post-bind leaf must now be a user-owned socket before its inode is adopted, and chmod does not follow symlinks. Both deterministic replacement tests fail the original code and preserve the replacement and target with the fix.

## Requirement mapping

The contracts have section names rather than stable requirement IDs; these audit-local IDs map directly to those sections.

| ID | Contract / expected outcome | New cases and evidence |
| --- | --- | --- |
| TR-W1 | Bridge `Wire protocol v1`: bounded JSON Lines snapshots | 6 empty/invalid UTF-8/JSON/control-shape cases; 2 UTF-16/32 producer rejections; fragmented multibyte UTF-8 plus coalesced newer/stale full snapshots; exact 512 KiB and one-byte-over frames. Bad input cannot register a launch; unrelated valid traffic continues. |
| TR-I1 | Bridge `Receiver and registry`: stable identity, old sequence cannot replace latest, independent roots | Identity switch drops offender without changing the other root; duplicate reconnect EOF preserves current owner; newer replacement survives old peer EOF and accepts another heartbeat. Slot remains stable. |
| TR-L1 | Ticket `launch and lifetime`, bridge `Receiver and registry`: EOF/lease differs from death, clear is serialized | New Event-gated dead-PID probe versus queued reconnect proves successful clear tombstone wins and the queued old identity cannot resurrect; a fresh launch can use the released slot. Existing focused tests exercise real owned child exit, connected/lease-expired refusal, ambiguous PID refusal, EOF and slot retention. |
| TR-C1 | Bridge `Python API / gjc_source.py`: bounded clients/buffers, stopped thread | Injected clock and actual two-client cap reject the third connection, expire partial-frame stalls exactly at timeout and then serve controls. Storage failure reaches all foreground surfaces, closes thread/sockets/locks, preserves committed registry and restarts to unknown then live state. |
| TR-R1 | Bridge `Receiver and registry`: strict control success/refusal schemas | 2 UTF-16/32 response rejections; 6 negative/status-versus-clear shape cases; exact control byte cap and one byte over. Existing malformed rejection matrix also executes. |
| TR-O1 | Ticket `socket and configuration`, bridge `gjc_source.py`: ownership and safe paths | 2 post-bind leaf replacements; actual subprocess collisions for same socket with separate registry and shared registry with separate socket. Owner registry bytes and subsequent heartbeat remain valid. Existing unsafe lock/symlink, stale socket, restart and replacement cleanup cases also execute. |

## Commands and artifacts

Green:

```sh
.venv/bin/pytest -q tests/test_gjc_transport_faults.py tests/test_gjc_source.py
.venv/bin/ruff check src/orca_keychron_gjc/gjc_source.py tests/test_gjc_source.py tests/test_gjc_transport_faults.py
```

Artifacts: `transport-audit-green.txt` (83 passed), `transport-audit-lint.txt`, `transport-audit-python39.txt`, `transport-audit-source.patch`, `transport-audit-before.sha256`, and `transport-audit-owned.sha256` alongside this report.

Clean red, loading the old module only into the test process (does not swap shared working files):

```sh
.venv/bin/python - <<'PY'
import sys
import types
from pathlib import Path
import pytest
import orca_keychron_gjc
name = 'orca_keychron_gjc.gjc_source'
module = types.ModuleType(name)
module.__file__ = str(Path('docs/testing/transport-audit-source-before.txt').resolve())
sys.modules[name] = module
orca_keychron_gjc.gjc_source = module
exec(compile(Path(module.__file__).read_text(), module.__file__, 'exec'), module.__dict__)
raise SystemExit(pytest.main(['-q', 'tests/test_gjc_transport_faults.py', '-k',
    'non_utf8 or bind_leaf_replacement']))
PY
```

`transport-audit-regressions-red.txt` records **6 failed, 21 deselected** before the last three non-regression cases were added. Re-running now selects the same six regressions with 24 deselected. The initial exploratory `transport-audit-red.txt` also contains a test-side synchronization mistake: EOF was assumed to imply tracker disconnect had already run. The corrected test uses a processed control response as a receiver barrier. A later test assertion was corrected because persisted display rows are deliberately always unknown/disconnected; disconnect must preserve those bytes. Neither was reported as a product defect.

## Lifetime, bounds and remaining limits

- Code uses 32 clients, 512 KiB frame bytes, 64 KiB read/write chunks, 10-second inactivity timeout, and 32 MiB response cap. Inbound buffering can transiently hold one extra read chunk before validation. Response allocation precedes the response-size check. The conservative bound from client count times response cap alone is approximately 1 GiB of retained response bytes, in addition to input buffers and temporary serialization/copy allocations; schema bounds constrain actual realizable replies further. This audit did not establish a lower memory budget or measure peak resident memory. Partial-input stalls were exercised; a saturated non-reading control-output peer was not separately forced.
- Connection replacement guards the owner identity before dropping the old socket. The receiver is the serialization boundary for producer applies and clear; injected Events establish ordering without sleeps or assumptions about kernel packetization. The new tests use queues/Events for processing completion and an injected source clock for expiration. Existing source tests retain their historical polling helpers.
- Sidecar `flock` ownership is cooperative. A same-UID actor can replace the lock inode; these tests prove normal process contention, not exclusion of a malicious same-UID filesystem writer. Post-bind type validation and no-follow chmod close the reproduced replacement window. They are not a proof of atomic path safety across every lstat/chmod/unlink race, including replacement by another socket inode between bind and the first lstat. Eliminating those stronger races would require a separately designed ownership/path protocol; it is not claimed here.
- Python 3.9.6 real runtime smoke passed, but the full new pytest matrix ran under Python 3.13.5. No Linux runtime, real GJC/provider, physical key input, visual LED verification, or live HID behavior was tested by this worker. Protocol/tracker implementations were read, not modified; no independently proven protocol/tracker defect was identified.

All owned subprocesses are bounded or explicitly joined, temporary sockets live under `/tmp` temporary directories, and cleanup runs in `finally`/context managers. No temporary server remains running.
