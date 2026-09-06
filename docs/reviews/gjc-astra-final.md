# GJC bridge Astra final delta audit

## Final review: no actionable findings

- **Scope**: prior independent full review in `docs/reviews/gjc-astra-high.md` plus the exact subsequent delta and impacted callers; branch `orca-version-check`, `origin/main`, merge base and HEAD `a1e844f3402b6c76dd3014719fc021cf1435a9c7`; introduced implementation remains working-tree scope.
- **Files**: 33 implementation/test/build inputs; 30 byte-identical to the prior reviewed snapshot, 3 changed. No additional product/test files were found outside that inventory in the current Git delta/untracked scope.
- **Findings**: 0 actionable product bugs (critical: 0, high: 0, medium: 0). All four original findings are closed. Introduced bugs only; style/nits/pre-existing issues excluded.
- **Ownership**: only `docs/reviews/gjc-astra-final.md` was written by this reviewer. Task `task_2c3f72be2e69`, dispatch `ctx_e534d218e555`. No product/test edits, subworkers, HID access, global install, provider requests, commits, PRs or external review publication.

This completes the requested full final review by combining the prior independent review with this delta audit. It is not a new whole-codebase review or physical/real-model E2E certification. The broad experimental lint failure below is separate from the clean product-bug result.

## Exact delta and impacted callers

| Changed file | Complete difference from prior reviewed bytes | Result |
|---|---|---|
| `src/orca_keychron_gjc/cli.py` | `_add_orca_option(serve)` becomes `_add_orca_option(serve, saved=True)` at line 134; `serve_command` loads config and resolves socket and Orca command through existing helpers at lines 282–289. | Explicit options retain priority, saved config supplies omitted options, missing config uses platform defaults. Real private listener/control traffic passed all three branches. |
| `tests/test_gjc_cli.py` | One new `test_serve_uses_saved_custom_socket_and_orca_command` at lines 119–149. | Constructor assertion complemented here by actual temporary listener/control checks. |
| `pyproject.toml` | Adds `extend-exclude = ["experiments/gjc-hooks/evidence"]` at line 52. | Only Ruff scope changes; wheel assets, dependencies, entrypoints and package discovery remain identical to prior reviewed bytes. |

Reversing only these edits **in memory** reproduced all three prior SHA256 values exactly; no reconstructed contents were written. `tests/test_gjc_config.py` already has short `/tmp` fixtures in the prior inventory and its current SHA is unchanged, despite the historical earlier failure retained in that report.

Inspected callers/boundaries: parser defaults and `_saved_or_default_socket` / `_saved_or_default_command` (`cli.py:130–177`), setup persistence (`217–225`), run (`240–263`), `_serve` cleanup (`266–279`), status (`318–334`), clear (`344–349`), install (`392–403`), doctor (`416–429`), private config load/save, and source startup/registry ownership. Saved command reuse follows existing run behavior and retains `shlex.split` for explicit strings.

## Original findings: final closure evidence

| Original finding | Status | Current evidence |
|---|---|---|
| #1 fresh readonly facade / root switch | **Closed** | Native loader API ownership at `assets/gjc_hook.ts:132–191`. Current unchanged native fixture suite passes fresh facade `/new` and resume, working/done/shutdown transitions, duplicate loader ordering and same-ID child fencing. `tests/gjc_hook.test.ts:187–255` also parses six transition snapshots through Python protocol. Native context shape is grounded in prior pinned GJC 0.16.4 source review; no real model used. |
| #2 config-created directory permissions | **Closed** | `config.py:28–35,59–73,160–171` uses private GJC leaf. Direct temporary repro saves/reloads config under existing `0755` parent; parent stays `0755`, leaf `0700`, file `0600`, and actual source answers control requests. Config tests cover fresh parent and unsafe directory/symlink rejection. |
| #3 distinct sockets sharing one registry | **Closed** | `gjc_source.py:169–178` acquires registry ownership then reloads state. Direct repro rejects second listener at distinct endpoint with `already owns this registry`; first still answers. Source tests additionally prove unchanged persisted bytes/tombstones after rejection, stale tracker reload on restart, independent registries, and crash/failure ownership release (`tests/test_gjc_source.py:296–483`). |
| #4 serve ignores saved custom socket | **Closed** | `cli.py:282–289` reads saved config. Direct CLI-to-real-source repro verifies saved socket/command, explicit overrides, and absent-config defaults. Selected socket answers and disappears after shutdown. Default socket is absent when custom endpoint is selected. |

## Exact commands and observed results

CWD: `<workspace>`; existing local tools only.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_gjc_cli.py tests/test_gjc_config.py tests/test_gjc_source.py
bun test tests/gjc_hook.test.ts
.venv/bin/ruff check --no-cache .
.venv/bin/ruff check --no-cache src tests
git diff --check
```

| Command | Observed result |
|---|---|
| Targeted Python | **72 passed in 5.20s**, ordinary macOS pytest paths, no special basetemp workaround. |
| Bun native fixtures | **21 passed, 0 failed, 93 expectations, 1.54s**. |
| Broad Ruff `.` | **Exit 1, 8 diagnostics**, all in out-of-review-scope `experiments/gjc-product-qa/harness.py`: EXE001 line 1, I001 lines 9/33, RUF100 lines 33–36, RUF059 line 121. An outstanding broad lint result, not actionable product bugs under this review's scope/filter. Coordinator notified; no edits made. |
| Scoped Ruff `src tests` | **All checks passed**. |
| `git diff --check` | **Exit 0**, no output. |

Coordinator supplied a completed worker run of **273 Python tests**; that is task-brief evidence, not an independently repeated full suite in this audit. Prior package metadata/asset wheel inspection remains applicable because those packaging settings are unchanged. No new wheel/release validation was performed.

### Independent CLI/source reproduction (exact executed script)

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from contextlib import ExitStack
import stat
from orca_keychron_gjc import cli, config
from orca_keychron_gjc.gjc_source import GjcStatusSource, request_control

with TemporaryDirectory(prefix='g-af-', dir='/tmp') as tmp:
    root = Path(tmp)
    parent = root / 'orca-keychron'
    parent.mkdir(mode=0o755)
    parent.chmod(0o755)
    leaf = parent / 'gjc'
    saved_endpoint = leaf / 'custom.sock'
    default_endpoint = leaf / 'bridge.sock'
    override_endpoint = leaf / 'override.sock'
    registry = leaf / 'registry.json'
    with ExitStack() as stack:
        stack.enter_context(patch.object(config, 'config_dir', return_value=leaf))
        saved = config.Config('Fixture', (1,), 72, ('saved-orca',), str(saved_endpoint))
        config.save_config(saved)
        assert config.load_config() == saved
        assert stat.S_IMODE(parent.stat().st_mode) == 0o755
        assert stat.S_IMODE(leaf.stat().st_mode) == 0o700
        assert stat.S_IMODE(config.config_path().stat().st_mode) == 0o600
        print('PASS #2: saved config round trip; existing parent=0755, private leaf=0700, config=0600')
        stack.enter_context(patch.object(cli, 'default_orca_command', return_value=['default-orca']))
        expected = {}
        def inspect_live(source, endpoint):
            assert endpoint == expected['endpoint']
            assert source.command == expected['command']
            source.start()
            try:
                assert request_control(endpoint)['ok'] is True
                if endpoint != default_endpoint:
                    assert not default_endpoint.exists()
                second = GjcStatusSource(leaf / 'second.sock', [], registry_path=registry)
                try:
                    second.start()
                except RuntimeError as error:
                    assert 'already owns this registry' in str(error)
                else:
                    raise AssertionError('second registry writer started')
                finally:
                    second.stop()
                assert request_control(endpoint)['ok'] is True
            finally:
                source.stop()
            assert not endpoint.exists()
        stack.enter_context(patch.object(cli, '_serve', side_effect=inspect_live))
        cases = [
            ('saved', ['serve'], saved_endpoint, ['saved-orca']),
            ('explicit', ['serve', '--socket', str(override_endpoint), '--orca-command', 'override-orca --json'], override_endpoint, ['override-orca', '--json']),
        ]
        for name, argv, endpoint, command in cases:
            expected.update(endpoint=endpoint, command=command)
            assert cli.serve_command(cli.build_parser().parse_args(argv)) == 0
            print(f'PASS #3/#4 {name}: real receiver answers on selected socket, second writer rejected, shutdown clean')
        config.config_path().unlink()
        expected.update(endpoint=default_endpoint, command=['default-orca'])
        assert cli.serve_command(cli.build_parser().parse_args(['serve'])) == 0
        print('PASS #4 missing config: default socket/command selected; real receiver answers')
PY
```

All four PASS lines observed; exit 0. Temporary configuration root and platform command selector were patched; `_serve` was replaced with bounded lifecycle assertions. Source, config persistence, Unix binding, ownership locks, control protocol and stop cleanup were real. No signal-loop, keyboard rendering, actual Orca command execution or provider completion is implied.

## Remaining proof limits, separate from code findings

1. **Real hardware**: physical colors, key-hold focus, USB reconnect, macOS permission prompts and competing HID owners were not exercised here. Mocked device/rendering tests and socket traffic do not prove physical outcomes.
2. **Real model/GJC**: no live model call, real account hook install, real `/new`/resume UI interaction or child-decision conversation. Native fixtures and prior pinned source evidence cover code contracts. Prompt-guided decision-worker compliance and unsupported confirm/input UI observation retain documented limits; these are not new core-code bugs.
3. **Deployment/gate**: no global package, hook or launch service changes, and no published release. Compare final inventory against bytes proposed for approval. Broad experimental Ruff failure must not be described as globally clean lint.

## Final reviewed file SHA256 inventory

Complete 33-file prior-review scope, including introduced product modules/assets, changed shared runtime modules, build inputs and relevant tests. This does not claim every unchanged legacy file was newly reviewed. Later byte changes require corresponding delta audit.

| Path | SHA256 | Delta from prior review |
|---|---|---|
| `pyproject.toml` | `82a76aa74b1b38176a2b84866c342c1fc0c6e1173d67d279750c24904055b46d` | changed |
| `src/orca_keychron/device_lock.py` | `020e98b242119666a654a8892ef2536fdb337ed95ee100ee0960742876643589` | identical |
| `src/orca_keychron/digit_hold.py` | `6ea8113f4bb69a1e1dd483aca7cfa576c32340a2cc59940d6a8c4488793bc1ad` | identical |
| `src/orca_keychron/indicator.py` | `2dbad3d32f2d0b99d49f076a46a1901689045958250ab85c07f1372b882f716a` | identical |
| `src/orca_keychron/keychron_hid.py` | `825a42285cf868581e32cc10e27a0ec993037abad6b14d66b3c7b7bccec52086` | identical |
| `src/orca_keychron/models.py` | `9f99f115e6971d8435a6d37f387361e83dd1323cce0b08aa95f200ef160d6aa5` | identical |
| `src/orca_keychron/rendering.py` | `f1ee96beaf5c105e92e7b526ae97344eec61a17f46716f2f2d8fc8a0d94e77d5` | identical |
| `src/orca_keychron_gjc/__init__.py` | `8b70d42deb2f1ba6784eb0d5f137f96110b97f05439b1a9e6baf3fec49abe52f` | identical |
| `src/orca_keychron_gjc/__main__.py` | `6d8b7d7846a845059d7a3107143f11131f63c5511d669b44085b15ec5e3d2279` | identical |
| `src/orca_keychron_gjc/assets/decision-parent.md` | `7ac06437bbfe7e3e6a941c7865191c531979ce6687936614f6c563a02eacb440` | identical |
| `src/orca_keychron_gjc/assets/decision-worker.md` | `b7c2bae336bb47fa1ad3193e284ab9bfd832bab4e5629a581fa9244168875b21` | identical |
| `src/orca_keychron_gjc/assets/gjc_hook.ts` | `d1f41261a9e669deb6cb9bb578bbd1eb07d5b540d6b50d1311b6b2eb8796211b` | identical |
| `src/orca_keychron_gjc/autostart.py` | `97bdd3e2ef144846f6ef2d1aadf8c401dc677dcb086460f59f1e663a9320dc67` | identical |
| `src/orca_keychron_gjc/cli.py` | `290d3f14c607b932423e702599ee73bb63f6e4ecdc3c825c6433d8f97bc793b0` | changed |
| `src/orca_keychron_gjc/config.py` | `cd57d71d3b2e41471d68edbe252d02b08240c1fe8d2a16425623e809b3eafe95` | identical |
| `src/orca_keychron_gjc/gjc_install.py` | `dd6eaf9d60467a316f81d5866f1929e1794c47b3e322bbdfbdd22a3016699bd5` | identical |
| `src/orca_keychron_gjc/gjc_protocol.py` | `c9cdd55e4f23525338af5fafb4adfb021c1f6ab11bfa03ab16780370e3ab3542` | identical |
| `src/orca_keychron_gjc/gjc_source.py` | `43d6aa2e321d137b0fe2f0939eddc2fa09b566ceb25c60191c14e9db04d9c530` | identical |
| `src/orca_keychron_gjc/gjc_tracker.py` | `30ee0d94db8f2f34af7a56683222acef9fffbca110cfa9bbcd293ad892a758f8` | identical |
| `tests/gjc_hook.test.ts` | `1537cd3d620190b1dd54453d5fd0b253fc7f75eeda4b1b1b7a93e3fc34a0f51f` | identical |
| `tests/test_device_lock.py` | `cc9fc822978ca7a1a8d722bbb09c9340ea49268d770b02bd29277b6572b6dc62` | identical |
| `tests/test_digit_hold.py` | `54450beb092c541e78fd88d87d5cef13e7ff75053786615bd747cc4271e9cdd2` | identical |
| `tests/test_gjc_autostart.py` | `1658459d9d40e98270ceee15f88afd212c8ed96b2aafe83e4e1aa6ae552ea2df` | identical |
| `tests/test_gjc_cli.py` | `783eda5b747106e2eb493755d641b97215033c947119ca0c9e96153989a09146` | changed |
| `tests/test_gjc_config.py` | `65e4018f0a543cdb157f93b50ffc0ef87bf583abe3d0341a13e9e5d81b825e7a` | identical |
| `tests/test_gjc_install.py` | `c9891d0c905a1cb29216a041925a49f36324f7f52fb6275f7c3d86f961cf775a` | identical |
| `tests/test_gjc_protocol.py` | `822cc7e68227bea953f6997c1d3fc18aeec56f21f94b8b9089a2535caf5a80ed` | identical |
| `tests/test_gjc_source.py` | `041ac3263dfa91f0fb32d27717160dbb70f3ea78169f5e93bd6668bb7fd27ece` | identical |
| `tests/test_gjc_tracker.py` | `c0580c29b5cedd74bd50cbf591504ee6373df96deaefa34c8d456ab228021a36` | identical |
| `tests/test_indicator.py` | `bb0171045e0dd711a12e1945ad4acfe7472b3a7c0630949bcf4d988f96b01cf9` | identical |
| `tests/test_keychron_hid.py` | `1e8ae62e44590dd3ce899a88374b1d91467d77c300c12fc85d5134fa58693c49` | identical |
| `tests/test_rendering.py` | `ee45eac4766661e9b731c37f270b35548efdfd105a1d450a37f5a16f21ca776f` | identical |
| `uv.lock` | `89057c0f6921506f41195cd133d60cd11a76235a78d72f27c9fe0bda0a74455b` | identical |

Inventory captured at 2026-09-05T18:44:55.103169+00:00.
