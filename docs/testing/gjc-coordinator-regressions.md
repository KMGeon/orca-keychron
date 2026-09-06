# Coordinator follow-up regressions

## Session-cap human-request retention

An independent Astra review challenged the new root-admission fallback at the 256-session cap. With an active root, one child holding the only human request, and 254 other active children, a new root previously evicted the first non-root record and lost the only pending request. Two added component regressions cover an ask and a yielded decision. Both failed with expected pending=1 / actual=0, recorded in `gjc-cap-priority-red.txt`.

The fallback now prefers a record without decisions or ask tools before dropping a record that needs human input. It still admits the actual new root, stays within 256 records and marks coverage incomplete. If every record contains a human request, bounded storage necessarily loses a record; the remaining requests retain waiting priority and complete=false exposes observation loss.

`bun test tests/` passed **44 tests / 163 assertions**, recorded in `gjc-cap-priority-green.txt`. The reviewer independently reran that suite. These cap traces exercise the exported observer with native-shaped events. Normal GJC new-session handling settles its owned children before switching, so this is not claimed as a fresh actual GJC run with 256 simultaneously active children.

Hook SHA-256 at this follow-up: `e29cad5aa8749bff21c1f4c213df96cbe4e6019fa19a22162aac8bf3f822cea1`.

## Test validity checks

The independent review also reproduced an E2E helper false-positive: filtering historical snapshots for a desired state could accept an older waiting state after the current state had incorrectly cleared both requests. The actual-GJC audit owner is correcting the temporal oracle and adding a regression; final results belong in that audit report.

The coordinator rejected a proposed tracker oracle that would discard pending counters on a closed child. A child shutdown does not establish a human answer. The final state-invariant test retains waiting and pending counts while excluding the closed child only from the active agent count.

The client-cap test's Python 3.9 BrokenPipe was eventually reproduced with a captured receiver error (None) and zero accepted clients. The Apple Python 3.9 interpreter starts its real monotonic clock near zero per process; the dataclass client timestamp factory retains that real callable, while the test set the receiver clock to 100.0. New clients therefore appeared over ten seconds idle and were correctly dropped. The test now seeds its fake clock from the real monotonic baseline before starting the receiver and advances it by CLIENT_TIMEOUT. This is a test defect, not a product timeout defect. The coordinator reran the real Python 3.9 source/transport suite: **83 passed in 7.36s**, recorded in `gjc-transport-clock-final-py39.txt`. An initial clock-swap-race hypothesis was discarded; stopping/restarting alone did not fix the mismatch. Failure diagnostics remain in the test for future receiver errors.

## Plain status exposes incomplete observation

Two regressions (direct CLI formatting and actual receiver/CLI subprocess) failed because complete=false working status was visually identical to complete=true. `_print_status` now appends `incomplete coverage` only when complete is explicitly false; waiting/working colors and the JSON schema are unchanged. A later complete frame removes the marker. Red evidence: `gjc-status-coverage-red.txt`. The isolated Python 3.13 CLI/unit/process/doctor selection passed **44 tests in 6.25s** (`gjc-status-coverage-green.txt`).

A preceding broader run passed 42 and failed two subprocess starts because a concurrent worker replaced the shared .venv interpreter. The public copy of `gjc-status-coverage-interpreter-race.txt` removes the entire ambient environment mapping and normalizes personal paths; an initial partial redaction was insufficient and was corrected before publication. The original and published hashes are recorded in `publication-redaction.json`; this is historical failure evidence, not a new test run or a product failure. Root validation now uses a dedicated `/tmp/gjc-test-audit/final-py313` environment. CLI test children receive only explicit PATH/HOME/PYTHONPATH/config variables, and the final gate itself uses an allowlisted environment.
