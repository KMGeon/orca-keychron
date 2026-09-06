# GJC Linux CI validation

Date: 2026-09-06 (Asia/Seoul)

Historical worker handoff status: **not ready**. See the coordinator follow-up below for the subsequent fixes and final gate. Workflow syntax passes, but a nonportable transport-test clock
fails on the supported CPython 3.9 configuration and makes the Python 3.9 CI jobs unsafe
to treat as deterministic. An actual Ubuntu run was not available.

## Scope and boundaries

This audit covers `.github/workflows/tests.yml`, `.github/workflows/publish.yml`,
`pyproject.toml`, the GJC Python/TypeScript sources, and the tests exercised by those
workflows. It does not touch HID/input devices, LaunchAgents, global hooks or services,
model providers, Git remotes, pull requests, or releases.

No actual Ubuntu/Linux test has run. `docker info` was read-only and returned exit 1
because `<home>/.docker/run/docker.sock` does not exist. Docker Desktop was not
started and no system tooling was installed.

## Workflow syntax and action pin

- `actionlint` v1.7.7 was built into `/tmp/gjc-linux-ci-audit/bin/actionlint` with an
  isolated `GOBIN`, `GOMODCACHE`, and `GOCACHE`. Binary SHA-256:
  `a9d3e38462fc51648ba14adfe3f55414f8d5bbc0cda34759275f9c1819277fec`.
- `/tmp/gjc-linux-ci-audit/bin/actionlint -color .github/workflows/tests.yml
  .github/workflows/publish.yml` returned exit 0 with no diagnostics.
- Read-only `git ls-remote https://github.com/oven-sh/setup-bun.git 'refs/tags/v2*'`
  resolves both `refs/tags/v2` and `refs/tags/v2.2.0` to the pinned commit
  `0c5077e51419868618aeaa5fe8019c62421857d6` used by both workflows.
- Both workflows request the exact Bun version `1.4.0`. The already-installed host Bun
  also reports `1.4.0`; this checks the command suite locally, not the Ubuntu action
  download/install path.

Workflow hashes at the first lint pass:

```text
f3cd25333a212cbbe0c7f57dc13908b73a6f38603c9c598b825875ee7173d0da  .github/workflows/tests.yml
714ec65a7ff44d6b3facba2e1c0c93014b09ede1688f0497184c10d007b87b4b  .github/workflows/publish.yml
241cb2e0a3f5b80d274f9bb4aed70ccce649d0678088bf36a0beb6ba283bc217  pyproject.toml
```

## Python 3.9 and Linux portability review

- `/Library/Developer/CommandLineTools/usr/bin/python3` is CPython 3.9.6. Its
  `compileall -q src tests` pass returned exit 0, so the current Python files parse on
  Python 3.9.
- New-style annotations (`list[...]`, `X | None`) are guarded by
  `from __future__ import annotations` in the affected source modules.
- Linux-relevant primitives used by the GJC runtime (`fcntl`, `AF_UNIX`, selectors,
  `SIGTERM`/`SIGKILL`, and XDG config paths) are available on GitHub's Ubuntu runner.
  macOS LaunchAgent behavior is platform-gated, while its tests explicitly substitute
  `sys.platform` and a fake `launchctl` runner.
- The Python 3.9 wheel build succeeded as `py3-none-any`, and the package metadata limits
  the PyObjC dependencies to Darwin. This is positive packaging evidence, not proof that
  Linux dependency installation or the full suite passes on Ubuntu.
- The integration fixtures use `venv/bin/python`, `/bin/sh`, Unix-domain sockets, and
  negative signal return codes; those paths and semantics match Ubuntu. They do not use
  macOS-only venv executable layout in the Linux branch.

## Test evidence

### Provisional macOS full-suite evidence (not a release gate)

An isolated CPython 3.9.6 environment was created at
`/tmp/gjc-linux-ci-audit/python39-darwin`, installed with the workflow-equivalent
`python -m pip install --upgrade ".[dev]" build`, and built a fresh local wheel in
`/tmp/gjc-linux-ci-audit/wheel-py39-initial`.

The subsequent full test run reported `17 failed, 401 passed`, but its test-source hash
manifest changed during execution: three tests were edited and two new fault-test files
appeared. That run is invalid as a final gate and the failures must not be attributed to
one immutable source revision. It is retained only to explain why a frozen rerun is
required.

The initially observed transport failure passed on CPython 3.13.5 in isolation and in 50
fresh-process repetitions. Those passes did not clear Python 3.9 compatibility: the final
focused rerun below reproduces the failure deterministically on CPython 3.9.6.

### Stable CPython 3.9 failure

The coordinator added receiver diagnostics and requested one final focused run. With
stable before/after hashes, the exact command failed:

```text
/tmp/gjc-linux-ci-audit/python39-darwin/bin/python -m pytest -q \
  tests/test_gjc_transport_faults.py::test_client_cap_and_partial_stalls_release_capacity_with_injected_clock -vv

BrokenPipeError: [Errno 32] Broken pipe
AssertionError: Partial clients failed: receiver_error=None, accepted_clients=0

9fa9414e7055af0a60ac0d8be402c19e855737c912b6263776a17bc223580607  src/orca_keychron_gjc/gjc_source.py
259906cb60a8e391476e93cda35f0a9065ff5866140899d4ad78a72df5158e08  tests/test_gjc_transport_faults.py
```

The failure is a test-clock compatibility bug, not evidence of a receiver exception:

1. `_Client.touched` captures the original `time.monotonic` callable as its dataclass
   `default_factory` when `gjc_source.py` is imported.
2. The test later replaces the module's `time` object and sets its fake clock to `100.0`.
3. Apple's Command Line Tools CPython 3.9.6 reports the original monotonic clock near
   process-relative zero (`0.005921291` in the audit), whereas CPython 3.13.5 reports a
   system-wide value (`328450.004241125`).
4. On Python 3.9 the accepted clients therefore start with `touched` near zero, while the
   receiver loop observes fake `now == 100.0`; it immediately expires both as more than
   `CLIENT_TIMEOUT` old, and the first write receives EPIPE.

Restarting the receiver after installing the fake clock does not change the dataclass's
already-captured default factory. A portable test should seed its fake clock from the
original monotonic callable before replacing the module time object, then advance from
that baseline by `CLIENT_TIMEOUT`.

This proves a supported-version portability defect in the test. It does not prove that a
particular Ubuntu runner will fail: Linux uses a different monotonic-clock implementation,
and the observed outcome can depend on whether runner uptime is below the test's arbitrary
`100.0` baseline. That platform dependence is the CI risk.

### Additional lint blocker pending final change-set selection

The exact workflow command `.venv/bin/ruff check .` also exited 1 with 93 findings:
92 under `experiments/gjc-successor-audit/` and one import-order finding in
`tests/test_gjc_install_faults.py`. Because those paths are currently untracked and are
being modified by other workers, this blocks CI only if they are included in the change
set and remain unfixed when committed.

## Required rerun after the Python 3.9 test fix

1. Seed the injected clock from the original monotonic value and rerun the focused test
   under CPython 3.9.6.
2. Record one SHA-256 manifest for workflows, `pyproject.toml`, `src`, and `tests`.
3. Build a new wheel into an empty audit-owned directory and set
   `GJC_TEST_WHEEL_DIR` to that exact directory.
4. Run the full Python suite on macOS CPython 3.9.6 and 3.13.5.
5. Run `bun test tests/`, `ruff check .`, and `actionlint` on both workflow files, then
   compare the ending manifest and reject the run if audited source changed.

The final audit snapshot is `/tmp/gjc-linux-ci-audit/final-audited-source.sha256`; its
SHA-256 is `1a22fff68d84a196008c0a9ea491ca4d2ddcc570428ca1b5e25b17e21b8ed35d`.
It is a handoff snapshot, not a source-freeze attestation, because product work was still
concurrent and the coordinator requested this worker finish after the focused diagnostic.

## Coordinator follow-up

The transport test clock was corrected to use the original monotonic baseline. The focused real CPython 3.9 source/transport suite passed 83 tests; evidence is `gjc-transport-clock-final-py39.txt`. All 93 reported Ruff findings were resolved. The frozen-wheel full CPython 3.9 and 3.13 gates, Bun suite, Ruff, and actionlint now pass; exact final counts and commands are in [the second-audit report](gjc-second-audit.md) and [final-gate-results.json](final-gate-results.json). This supersedes the provisional blockers above. Actual Ubuntu execution remains unperformed; no local macOS pass is presented as Linux execution.
