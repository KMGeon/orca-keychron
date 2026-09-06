# GJC parent-decision restart/successor audit

This harness closes the process-restart boundary in `GJC-DECISION-RESTART`.
It uses installed, unmodified GJC 0.16.4 in two exact Orca terminals, an
isolated product native hook, the real bridge/tracker, and a loopback-only
deterministic provider. It never uses a model account, HID, keyboard input,
global install, or global service.

## Expected flow

1. Launch A creates an actual child. The child yields the exact
   `needs_user_decision` envelope and the parent reads the actual `agent://` output.
2. The product status must be `waiting` with unresolved requests while the real
   parent `ask` UI is open. The harness chooses the fixture's explicit answer.
3. The fixture records the actual predecessor child ID, request ID, checkpoint,
   and actual answer. Launch A does not resume the child and exits gracefully.
4. Fresh launch B first attempts the actual predecessor ID. GJC 0.16.4 must
   return its native `not_found` receipt; the harness never calls that a resume.
5. Launch B starts a new actual successor with the preserved envelope and answer.
   The successor validates request, checkpoint, answer, and continuation kind;
   its ID must differ and its final outcome must be exactly `successor`.

## Reproduce

Use a fresh canonical `/private/tmp` runtime each time:

```sh
python3 experiments/gjc-successor-audit/harness.py run \
  --runtime /private/tmp/gjc-successor-audit-$(uuidgen)
```

For the required frozen distribution run, pass the exact wheel supplied by the
coordinator. The harness safely extracts it under the owned runtime and imports
the installer, bridge, tracker, and hook asset from that wheel:

```sh
python3 experiments/gjc-successor-audit/harness.py run \
  --runtime /private/tmp/gjc-successor-final-$(uuidgen) \
  --wheel /absolute/path/orca_keychron-<version>-py3-none-any.whl \
  --expected-wheel-sha256 <coordinator-supplied-sha256>
```

Focused fixture verification:

```sh
python3 -m pytest -q tests/test_gjc_successor_fixture.py
uvx ruff check --select E,F,I,B \
  experiments/gjc-successor-audit/harness.py \
  tests/test_gjc_successor_fixture.py
```

The run writes metadata-only `verdict.json`, native wire lifecycle rows, provider
verdict events, explicit synthetic `fixture-data.json`, commands, and install
hashes under its runtime. `finally` closes only created terminal handles, stops
owned provider/receiver and exact-agent-dir GJC broker PIDs, and removes the
owned socket. A failed assertion keeps the runtime evidence and returns nonzero.

## Evidence boundary

The result proves the actual GJC tool/lifecycle path against deterministic
fixture data. It does not prove automatic answer persistence, original-child
resume, real-model prompt compliance, provider-account behavior, physical HID,
keyboard output, global setup, or versions other than GJC 0.16.4.
