# GJC product integration QA

This is a bounded loopback harness for the **actual `src/orca_keychron_gjc` product hook and receiver** with installed, unmodified GJC 0.16.4. It never uses a real model, global GJC profile, Keychron HID, global product config, or another user's terminal.

## Safety boundary

- Use a fresh private runtime such as `/tmp/gjc-product-qa-<run>`.
- Every case gets an explicit isolated `agent` directory and `sessions` directory.
- `prepare` installs the actual product hook into that explicit agent directory. The `duplicate` case also installs the same product hook into the isolated fixture project's `.gjc` directory.
- The provider binds to `127.0.0.1` and logs metadata only. The receiver is the actual `GjcStatusSource`; a read-only parse observer records only the production wire schema.
- Launches are direct `gjc` commands in Orca-owned terminals. No product wrapper is required for registration.

## Bounded workflow

1. Start the provider in an owned Orca terminal:

   ```sh
   PYTHONPATH=src python3 experiments/gjc-product-qa/harness.py provider --runtime /tmp/gjc-product-qa-<run>
   ```

2. Start receiver generation 1 in a second owned Orca terminal:

   ```sh
   PYTHONPATH=src python3 experiments/gjc-product-qa/harness.py receiver --runtime /tmp/gjc-product-qa-<run> --generation 1
   ```

3. Prepare a fresh case. Supported scenarios are `success`, `failed`, `slow`, `mass`, `decisions_two`, and `duplicate`:

   ```sh
   PYTHONPATH=src python3 experiments/gjc-product-qa/harness.py prepare --runtime /tmp/gjc-product-qa-<run> --name success_a --scenario success
   ```

4. Copy the printed `directLaunch` value exactly into `orca terminal create --worktree active --command ...`. It changes only to the isolated fixture cwd and then runs the unmodified `gjc` binary directly with the isolated profile environment.

5. Capture live status and renderer output without HID:

   ```sh
   PYTHONPATH=src python3 experiments/gjc-product-qa/harness.py status --runtime /tmp/gjc-product-qa-<run>
   PYTHONPATH=src python3 experiments/gjc-product-qa/harness.py colors --runtime /tmp/gjc-product-qa-<run>
   ```

## Required assertions

1. Two direct `success` launches produce two launch IDs in distinct stable slots; each root's native children remain sessions within its launch rather than consuming another slot.
2. `mass` reaches one launch with 12 sessions. Capture a wire frame with ten `working` sessions, one pending-decision `waiting` child, and one completed fanout session; aggregate state is `waiting`, pending count is one, and `colors` reports `isOrange: true`.
3. In `decisions_two`, answer `req_1`, capture that the launch remains `waiting` with a nonzero pending count for `req_2`, then answer `req_2`. Provider metadata must show each actual child resume and both correlation/checkpoint validations.
4. `success`, `failed`, and interrupted `slow` launches must remain distinguishable in wire metadata as `done`, `failed`, and `cancelled`; the receiver intentionally renders a disconnected/cancelled aggregate conservatively as `unknown`.
5. Stop receiver generation 1, verify persisted status is `unknown` with unchanged slots, start generation 2, and verify hook reconnect snapshots return the same launches to `connected` without renumbering. Kill one exact owned GJC producer to verify disconnect becomes `unknown`; the `duplicate` case must still register one launch/group.

## Interpretation

Passing this harness proves product hook discovery, content-free snapshot transport, receiver aggregation, stable local slots, and existing renderer mapping against a deterministic local provider. It does not prove real-model compliance, physical keyboard output, global installation, or behavior across unsupported GJC versions.
