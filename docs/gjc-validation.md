# GJC package validation

This is the historical first validation snapshot (298 Python / 21 Bun tests).
For subsequent fixes, expanded requirements coverage and current frozen-byte results,
see [the second test audit](testing/gjc-second-audit.md). The evidence below is preserved
and must not be treated as validation of later source edits.

## Release gate result: PASS

Validation completed on 2026-09-06 KST against the settled working-tree product bytes. The
software/package gate passes: both Python runtimes pass the complete source suite, Ruff and the
native TypeScript fixtures pass, the wheel and sdist pass strict metadata checks, and a fresh
Python 3.9 environment installs and runs the wheel without editable or checkout imports.

This gate performed no global installation or service mutation, no HID access, no physical input,
and no live model/provider request. All mutable HOME, agent, registry, and socket paths were under
`/tmp/gjc-validation.K3OypM`.

## Failures discovered and closed

1. The first fresh `/usr/bin/python3` 3.9 wheel install selected yanked `pyobjc-core==12.0`, whose
   metadata advertised Python 3.9 support, then failed compiling with
   `-Wdefault-const-init-var-unsafe`. The complete original failure remains in
   `/tmp/gjc-validation.K3OypM/pip-install.log`. This matches upstream
   [PyObjC issue 661](https://github.com/ronaldoussoren/pyobjc/issues/661).
2. `pyproject.toml` now constrains only the directly consumed
   `pyobjc-framework-ApplicationServices` and `pyobjc-framework-Quartz` to `<12` on Darwin with
   Python `<3.10`; Python 3.10+, non-Darwin platforms, and `requires-python >=3.9` are unchanged.
   `uv.lock` resolves the Python 3.9 framework graph, including Core, Cocoa, and CoreText, to 11.1.
3. The first actual Python 3.9 suite after dependency installation exposed a separate transport
   boundary: `request_control()` leaked Python 3.9's distinct `socket.timeout`. The preserved log
   `/tmp/gjc-validation.K3OypM/pytest-py39-fixed.log` records `1 failed, 276 passed`. The client now
   raises builtin `TimeoutError` with the transport exception retained as its cause.
4. Independent release review then reproduced floating-point cancellation at the exact eight-second
   tracker lease deadline. The authorized absolute comparison
   `received_at <= now < received_at + lease_seconds` and deterministic fractional-clock regression
   close it without tolerance or sleeps. The final actual Python 3.9 suite passes 298/298.

## Final source/runtime checks

| Check | Runtime | Result | Evidence |
|---|---|---:|---|
| Complete pytest suite | Python 3.13.5 | 298 passed in 8.35s | `/tmp/gjc-validation.K3OypM/pytest-py313-final-gate.log` |
| Complete pytest suite | `/usr/bin/python3` 3.9.6 | 298 passed in 8.54s | `/tmp/gjc-validation.K3OypM/pytest-py39-wheel-env-gate.log` |
| Ruff, complete checkout scope | Ruff via `uv run` | All checks passed | `/tmp/gjc-validation.K3OypM/ruff-final-gate.log` |
| GJC native fixtures | Bun 1.4.0 | 21 passed, 0 failed, 93 expectations | `/tmp/gjc-validation.K3OypM/bun-final-gate.log` |
| Lock consistency | `uv lock --check --offline` | Resolved 29 packages, exit 0 | `/tmp/gjc-validation.K3OypM/uv-lock-check-gate.log` |
| Whitespace | `git diff --check` | exit 0 | `/tmp/gjc-validation.K3OypM/diff-check-final-gate.log` |

The Python 3.9 full-suite command ran the checkout tests under the actual interpreter and therefore
used `pyproject.toml`'s intentional `pythonpath = ["src"]`. Wheel runtime evidence is separate below
and was run outside the repository with empty `PYTHONPATH`, proving it did not accidentally import
the checkout.

```sh
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /tmp/gjc-validation.K3OypM/py39-gate/bin/python \
  -m pytest -q -p no:cacheprovider
uv run ruff check --no-cache .
bun test tests/gjc_hook.test.ts
uv lock --check --offline
git diff --check
```

Ruff's recorded experimental evidence exclusion is active through
`extend-exclude = ["experiments/gjc-hooks/evidence"]`; the remaining source, tests, experiments,
and QA harness were checked by the broad `.` command.

## Built distributions

Command:

```sh
uv build --out-dir /tmp/gjc-validation.K3OypM/dist-gate-final
uvx twine check --strict /tmp/gjc-validation.K3OypM/dist-gate-final/*
```

Both distributions passed `twine check --strict`.

| Artifact | SHA-256 |
|---|---|
| `orca_keychron-0.1.2.dev1+ga1e844f34.d20260905-py3-none-any.whl` | `ee6cd41f3c40efeb4329e5c2e6bc87a058654265e0d2b9f0eead1b41336937c3` |
| `orca_keychron-0.1.2.dev1+ga1e844f34.d20260905.tar.gz` | `1bba0242ff83972d3e76e1fe625e635d6531bec9ed2d7a273f2cc0fa16e00fdb` |

Wheel and sdist each contain 15 `orca_keychron` Python files, 9 `orca_keychron_gjc` Python files,
and the same 3 GJC assets. All 27 wheel package Python/asset members are byte-identical to their
settled source inputs. Entry points are:

```ini
[console_scripts]
orca-keychron = orca_keychron.cli:main
orca-keychron-gjc = orca_keychron_gjc.cli:main
```

The actual packaged assets and their wheel/source-identical hashes are:

| Asset | SHA-256 |
|---|---|
| `decision-parent.md` | `7ac06437bbfe7e3e6a941c7865191c531979ce6687936614f6c563a02eacb440` |
| `decision-worker.md` | `b7c2bae336bb47fa1ad3193e284ab9bfd832bab4e5629a581fa9244168875b21` |
| `gjc_hook.ts` | `d1f41261a9e669deb6cb9bb578bbd1eb07d5b540d6b50d1311b6b2eb8796211b` |

Wheel metadata retains `Requires-Python: >=3.9` and contains exactly these compatibility additions:

```text
Requires-Dist: pyobjc-framework-ApplicationServices<12; sys_platform == "darwin" and python_version < "3.10"
Requires-Dist: pyobjc-framework-Quartz<12; sys_platform == "darwin" and python_version < "3.10"
```

## Fresh Python 3.9 wheel install and runtime

A new venv was created from the actual `/usr/bin/python3` (3.9.6), then the final wheel was installed
directly without a constraints file or `--no-deps`:

```sh
/usr/bin/python3 -m venv /tmp/gjc-validation.K3OypM/py39-gate
/tmp/gjc-validation.K3OypM/py39-gate/bin/python -m pip install \
  /tmp/gjc-validation.K3OypM/dist-gate-final/*.whl
/tmp/gjc-validation.K3OypM/py39-gate/bin/python -m pip check
```

Installation succeeded and `pip check` reported no broken requirements. Resolution selected
`pynput==1.7.8` plus PyObjC Core, ApplicationServices, Quartz, Cocoa, and CoreText all at 11.1.
The wheel import smoke ran from `/tmp` under `env -i`, with empty `PYTHONPATH` and isolated HOME.
Observed module paths were:

```text
/private/tmp/gjc-validation.K3OypM/py39-gate/lib/python3.9/site-packages/orca_keychron/__init__.py
/private/tmp/gjc-validation.K3OypM/py39-gate/lib/python3.9/site-packages/orca_keychron_gjc/__init__.py
```

Both installed commands returned the package version and rendered help successfully:

```text
orca-keychron 0.1.2.dev1+ga1e844f34.d20260905
orca-keychron-gjc 0.1.2.dev1+ga1e844f34.d20260905
```

The GJC command help exposed `setup`, `run`, `serve`, `status`, `clear`, `install`, `uninstall`,
`doctor`, and `autostart`.

## Isolated hook and bridge smoke

The installed wheel was exercised against GJC 0.16.4 with:

- HOME: `/tmp/gjc-validation.K3OypM/home-gate`
- agent profile: `/tmp/gjc-validation.K3OypM/agent-gate`
- socket/registry roots: `/tmp/gjc-validation.K3OypM/runtime-gate` and
  `/tmp/gjc-validation.K3OypM/runtime-cli-gate2`

`install` created the four managed files, reported `installed=true`, `can_apply=true`, and no
recovery requirement. `doctor` identified GJC 0.16.4 as supported and the isolated installation as
healthy. `uninstall` removed all managed hook/release/decision files and reported `removed=true`;
only the private reusable `.orca-keychron/install.lock` remained in the isolated agent root.

The local receiver smoke used a real AF_UNIX listener and the installed CLI/API. It proved a valid
snapshot is received, CLI `status --json` uses the live endpoint, connected-launch clear returns the
typed `clear_refused/connected` response and retains the launch, the same launch clears only after
disconnect plus positive child-process death, and source shutdown removes the socket. Evidence:
`/tmp/gjc-validation.K3OypM/receiver-cli-smoke-gate.log`.

## Reviewed-byte boundary

Comparison with the earlier 33-file `docs/reviews/gjc-astra-final.md` snapshot shows eight expected,
authorized deltas: `pyproject.toml`, `uv.lock`, CLI/source/tracker, and their three test files. The
subsequent independent release review inventory in
`docs/reviews/gjc-astra-release-hashes.json` covers 49 source, asset, test, and build inputs and
matches the final gate bytes with zero missing or mismatched hashes. The inventory file SHA-256 is
`e4e0c0cf593d67b31cedc387bfc9f93928b09b3374ab4e030bece4e88bf64c49`.

Key final changed-input hashes are:

| Input | SHA-256 |
|---|---|
| `pyproject.toml` | `241cb2e0a3f5b80d274f9bb4aed70ccce649d0678088bf36a0beb6ba283bc217` |
| `uv.lock` | `8eba354293dd531d7049af4290957df04042c777b21fd91dd443f5d750c64761` |
| `src/orca_keychron_gjc/cli.py` | `ee098b9bc2cae1cd8a7ad613e6c4982030e4b78733b85b2520184093202688bc` |
| `src/orca_keychron_gjc/gjc_source.py` | `8276e593b06b40f75193d30826468978ffcac44ea0b5d03977317eb32f4b7493` |
| `src/orca_keychron_gjc/gjc_tracker.py` | `8c98f7a07761f4ebbbc72c4117e882ef3090040425dc1a99d1d43643423ca5f3` |

## Proven and unproven boundary

Proven here: source suites on Python 3.13.5 and actual Python 3.9.6; deterministic Bun hook behavior;
build metadata and payloads; clean fresh wheel dependency resolution; installed CLI entry points;
reversible isolated hook lifecycle; real local socket/status/safe-clear behavior; and byte equality
with the independent final release inventory.

Not performed here: global package/hook/autostart installation, launch service mutation, real HID
or keyboard access, physical/optical key validation, permission prompts, USB reconnect/competing HID
owners, live model/provider calls, release upload, deployment, or a published PR. Hardware ACK,
lighting restoration/navigation, and actual GJC root-switch evidence exist in separate project
reports, but are not reclassified as executions by this package validator.
