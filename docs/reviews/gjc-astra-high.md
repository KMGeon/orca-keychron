# GJC bridge independent strict review

## Final review

- **Scope**: `origin/main…HEAD` + staged/unstaged + relevant untracked implementation/tests. `origin/main`, merge base, and `HEAD` were all `a1e844f3402b6c76dd3014719fc021cf1435a9c7`; introduced implementation is working-tree scope.
- **Files**: 33 implementation/test/build-input files, inventoried below; contract and pinned upstream files were supporting evidence.
- **Initial findings**: 4 (critical: 0, high: 2, medium: 2). **After concurrent fixes: 1 open medium finding (#4)**; #1–#3 were fixed by other workers and rechecked below.
- **Review assignment**: independent Codex gpt-6-astra HIGH; task `task_ada4f342de03`, dispatch `ctx_836cf8a6b5a5`. Product/test files were not edited. Only this report is owned by this reviewer.
- **Boundary**: reviewed against `docs/gjc-bridge-contract.md` and local GJC 0.16.4 source `/tmp/gajae-code-keychron-research-20260906`. Generated experiments, visualization, `.agents`, and other reviewers' artifacts were excluded.

## Final delta result

The remaining product finding is **#4: `serve` ignores the saved custom socket**, currently `src/orca_keychron_gjc/cli.py:282-285`. The original findings and reproduction evidence below are retained as history; their original line references describe the pre-fix implementation. No product changes were made by this reviewer.

| Initial finding | Final review status | Independently checked evidence |
|---|---|---|
| #1 fresh facade / root switch | Fixed | Native loader API identity replaces manager reference equality; 21 Bun tests pass, including fresh readonly `/new` and resume, duplicate loader ordering, and same-ID headless child fencing. |
| #2 config directory permissions | Fixed | Private `orca-keychron/gjc` leaf is created as `0700`; direct temp reproduction preserves an existing `0755` parent and starts the source successfully. |
| #3 registry writer ownership | Fixed | Registry sidecar lock precedes reload under ownership; direct two-socket reproduction rejects the second writer; added source tests cover restart, crash, stale readers and tombstones. |
| #4 saved socket in serve | Open, medium | Latest `serve_command` still selects `args.socket or socket_path()` while the other callers use saved config. |

### #1 [Fixed during review] 실제 GJC 컨텍스트에서 세션 전환 후 모든 루트 이벤트가 무시됨

GJC에서 `/new`, fork 또는 다른 세션으로 전환하면 `sessionManager` 객체 동일성 검사 때문에 `session_switch`와 이후의 루트 이벤트가 모두 무시됩니다. 실제 0.16.4 `ExtensionRunner.createContext()`는 이벤트마다 새 `createReadonlySessionManager()` facade를 생성하므로 최초 `session_start`의 객체와 같지 않으며, 전환 후에는 session ID도 달라져 이 조기 반환에 걸립니다. 그 결과 이전 루트의 idle/done/failed 상태를 heartbeat로 계속 전송하고 새 작업·질문·정상 종료를 반영하지 않습니다. 최초 facade의 참조 동일성 대신 실제 native hook/session 소유 경계와 전환 이벤트를 이용해 루트를 추적해야 합니다.

- **File**: `src/orca_keychron_gjc/assets/gjc_hook.ts`
- **Lines**: `168-175`
- **Severity**: `high`

Evidence: upstream `extensibility/extensions/runner.ts:628-637` creates the context, `session/session-manager.ts:2505-2540` creates a fresh frozen facade, and `extensibility/hooks/loader.ts:315-337` passes that facade through to the native hook. `session/agent-session.ts:15645-15650` emits the `/new` `session_switch`. The original `tests/gjc_hook.test.ts` fixture reused a single context/manager object and therefore missed this runtime mismatch; the final tests cover fresh facades.

Bounded reproduction executed with Bun, without loading GJC or a provider:

```typescript
import { Publisher } from "./src/orca_keychron_gjc/assets/gjc_hook.ts";
const handlers = new Map<string, Function>();
const publisher = new Publisher({ socketPath: "/tmp/review-absent.sock" }, {
  ORCA_TERMINAL_HANDLE: "t", ORCA_PANE_KEY: "p", ORCA_WORKTREE_ID: "w",
});
publisher.attach({ on: (type, handler) => { handlers.set(type, handler); } });
let id = "root-a";
const context = () => ({ hasUI: true, sessionManager: { getSessionId: () => id } });
handlers.get("session_start")!({}, context());
id = "root-b";
handlers.get("session_switch")!({ reason: "new" }, context());
handlers.get("agent_start")!({}, context());
console.log(publisher.snapshot());
await handlers.get("session_shutdown")!({}, context());
console.log(publisher.snapshot()?.closed);
publisher.dispose();
```

Observed: root remains `root-a`, sole session remains `idle`, `complete=true`, and shutdown prints `false`. Expected: the declared root moves to `root-b`, new work is observed, and root shutdown closes the launch.

### #2 [Fixed during review] 설정 저장이 만든 디렉터리 권한 때문에 기본 실행 경로가 실패함

일반적인 umask `022`에서 `setup`이 처음 설정을 저장하면 이 `mkdir`가 공유 `orca-keychron` 디렉터리를 `0755`로 만듭니다. 이후 `run`/`serve`가 기본 registry를 사용하는 `GjcStatusSource`를 생성하면 `GjcTracker.__init__()`의 `ensure_private_directory()`가 해당 디렉터리를 거부해 `PermissionError`로 종료합니다. 기존 Orca 설정 저장도 같은 공유 디렉터리를 `0755`로 만들기 때문에 기존 사용자에게도 발생합니다. 새 GJC 전용 상태 디렉터리를 `0700`으로 마련하는 등의 방식으로, 설정·registry·socket의 경로 및 권한 계약을 함께 맞춰야 합니다.

- **File**: `src/orca_keychron_gjc/config.py`
- **Lines**: `124-126`
- **Severity**: `high`

Proven original callers: `cli.setup_command → save_config`, followed by `cli.run_command/serve_command → GjcStatusSource.__init__ → GjcTracker.__init__ → ensure_private_directory`. `gjc_tracker.py:62-71` rejects any group/other permission. Existing `src/orca_keychron/config.py:96` uses the same default mkdir permissions; the original GJC autostart path could also create the shared parent through its logs directory.

Bounded reproduction executed with `PYTHONPATH=src .venv/bin/python`, using only a temporary directory:

```python
import tempfile
from pathlib import Path
from orca_keychron_gjc.config import Config, save_config
from orca_keychron_gjc.gjc_source import GjcStatusSource
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory) / "orca-keychron"
    save_config(Config("test", (1,), 10), root / "gjc-config.json")
    print(oct(root.stat().st_mode & 0o777))
    GjcStatusSource(root / "gjc.sock", [], registry_path=root / "gjc-registry.json")
```

Observed: `0o755`, then `PermissionError: A private user-owned directory is required`. The failure happens in construction, before HID or a listener starts. The existing round-trip test checks only the JSON file's `0600` mode and uses an already-private pytest directory.

### #3 [Fixed during review] 서로 다른 소켓의 수신기가 동일 registry를 덮어씀

기본 `run` 또는 `serve`가 실행 중일 때 `serve --socket <다른 경로>`를 실행하면 두 수신기가 같은 기본 registry를 사용하면서도 각각 다른 socket lock을 획득하여 동시에 시작됩니다. 각 tracker의 `_persist()`는 자신이 아는 전체 launches/retired 목록으로 파일을 교체하므로, 다른 수신기의 슬롯과 clear tombstone을 지웁니다. 별도 임시 소켓 두 개에 각각 launch를 전송한 재현에서도 양쪽 live status에는 한 개씩 있지만 디스크에는 마지막 수신기의 launch 한 개만 남았습니다. registry를 읽고 복구하기 전부터 수신기 종료까지 registry 자체의 독점 소유권을 확보하거나 소켓별 registry를 분리해야 합니다.

- **File**: `src/orca_keychron_gjc/gjc_source.py`
- **Lines**: `149-155`
- **Severity**: `medium`

Proven callers: `cli.run_command` and `cli.serve_command` independently accept `--socket`, but both pass `args.registry or registry_path()`. `GjcTracker._persist()` at `gjc_tracker.py:229-264` replaces the full file. Device ownership does not prevent this path because `serve` is intentionally receiver-only.

Reproduction procedure executed in a private `/tmp/gjc-review-*` directory: construct A at `a.sock` and B at `b.sock`, both with `registry_path=registry.json`; start both; connect one AF_UNIX client to each and send independent valid `tests/test_gjc_protocol.py:frame()` snapshots; wait up to two seconds for each source's status; read the registry; close both clients and stop both sources.

Observed IDs:

```text
a live:    [ce5fdd8f-61d3-4d3e-a304-e98638592dae]
b live:    [7a23cd74-bd1c-4beb-8301-03111b606385]
persisted: [7a23cd74-bd1c-4beb-8301-03111b606385]
```

This is loss of persisted identity/slot data, not a merely stale display state. A later reconnect can repopulate a row but does not restore its previous assignment or a lost retired identity.

### #4 `serve`가 저장된 사용자 지정 소켓을 무시함

`setup --socket <사용자 지정 경로>` 후 `install`과 `serve`를 기본 옵션으로 실행하면, 설치된 훅과 `status`는 저장된 소켓을 사용하지만 `serve`만 기본 소켓에 바인딩합니다. 이 명령은 `load_config()`와 `_saved_or_default_socket()`을 거치지 않아 publisher가 연결되지 않고 `status`도 수신기를 찾지 못합니다. `run`, `install`, `status`, `doctor`와 같은 소켓 설정 해석 경로를 사용해야 합니다.

- **File**: `src/orca_keychron_gjc/cli.py`
- **Lines**: `282-285` (current delta)
- **Severity**: `medium`

Bounded boundary reproduction: patch `cli.load_config` to return `Config(..., socket_path="/tmp/custom-gjc.sock")`, patch `cli.socket_path` to `/tmp/default-gjc.sock`, replace `GjcStatusSource` and `_serve` with `unittest.mock` mocks, then call `serve_command(build_parser().parse_args(["serve"]))`. No hardware, real service, or account configuration is invoked.

```text
saved socket:             /tmp/custom-gjc.sock
actual receiver socket:   /tmp/default-gjc.sock
status/install selected:  /tmp/custom-gjc.sock
```

## Verification and review coverage

1. Initial `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_gjc_*.py tests/test_device_lock.py tests/test_digit_hold.py tests/test_indicator.py tests/test_keychron_hid.py tests/test_rendering.py`: **211 passed in 4.74s**. After concurrent fixes, the same command returned **222 passed / 3 failed in 6.38s**: new `test_gjc_config.py` cases use long default macOS pytest temp paths exceeding the protocol's 103-byte socket limit, so validation preempts their intended directory assertions. This test-fixture issue was reported to the coordinator; it is separate from the remaining product finding. Re-running only `tests/test_gjc_config.py` with a fresh short `/tmp/g-r-*/p` `--basetemp` passed all **13 tests in 0.04s**, confirming the path-length cause without changing test files. Real process-lock tests use private temporary lock files; HID and launchctl boundaries are mocked.
2. Initial `bun test tests/gjc_hook.test.ts`: **17 passed, 0 failed, 71 expectations**; after the native root fix, **21 passed, 0 failed, 93 expectations**. Includes full snapshot/reconnect/closure socket tests, fresh readonly facades and root ownership, ask correlation, child decisions, retry, bounds, and Python protocol compatibility.
3. Offline wheel build from a temporary copy of `src`, `pyproject.toml`, `README.md`, and `LICENSE`: `uv build --offline --wheel --out-dir <temp>/wheel <temp>/project` succeeded. ZIP inspection confirmed `gjc_hook.ts`, `decision-parent.md`, `decision-worker.md` under `orca_keychron_gjc/assets/` and both correct console entrypoints. The temporary copy has no Git metadata, so version `0.1.0` is the documented SCM fallback; this was an asset/entrypoint check, not a release build.
4. Upstream source validates native `hooks/pre/<name>.ts` discovery and runtime-event adaptation, `yield.details.{status,data,error}`, single-question `ask.details.{selectedOptions,customInput,...}`, batch `ask.details.results[].id`, and fresh readonly context facade behavior. Named-agent tools array and `forkContext: allowed` parsing are supported. Existing lock, coalescing, lease, stale-sequence, priority, and explicit-clear handling were inspected; no additional qualifying finding was identified there beyond registry ownership.
5. No live GJC provider/model request, real account hook install, real autostart mutation, keyboard access, commit, PR, or external review publication was performed. Unsupported extension confirm/input UI observation and prompt-guided decision-worker compliance are documented limits, not findings requiring a GJC core change. This review does not claim physical or real-model E2E completion.

## Snapshot and final delta audit

The SHA256 inventory below identifies the reviewed product/test/build-input bytes. CLI and installer workers were active during review; use the inventory to identify later changes, then review those deltas before a final ship decision. Findings were sent early to the coordinator as orchestration status messages; subsequent fixes are not implicitly approved by this report.

| Path | SHA256 |
|---|---|
| `pyproject.toml` | `abe21e6ad2f4fe7f3f4c76063272e79d97f741dab9cfae6bf73fb2356553dbef` |
| `src/orca_keychron/device_lock.py` | `020e98b242119666a654a8892ef2536fdb337ed95ee100ee0960742876643589` |
| `src/orca_keychron/digit_hold.py` | `6ea8113f4bb69a1e1dd483aca7cfa576c32340a2cc59940d6a8c4488793bc1ad` |
| `src/orca_keychron/indicator.py` | `2dbad3d32f2d0b99d49f076a46a1901689045958250ab85c07f1372b882f716a` |
| `src/orca_keychron/keychron_hid.py` | `825a42285cf868581e32cc10e27a0ec993037abad6b14d66b3c7b7bccec52086` |
| `src/orca_keychron/models.py` | `9f99f115e6971d8435a6d37f387361e83dd1323cce0b08aa95f200ef160d6aa5` |
| `src/orca_keychron/rendering.py` | `f1ee96beaf5c105e92e7b526ae97344eec61a17f46716f2f2d8fc8a0d94e77d5` |
| `src/orca_keychron_gjc/__init__.py` | `8b70d42deb2f1ba6784eb0d5f137f96110b97f05439b1a9e6baf3fec49abe52f` |
| `src/orca_keychron_gjc/__main__.py` | `6d8b7d7846a845059d7a3107143f11131f63c5511d669b44085b15ec5e3d2279` |
| `src/orca_keychron_gjc/assets/decision-parent.md` | `7ac06437bbfe7e3e6a941c7865191c531979ce6687936614f6c563a02eacb440` |
| `src/orca_keychron_gjc/assets/decision-worker.md` | `b7c2bae336bb47fa1ad3193e284ab9bfd832bab4e5629a581fa9244168875b21` |
| `src/orca_keychron_gjc/assets/gjc_hook.ts` | `d1f41261a9e669deb6cb9bb578bbd1eb07d5b540d6b50d1311b6b2eb8796211b` |
| `src/orca_keychron_gjc/autostart.py` | `97bdd3e2ef144846f6ef2d1aadf8c401dc677dcb086460f59f1e663a9320dc67` |
| `src/orca_keychron_gjc/cli.py` | `d91de1f7f793b0424d5275b548c0e2b7f29e2591b4427a40d273b8358b9b3806` |
| `src/orca_keychron_gjc/config.py` | `cd57d71d3b2e41471d68edbe252d02b08240c1fe8d2a16425623e809b3eafe95` |
| `src/orca_keychron_gjc/gjc_install.py` | `dd6eaf9d60467a316f81d5866f1929e1794c47b3e322bbdfbdd22a3016699bd5` |
| `src/orca_keychron_gjc/gjc_protocol.py` | `c9cdd55e4f23525338af5fafb4adfb021c1f6ab11bfa03ab16780370e3ab3542` |
| `src/orca_keychron_gjc/gjc_source.py` | `43d6aa2e321d137b0fe2f0939eddc2fa09b566ceb25c60191c14e9db04d9c530` |
| `src/orca_keychron_gjc/gjc_tracker.py` | `30ee0d94db8f2f34af7a56683222acef9fffbca110cfa9bbcd293ad892a758f8` |
| `tests/gjc_hook.test.ts` | `1537cd3d620190b1dd54453d5fd0b253fc7f75eeda4b1b1b7a93e3fc34a0f51f` |
| `tests/test_device_lock.py` | `cc9fc822978ca7a1a8d722bbb09c9340ea49268d770b02bd29277b6572b6dc62` |
| `tests/test_digit_hold.py` | `54450beb092c541e78fd88d87d5cef13e7ff75053786615bd747cc4271e9cdd2` |
| `tests/test_gjc_autostart.py` | `1658459d9d40e98270ceee15f88afd212c8ed96b2aafe83e4e1aa6ae552ea2df` |
| `tests/test_gjc_cli.py` | `573d2b09fff8545410a4285b9aaae5a91ef080804586aacc02ca6a73b5deb6f6` |
| `tests/test_gjc_config.py` | `65e4018f0a543cdb157f93b50ffc0ef87bf583abe3d0341a13e9e5d81b825e7a` |
| `tests/test_gjc_install.py` | `c9891d0c905a1cb29216a041925a49f36324f7f52fb6275f7c3d86f961cf775a` |
| `tests/test_gjc_protocol.py` | `822cc7e68227bea953f6997c1d3fc18aeec56f21f94b8b9089a2535caf5a80ed` |
| `tests/test_gjc_source.py` | `041ac3263dfa91f0fb32d27717160dbb70f3ea78169f5e93bd6668bb7fd27ece` |
| `tests/test_gjc_tracker.py` | `c0580c29b5cedd74bd50cbf591504ee6373df96deaefa34c8d456ab228021a36` |
| `tests/test_indicator.py` | `bb0171045e0dd711a12e1945ad4acfe7472b3a7c0630949bcf4d988f96b01cf9` |
| `tests/test_keychron_hid.py` | `1e8ae62e44590dd3ce899a88374b1d91467d77c300c12fc85d5134fa58693c49` |
| `tests/test_rendering.py` | `ee45eac4766661e9b731c37f270b35548efdfd105a1d450a37f5a16f21ca776f` |
| `uv.lock` | `89057c0f6921506f41195cd133d60cd11a76235a78d72f27c9fe0bda0a74455b` |

Inventory refreshed after reviewing the concurrent fixes at 2026-09-05T18:37:35.125491+00:00. Later bytes require a delta audit.
