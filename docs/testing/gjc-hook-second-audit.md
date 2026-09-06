# GJC native hook second audit — 2026-09-06

Scope: owned `src/orca_keychron_gjc/assets/gjc_hook.ts`, `tests/gjc_hook.test.ts`, new `tests/gjc_hook_faults.test.ts`, and new evidence in this directory. No upstream edits, provider/model accounts, HID, services, global installation, Git writes, or unrelated terminals were used. Other workers' checkout changes were preserved.

## Outcome

Added **21 fault cases** beyond the original 21 Bun tests; final **42 passed, 0 failed, 153 assertions**. Three newly added cases failed against the original hook, revealing two defect mechanisms: session-cap root identity loss and decision-answer temporal miscorrelation. Both mechanisms are fixed with their red regressions retained. Two semantic mutants were killed in temporary source copies. Strict TypeScript checking and the evidence runner's Ruff check pass.

## Requirements and cases

These IDs are audit-local aliases for the named sections of `docs/gjc-keychron-development-ticket.md` and `docs/gjc-bridge-contract.md`, not pre-existing ticket IDs.

| ID | Contract source | Added cases / expected behavior |
|---|---|---|
| H-ID / H-LOADER | launch lifetime; Publisher duplicate suppression | At 256 sessions, `/new` must track the actual new root and close on its shutdown; retain pending child when an inactive record can be evicted. Separate user/project registrations receive original shared event objects and remain root-authorized after delivery-order changes. Child reopening current root cannot close it. |
| H-CORR | state interpretation; parent actual-answer rule | An ask that started before a decision cannot answer that future request. Concurrent answers bound to an earlier receipt cannot clear a later receipt reusing the same request ID. A new ask can resolve the current receipt. |
| H-PENDING / H-PRIORITY | unresolved requests; waiting priority | Child/grandchild/great-grandchild requests survive parent completion and session switches. Cancelled or clarification answers leave their matching decisions pending. Reopened child ID plus late terminal events preserves pending decision. Failure/cancel/retry never supersedes an unresolved ask's waiting state. |
| H-YIELD | validated yield result | Seven malformed receipts: null, empty, missing data, null data, forged status, conflicting error, duplicate options all remain unknown after child shutdown. |
| H-BOUNDS | Publisher observation bounds | Same tool ID in separate sessions stays independent; deduped closed call does not reopen. Tool overflow retains 128 asks and marks incomplete; exhausted resolved-call history never regains complete=true. |
| H-TRANSPORT / H-BACKPRESSURE | Publisher transport | Real temporary Unix reconnect carries latest full state, stable IDs, retained grandchild pending decision and explicit closed flush. Real paused receiver induces write backpressure; writable buffer and coalesced latest frame each remain below 512 KiB; bounded shutdown exits. |
| H-LIVENESS / H-LINEAGE | no host liveness interference; nested CLI ownership | A real Bun subprocess exits naturally with absent receiver without disposal. A real nested Bun process inherits the parent ownership marker and cannot register a root. |
| Privacy | wire protocol forbidden contents | Secret sentinel in question/options/checkpoint, tool results, answers and errors is absent from snapshots and actual reconnect wire frames. Receiver persistence/privacy is another owner's scope. |

Original tests additionally cover successful/aborted assistant classification, exhausted retry, queued work, maintenance-related behavior, multiple asks, request-ID collisions, bounded shutdown without receiver, and Python wire parsing. They remain baseline coverage, not proof of exhaustive correctness.

## Proven failures and fixes

1. **Session capacity loses actual root identity.** Original `observe()` returned before accepting a root `session_switch` when the map already held 256 sessions. The next root shutdown therefore could not close the launch, and snapshots kept the obsolete root ID. Root switches now admit the real root, preferentially evicting an inactive record without tools, decisions, maintenance or queued work; coverage becomes permanently incomplete. At absolute saturation with all records pending, a bounded model must drop a record, and `complete=false` explicitly signals that loss.
2. **A matching request string was insufficient to attribute an answer.** Original ask completion searched whichever decisions existed at completion time. It could clear a decision raised after the ask started, or a new receipt reusing an old answered request ID while another old ask remained active. Each pending decision now has a process-local symbol receipt; ask start captures only uniquely observed receipt tokens. Completion requires the current token to match. Tokens and question IDs remain internal and never enter snapshots.

`tests/gjc_hook.test.ts` has only a type-check correction: convert the observed environment value with `String(...)` so TypeScript does not keep an obsolete `undefined` narrowing across the opaque `createHook()` mutation. Runtime assertion remains the exact expected PID string.

## Reproduction / evidence

- Red: `bun test tests/gjc_hook_faults.test.ts` against original hook SHA-256 `d1f41261a9e669deb6cb9bb578bbd1eb07d5b540d6b50d1311b6b2eb8796211b`; output `gjc-hook-second-audit-red.txt` records 10 pass / 3 fail in the initial 13 cases.
- Green: `bun test tests/gjc_hook.test.ts tests/gjc_hook_faults.test.ts`; output `gjc-hook-second-audit-green.txt` records final 42 pass / 0 fail. `gjc-hook-second-audit.patch` preserves the product delta; apply it in reverse to a temporary copy to reconstruct original bytes, never to shared source during an audit.
- Mutations: `python3 docs/testing/gjc-hook-mutation-check.py`; output `gjc-hook-second-audit-mutations.txt`. Mutants replace waiting with unknown and clear child decisions on shutdown. Both fail the focused semantic expectations; all source/test copies are cleaned by TemporaryDirectory.
- Strict type check: TypeScript 5.4.5, `--noEmit --strict --skipLibCheck --target ES2022 --module ESNext --moduleResolution bundler --allowImportingTsExtensions`, all three owned TS files, temporary typeRoots symlinking existing cached `@types/node` 22.19.8 and `bun-types` 1.3.9; output `gjc-hook-second-audit-typecheck.txt`. No package download/install. Ruff: `uv run --no-sync ruff check docs/testing/gjc-hook-mutation-check.py`; output `gjc-hook-second-audit-lint.txt`.
- Socket/process tests use event-based frame/connect gates and deadline timeouts, not arbitrary synchronization sleeps; every owned process, socket server and temporary directory is cleaned in finally. The pre-existing tests retain their older polling helper unchanged.

## Native provenance and limits

Pinned checkout `/tmp/gajae-code-keychron-research-20260906` was verified at commit `f50b17a7fa9faab5935cbf2c358794597b1bd760`. Inspected `packages/coding-agent/src/extensibility/hooks/loader.ts` createHookExtensionFactory (original payload forwarded, context adapted), `extensibility/extensions/runner.ts` createContext (fresh readonly facade), `session/agent-session.ts` event mapping around lines 8770–8845 (`tool_execution_end` includes explicit isError; retry end contains success/attempt/finalError), and `tools/yield.ts` lines 200–248 (native details data/status/error shape). Ask fixture uses native questions/options and selectedOptions/customInput/results shapes.

Most cases are deterministic native-loader-shaped events, **not an actual GJC process**. Transport/liveness tests use actual Bun processes and Unix sockets, but synthetic hook API registration; actual installed GJC E2E belongs to the coordinator's runtime worker and must refresh to the hook hash below. Prompt-only decision instructions do not enforce child resume or provider behavior; no template was edited. Pending retention for reused child IDs is tested, but events without generation identity cannot prove which reopened same-ID execution produced every late non-pending terminal event. No real hardware or model behavior is claimed.

## Owned final SHA-256

- `src/orca_keychron_gjc/assets/gjc_hook.ts`: `f3e0ff1e113023635167b6d72fa45e23fbec0f5f1d994351105c9e42c54ba056`
- `tests/gjc_hook.test.ts`: `8a294967f083702d6ce6df2d5041cb9f5ffc7d318a2d2672416d438703594460`
- `tests/gjc_hook_faults.test.ts`: `1a6af6a6b78d889ae5ef24d39b7b14c34bf6ab8d3b6ccfc83e5b75a85abcec65`
