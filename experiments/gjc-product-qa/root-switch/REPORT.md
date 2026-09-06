# GJC `/new`, resume, and shutdown root regression

Verdict: **PASS** on GJC 0.16.4 using the actual installed product hook, actual `GjcStatusSource`, and the existing loopback `product-qa/fixture` provider. The metadata-only result is [`evidence.json`](evidence.json).

## Exact case executed

1. Started `harness.py provider` and `harness.py receiver --generation 1` on the private runtime `/private/tmp/gjc-rs-final-8e0c253c` in two exact Orca terminals.
2. Ran `harness.py prepare --name root_switch --scenario success`; the isolated installer copied the product `gjc_hook.ts` with matching source/installed SHA-256 `d1f41261...6211b`.
3. Launched unmodified `gjc/0.16.4` directly in exact Orca terminal `term_c413c850-4648-4263-810e-e08071d58e59`, completed the initial fixture turn, invoked `/new`, completed one fixture turn under the new root, selected the prior known session through `/resume`, and completed one fixture turn under the resumed root.
4. Invoked `/exit`, verified the GJC PID exited, observed the final content-free wire snapshot with `closed=true`, and verified the actual receiver returned zero launches afterward.

## Result

- `/new`: root changed from `01a072e9...a171` to `01a072ea...4d2f`; `launchId=e6c8baba...da72`, producer, PID 33693, slot 0, terminal, pane, and `startedAt` stayed unchanged. The new root emitted `idle`, `working`, then `done` over sequences 30–51.
- Resume: the same process switched root back to `01a072e9...a171`; the following turn emitted `working` then `done` while the launch remained connected in slot 0.
- Shutdown: sequence 69 reported root `closed`, `closed=true`, and `complete=true`; the next live status contained `launches=[]`, so the owned slot was freed.
- The final observed launch lifetime was 95.7 seconds. The provider handled three fixture requests and all three identified the local fixture model.

## Boundary and limits

- Evidence contains only identity, sequence, state, count, connection, and lifecycle metadata; no prompt, answer, tool result, or session history is included.
- This does not verify a real model/provider account, physical HID output, global installation/autostart, or GJC versions other than 0.16.4.
- A discarded first attempt used `/tmp/gjc-rs-8e0c253c`; on macOS `/tmp` is a symlink, so GJC's own storage guard rejected `/exit` with `Unsafe reparse storage path: /tmp`. Re-running through canonical `/private/tmp` removed that unrelated harness-path condition and produced the passing shutdown evidence above; no GJC core or product code was changed.
- `orca terminal wait --for exit` timed out because the Orca command terminal returned to its shell after GJC exited. PID absence, final `closed` wire metadata, and empty receiver status are the shutdown assertions.
