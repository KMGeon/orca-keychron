# GJC protocol/tracker second audit

Date: 2026-09-06 Asia/Seoul  
Task: `task_654988da7d63` / dispatch `ctx_e7cfc6474f91`  
Scope: `gjc_protocol.py`, `gjc_tracker.py`, their existing focused tests, and the new deterministic invariant suite. No GJC/provider account, HID, keyboard input, service, global install, Git, or PR action was used.

## Outcome

Two owned product defects were reproduced and fixed.

1. **R24 / WIRE-5:** `parse_snapshot(bytes)` delegated bytes directly to `json.loads`, which autodetected UTF-16/32 and accepted a UTF-8 BOM. It now enforces the JSON Lines boundary by checking the raw byte limit first, decoding strict UTF-8, and letting the text JSON parser reject a BOM.
2. **R29, R33 / REG-2:** registry restore opened a path for blocking reads before checking that it was a regular file. A mode-0600 FIFO could therefore hang startup. Restore now opens nonblocking, then retains the existing owner/type/mode/size checks.

One proposed semantic change was rejected after cross-owner contract review. **R18/R39 / STATE-3** intentionally retains unresolved pending counters and `waiting` human priority even when that session's state is `closed`; only `agent_count` excludes the closed row. Child shutdown does not prove the human request was answered, so no weakening tracker edit remains.

## Added cases

`tests/test_gjc_state_invariants.py` adds 44 collected tests grouped into five requirement-driven areas.

| Requirement IDs | Independent case/oracle |
|---|---|
| R18, R39 | All 1,956 permutations of all nonempty subsets of the six priority classes; incomplete and paused/cancelled aliases; ten `working` plus one `waiting` at every position; closed+pending retention; explicit frame closure. |
| R24, R28 | Malformed scalar types, bool/int confusion, exact identifier/session/counter boundaries, total 65,536 pending bound, duplicate session IDs, missing/multiple root identity, strict UTF-8/no-BOM byte frames. |
| R15, R31, R32 | Complete recovery after an incomplete sequence gap, same/older replay rejection, stale producer/process/pane/worktree generations, valid `/new` root-session switch, fractional lease edge/backward query/disconnect/reconnect. |
| R33, R35 | Five-launch deterministic trace covering stable slots, overflow order, disconnect without reclaim, clear promotion, registry restart as unknown, higher-sequence reconnect, explicit close promotion, and persistent tombstones. |
| R29, R33, R34 | Partial/corrupt/duplicate/non-UTF registry input, malicious FIFO nonblocking rejection, pre-commit replace failure cleanup and later-frame recovery, plus representative priority and reclaim semantic mutation kills. |

The mutation guard temporarily substitutes a wrong `working`-over-`waiting` aggregate and a no-op slot allocator in memory. Both violate the independent oracle as expected; shared source files are never rewritten for mutation testing.

## Red and green evidence

Detailed RED output and the reclassified STATE-3 challenge are in `docs/testing/gjc-state-audit-red.txt`. Final commands and cleanup evidence are in `docs/testing/gjc-state-audit-green.txt`.

- RED REG-2: focused invariant suite timed out in its bounded two-second child process while opening a FIFO registry.
- RED WIRE-5: strict encoding selector produced 3 failures because UTF-16LE, UTF-32LE, and UTF-8 BOM frames were accepted.
- GREEN Python 3.13: 88 focused protocol/tracker tests passed in 0.16s.
- GREEN Python 3.9.6: the same 88 tests passed in an isolated temporary environment in 0.22s; the environment was removed afterward.
- GREEN lint: focused Ruff check passed for both owned modules and all three focused test files.

## Owned content hashes

SHA-256 values after green verification:

```text
239ccc2849e466c2a4b0b12b2257c6b424a3436658f4106baa6e754b7e635e40  src/orca_keychron_gjc/gjc_protocol.py
fed2fa0e1255974b5e06f19165b3fcea5d29e3c5e1be9a11d669758a0b66f9f0  src/orca_keychron_gjc/gjc_tracker.py
86ef79d03a8cabe217ad26b44284a99dfc865831edce998eb11c8c9239f005bd  tests/test_gjc_state_invariants.py
6fe77789fe77c4f28e4c334fe99d51eff41616d6cb1b9975dd8950d88390358f  docs/testing/gjc-state-audit-red.txt
a5e37fda362eb73a4e7a582b0c1e3b09b1d7db24796b91e65b38ab9c79509f67  docs/testing/gjc-state-audit-green.txt
```

## Unresolved limitations

- R36 OS-death authorization remains a source-layer responsibility; this tracker audit covers only the post-authorization clear/tombstone transition and does not claim to prove PID death policy.
- The FIFO regression proves bounded rejection for one malicious special-file class. Same-UID concurrent path replacement remains a cooperative-local boundary, not a hostile-user security guarantee.
- Python 3.9 verification used an isolated temporary pytest environment because the system 3.9 interpreter had no pytest package; no global package or service was installed.
- These are software protocol/state/persistence tests. They do not constitute real GJC model/provider, HID, physical key input, optical LED, global service, or full user-visible E2E evidence.
