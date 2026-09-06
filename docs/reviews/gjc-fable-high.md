# Final review: GJC package + shared runtime (Fable 5.1 high)

- **Scope**: `main` (merge base `a1e844f`, equal to HEAD) + uncommitted; `pyproject.toml`, `src/orca_keychron_gjc/**`, changed `src/orca_keychron/*`, `tests/test_gjc_*.py`, `tests/gjc_hook.test.ts`. Skipped: `experiments/`, `docs/visualizations/`, `.agents/`, experiment evidence docs (used only to cross-check claims).
- **Files**: 13 GJC product files (3 assets), 6 shared runtime files, 8 test files, contract doc
- **Findings**: 2 (critical: 0, high: 0, medium: 2)
- **Reviewer model**: harness reports Claude Fable 5.1 (`claude-fable-5-1`); not independently verified.
- **Reviewed at**: 2026-09-06 03:05–03:47 KST. `gjc_hook.ts`, `gjc_source.py`, `config.py`, `cli.py`, `pyproject.toml` and the contract doc were modified by other workers during the review; every finding and hash below refers to the final state listed in the hash table, which I re-read after the last change notice (line counts matched: hook 476, source 368, cli 478, config 210).

### **#1 `clear`가 잘못된 launch id를 "bridge is not reachable"로 보고함**

`request_control()`은 소켓에 연결하기 전에 `_control(request)` → `_uuid()`로 `launch_id`를 검증하고, UUID가 아니면 `GjcProtocolError`(`ValueError` 하위)를 던진다. `clear_command`는 `(OSError, ValueError, RuntimeError)`를 한꺼번에 잡아 "GJC bridge is not reachable; start orca-keychron-gjc run or serve before clearing"으로 바꾸므로, 브리지가 살아 있어도 `orca-keychron-gjc clear not-a-uuid`(오타, 슬롯 키 입력 등)는 존재하지 않는 연결 문제로 안내된다. 검증 오류는 연결 시도 전에 분리해서(예: `_control` 검증을 먼저 호출하거나 `GjcProtocolError`를 별도 처리) 실제 원인을 출력해야 한다.

- **File**: `src/orca_keychron_gjc/cli.py`
- **Lines**: `346-351` (`request_control` 검증: `src/orca_keychron_gjc/gjc_source.py:79-82`)
- **Severity**: `medium`

### **#2 receiver 소유권·실패 `RuntimeError`가 traceback으로 노출됨**

`GjcStatusSource.start()`는 소켓/registry sidecar lock 경합 시 `RuntimeError("Another GJC receiver already owns this ...")`(`gjc_source.py:44`, `:194`)를, `indicators()`/`status()`는 receiver thread 실패 후 `RuntimeError("GJC receiver failed; ...")`(`gjc_source.py:224`)를 던진다. `_serve`(`cli.py:272,275`)와 `Indicator.run`(`src/orca_keychron/indicator.py:111,123`)은 이를 잡지 않고, `main()`은 `(AutostartError, ConfigError, GjcInstallError, KeychronError)`만 `SystemExit(str)`로 바꾸므로 사용자는 한 줄 메시지 대신 Python traceback을 본다. 재현: autostart `run` 서비스가 떠 있는 상태에서 `orca-keychron-gjc serve` 실행(HID lock을 거치지 않으므로 `KeychronError` 경로도 없음), 또는 `serve`를 두 번 실행. `main()`의 예외 매핑에 receiver 오류를 포함하거나 전용 예외 타입으로 감싸면 된다.

- **File**: `src/orca_keychron_gjc/cli.py`
- **Lines**: `475-478`
- **Severity**: `medium`

## Verified clean (evidence)

- **Hook ↔ upstream 0.16.4 event contract**. Native `hooks/pre/<name>.ts` modules are adapted onto the ExtensionRunner (`extensibility/hooks/loader.ts` `createHookExtensionFactory`), so `tool_execution_start/end`, `message_end`, `agent_failed`, `auto_retry_*`, `session_switch` and `before_agent_start{systemPrompt}` are delivered (extension `on()` overloads at `extensions/types.ts:1181-1235`; runner passes the same `event` object to every handler, `runner.ts:803-830`). The `pre/orca-keychron` matcher only filters `tool_call` (`hooks/normalize.ts` `hookModulePre.runtimeEvent = "tool_call"`), which the hook never registers. `normalizeToolMatcher` accepts hyphenated names. `.ts` files are discovered (`discovery/builtin.ts:703-760`, no extension filter, dot-entries skipped so `.orca-keychron/releases` is never loaded as a hook).
- **Yield / ask shapes**. `YieldDetails = {data, status: "success"|"aborted", error?}` (`tools/yield.ts:22-26,248`) matches `toolEnd`. Ask single-question details carry `selectedOptions/customInput/clarificationQuestion`, multi-question `results[{id,...}]` (`tools/ask.ts:84-103,1349-1386,1440-1455`); cancel throws `ToolAbortError` (so `isError` is true and no correlation happens), timeout returns empty selection (no answer). `questions[].id` exists in the ask schema (`ask-contract.ts:180,272`). `agent_end.stopReason` upstream is `completed|paused|cancelled|maintenance`; the hook's `"aborted"` check is dead but a cancelled run still lands in the tracker's `unknown` bucket via the assistant `stopReason:"aborted"` outcome, so no display difference.
- **Human-priority aggregation** (`gjc_tracker.py:191-209`): pending asks/decisions or `waiting` → failed → working → incomplete/unknown/paused/cancelled → done → idle; root `done` does not clear child pendings (`test_priority_child_asks_survive_root_done_and_full_recovery`). Complete-snapshot replacement, sequence monotonicity, producer/pid/startedAt/root-identity pinning (root `sessionId` intentionally not pinned so `/new` root switch is accepted), 8 s receive-clock lease, EOF → `unknown` with slot retained, explicit `closed` → retire + slot release, registry restore as offline `unknown`, retired identities never resurrect. Registry writes are 0600 atomic with fsync; restore rejects non-private/oversized/duplicate-slot/invalid-capacity files.
- **Receiver**: 32 clients, 512 KiB line bound, 10 s idle drop, one control per connection, producer connections cannot send controls, newer connection supersedes older without a false disconnect, second receiver fails without unlinking the live socket (flock sidecar + ECONNREFUSED probe), stop joins the thread and closes both lock fds even if resource cleanup raises. Storage failure marks all launches offline and surfaces via `RuntimeError` (see #2 for the CLI surface).
- **Installer**: user root `~/.gjc/agent` or `GJC_CODING_AGENT_DIR` (matches `gc-runtime.ts:445` primary), project root `<project>/.gjc`; hooks discovered from `<root>/hooks/pre`, agents from `<root>/agents` (`task/discovery.ts:52-61`), so both managed files land where 0.16.4 loads them. Loader embeds only `socketPath` + parent instructions. Journal/rollback, conflict refusal, symlink refusal, and socket length (≤103 bytes, same bound as the hook) are covered by `test_gjc_install.py`.
- **Version gate**: `install_command` expects `gjc/0.16.4`; the installed binary here prints exactly `gjc/0.16.4` (run locally: `gjc --version`), so the gate is correct against the real executable even though the pinned source's `main.ts:1499` prints the bare `VERSION`.
- **Wheel**: `uv build --wheel --offline` succeeded; the wheel contains `orca_keychron_gjc/assets/{gjc_hook.ts,decision-parent.md,decision-worker.md}` and the `orca-keychron-gjc` entry point.
- **Tests run by me**: `pytest tests/test_gjc_*.py` → 153 passed; `bun test tests/gjc_hook.test.ts` → 21 pass; earlier shared-runtime set → 104 passed (see `gjc-shared-runtime-fable.md`). Tests use `/tmp` sockets, tmp registries and patched lock paths only; no real HID, config, or hooks touched.
- **Orca identity env**: this Orca terminal exports `ORCA_TERMINAL_HANDLE`, `ORCA_PANE_KEY` (`<uuid>:<uuid>`, i.e. `tabId:leafId` as `orca_navigation.terminal_for_pane` expects) and `ORCA_WORKTREE_ID`, so `Publisher.enabled` is satisfied in the intended environment.

## Not flagged (known blind spots / design choices / below the bar)

- Extension confirmation/input UIs and child-local ask screens are not observable by the hook (documented in contract and `decision-parent.md`); `waiting` means observed ask or validated decision only. Model compliance with the decision envelope is prompt-guided, not enforced.
- `GjcTracker._persist` runs on every accepted frame including 2 s heartbeats (json + fsync file + fsync dir per launch, under the tracker lock shared with the 50 ms render tick). Wasteful but not user-visible on local SSD; consider persisting only when display data or slot assignments change.
- `_retired` grows without pruning until `MAX_IDENTITIES` (65536), after which new launches are refused until the registry is cleared manually. Long-horizon only.
- Installer honours `GJC_CODING_AGENT_DIR` but not upstream's secondary `PI_CODING_AGENT_DIR` fallback (`gc-runtime.ts:445`); a user relying only on the legacy variable would install to `~/.gjc/agent` while GJC loads from the legacy dir. `doctor` shows `native_dir`, so it is diagnosable.
- `agent_end{stopReason:"maintenance"}` is treated as a normal end; whether it can precede `auto_compaction_start` (and briefly show `done`) was not verified against the runtime and is left for the follow-up review.
- `_print_status` labels slots ≥ 12 as `overflow` even when more than 12 LEDs are configured. Cosmetic.

## SHA256 of reviewed files (final state, 2026-09-06 03:46:47 KST)

```
82a76aa74b1b38176a2b84866c342c1fc0c6e1173d67d279750c24904055b46d  pyproject.toml
8b70d42deb2f1ba6784eb0d5f137f96110b97f05439b1a9e6baf3fec49abe52f  src/orca_keychron_gjc/__init__.py
6d8b7d7846a845059d7a3107143f11131f63c5511d669b44085b15ec5e3d2279  src/orca_keychron_gjc/__main__.py
7ac06437bbfe7e3e6a941c7865191c531979ce6687936614f6c563a02eacb440  src/orca_keychron_gjc/assets/decision-parent.md
b7c2bae336bb47fa1ad3193e284ab9bfd832bab4e5629a581fa9244168875b21  src/orca_keychron_gjc/assets/decision-worker.md
d1f41261a9e669deb6cb9bb578bbd1eb07d5b540d6b50d1311b6b2eb8796211b  src/orca_keychron_gjc/assets/gjc_hook.ts
97bdd3e2ef144846f6ef2d1aadf8c401dc677dcb086460f59f1e663a9320dc67  src/orca_keychron_gjc/autostart.py
290d3f14c607b932423e702599ee73bb63f6e4ecdc3c825c6433d8f97bc793b0  src/orca_keychron_gjc/cli.py
cd57d71d3b2e41471d68edbe252d02b08240c1fe8d2a16425623e809b3eafe95  src/orca_keychron_gjc/config.py
dd6eaf9d60467a316f81d5866f1929e1794c47b3e322bbdfbdd22a3016699bd5  src/orca_keychron_gjc/gjc_install.py
c9cdd55e4f23525338af5fafb4adfb021c1f6ab11bfa03ab16780370e3ab3542  src/orca_keychron_gjc/gjc_protocol.py
43d6aa2e321d137b0fe2f0939eddc2fa09b566ceb25c60191c14e9db04d9c530  src/orca_keychron_gjc/gjc_source.py
30ee0d94db8f2f34af7a56683222acef9fffbca110cfa9bbcd293ad892a758f8  src/orca_keychron_gjc/gjc_tracker.py
020e98b242119666a654a8892ef2536fdb337ed95ee100ee0960742876643589  src/orca_keychron/device_lock.py
2dbad3d32f2d0b99d49f076a46a1901689045958250ab85c07f1372b882f716a  src/orca_keychron/indicator.py
9f99f115e6971d8435a6d37f387361e83dd1323cce0b08aa95f200ef160d6aa5  src/orca_keychron/models.py
f1ee96beaf5c105e92e7b526ae97344eec61a17f46716f2f2d8fc8a0d94e77d5  src/orca_keychron/rendering.py
6ea8113f4bb69a1e1dd483aca7cfa576c32340a2cc59940d6a8c4488793bc1ad  src/orca_keychron/digit_hold.py
825a42285cf868581e32cc10e27a0ec993037abad6b14d66b3c7b7bccec52086  src/orca_keychron/keychron_hid.py
bb985535422f995c284b4355be0314c0586e78c31d76eb7acd80216798cdd954  docs/gjc-bridge-contract.md
1537cd3d620190b1dd54453d5fd0b253fc7f75eeda4b1b1b7a93e3fc34a0f51f  tests/gjc_hook.test.ts
822cc7e68227bea953f6997c1d3fc18aeec56f21f94b8b9089a2535caf5a80ed  tests/test_gjc_protocol.py
c0580c29b5cedd74bd50cbf591504ee6373df96deaefa34c8d456ab228021a36  tests/test_gjc_tracker.py
041ac3263dfa91f0fb32d27717160dbb70f3ea78169f5e93bd6668bb7fd27ece  tests/test_gjc_source.py
65e4018f0a543cdb157f93b50ffc0ef87bf583abe3d0341a13e9e5d81b825e7a  tests/test_gjc_config.py
783eda5b747106e2eb493755d641b97215033c947119ca0c9e96153989a09146  tests/test_gjc_cli.py
c9891d0c905a1cb29216a041925a49f36324f7f52fb6275f7c3d86f961cf775a  tests/test_gjc_install.py
1658459d9d40e98270ceee15f88afd212c8ed96b2aafe83e4e1aa6ae552ea2df  tests/test_gjc_autostart.py
```

Initial hashes at review start (03:05 KST) for files that changed during the review, so the coordinator can diff what moved:

```
abe21e6ad2f4fe7f3f4c76063272e79d97f741dab9cfae6bf73fb2356553dbef  pyproject.toml (ruff extend-exclude added only)
7c6073ff808c2118a53c3c0afa57e4fe8841dfddda239d749e1c8daf3f4c1da0  src/orca_keychron_gjc/assets/gjc_hook.ts (rootApis/rootEvents root-switch fix landed mid-review; reviewed final)
e2d1e59856a047252a405114d5c0ee48cd20ac8dc17ec5777e8d25ba93d2d867  src/orca_keychron_gjc/cli.py
671af05423b7507676d289802ff4a69e5eb58e46593b2981ee114562ad6860e5  src/orca_keychron_gjc/config.py
7d1c1469a52e98795fd641829d04db00be95362bf860bc3cb5b027bbcd357941  src/orca_keychron_gjc/gjc_source.py (registry sidecar lock landed mid-review; reviewed final)
```
