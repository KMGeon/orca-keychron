# Repeatable GJC 0.16.4 second-audit E2E

This suite launches unmodified installed `gjc/0.16.4` directly in fresh Orca-owned
terminals. It uses the existing read-only `experiments/gjc-product-qa/harness.py`
loopback provider, the actual installed product hook, `GjcStatusSource`, tracker,
and renderer, plus the existing parent-decision fixture's correlation contract.

The runner owns every terminal it creates and closes those exact handles in a
`finally` block. Runtime state must be a fresh canonical `/private/tmp/...` path;
profiles, sessions, provider, Unix socket, and registry are isolated per run.

Run the fast independent oracle first:

```sh
python3 -m pytest -q tests/e2e/test_gjc_e2e_audit.py
```

Run a source-tree baseline while development is still changing:

```sh
python3 experiments/gjc-e2e-audit/run_audit.py \
  --evidence experiments/gjc-e2e-audit/evidence/baseline.json
```

Run the release audit only after the coordinator freezes source and supplies the
final wheel. The runner installs it without dependencies into an isolated venv,
then uses that venv for product installation, receiving, tracking, and rendering:

```sh
python3 experiments/gjc-e2e-audit/run_audit.py \
  --wheel /absolute/path/to/orca_keychron-final.whl \
  --evidence experiments/gjc-e2e-audit/evidence/final.json
```

Assertions are requirement-derived: two independent launches and stable slots;
initial receiver absence/reconnect; restart/backfill; killed producer unknown;
normal completion/failure/cancellation; duplicate user/project hook de-duplication;
ten working children plus one waiting decision and orange rendering; two correlated
decisions with proper actual-child resume; and `/new`, `/resume`, `/exit` lifetime.

Evidence is metadata-only. Real model/provider compliance, physical keyboard/HID,
global installation, and login services are deliberately unproven and unexercised.
