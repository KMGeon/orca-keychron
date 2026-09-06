# GJC 0.16.4 restart/successor audit

Verdict: **PASS** for `GJC-DECISION-RESTART`, `GJC-LAUNCH-LIFECYCLE`, and
`GJC-0.16.4` on the final frozen wheel. The machine-readable final evidence is
[`evidence/final.json`](evidence/final.json) (also retained at
`/private/tmp/gjc-successor-final-07b38aff/verdict.json`) (SHA-256
`68593bd56a5bd2a5380dc2cc1f94057d582ec25e923084251fed2bbb364b6d97`).

## Final input and runtime provenance

- Frozen wheel:
  `/tmp/gjc-test-audit/final-dist/orca_keychron-0.1.2.dev1+ga1e844f34.d20260905-py3-none-any.whl`,
  expected and observed SHA-256
  `134977ddf53a54903f9af9471cac8b511605539529193bb049f5c6a1cb56e48d`.
- The harness safely extracted the wheel into its private runtime and imported
  the installer/bridge from that payload; it did not claim a pip/global wheel
  installation. The installer then created the isolated GJC native hook.
- Wheel hook payload and installed immutable hook matched at SHA-256
  `e29cad5aa8749bff21c1f4c213df96cbe4e6019fa19a22162aac8bf3f822cea1`.
- Workspace hook SHA-256 was the same before and after the run, proving this
  audit made no product/native/upstream edit.
- Runtime was actual unmodified `gjc/0.16.4`, two exact Orca terminals, the
  actual product receiver/tracker, and a loopback deterministic fixture model.

## Requirement-derived cases

| Case | Expected outcome | Final observation |
|---|---|---|
| Launch A actual decision | Actual task child yields the exact decision and parent reads its full `agent://` result | Actual predecessor `0-predecessor`; request `req_restart`; checkpoint `checkpoint-restart-v1` |
| Unresolved boundary | Status remains waiting until the real parent answer, then pending count reaches zero | Before answer: `waiting`, 2 pending; after `Continue with A`: 0 pending |
| Process boundary | Launch A never resumes the child and closes; launch B has different launch/PID identity | A `3f210a4a...`, PID 27831, closed sequence 39; B `83535edf...`, PID 28139 |
| Stale resume and successor | Fresh GJC rejects predecessor and creates a different actual child | Native resume receipt was `not_found`; successor was `0-successor` |
| Correlation and outcome | Successor validates request, checkpoint, answer, and continuation; final result explicitly says successor | All four checks true; `answerConsumed=true`; `outcome=successor`; product status `done`, 0 pending |

The actual GJC stale-resume receipt reports `not_found` inside a successful
tool transport (`isError=false`). This is still a semantic rejection and was
not represented as an exception or as successful resume.

## Added tests and harness defect fixed

Normal pytest collection now contains seven fixture regressions in
`tests/test_gjc_successor_fixture.py`: actual child/envelope gating, stale
resume ordering, successor identity collision, native `not_found`, wrong
checkpoint, fully correlated success, and pre/post-answer lifecycle separation.

The first baseline exposed one owned harness defect: its rejection classifier
recognized `not found` but not GJC's actual `not_found` spelling. No product
file was implicated or edited.

```sh
# RED (before owned harness fix)
python3 -m pytest -q tests/test_gjc_successor_fixture.py -k not_found
# 1 failed: old_resume_failed(actual_gjc_receipt) was False

# GREEN
python3 -m pytest -q tests/test_gjc_successor_fixture.py
# 7 passed
```

Final checks:

```sh
/tmp/gjc-test-audit/final-py313/bin/python -m ruff check \
  experiments/gjc-successor-audit tests/test_gjc_successor_fixture.py
# All checks passed!

/Library/Developer/CommandLineTools/usr/bin/python3 -m py_compile \
  experiments/gjc-successor-audit/harness.py tests/test_gjc_successor_fixture.py
# exit 0 on Python 3.9.6
```

Owned input hashes were
`harness.py=7b31beb15defa03c6a72879d92d9a87283a2e636a2655136f89a798b57419eb2`,
`README.md=30fcc618ea1797a6b492f21cda87a7bd57f4423d5f27c029579c5896f71654de`,
and
`tests/test_gjc_successor_fixture.py=a4fb8fa3a19922c22d3cc9e58e1b0e88aa9139add5ec631a3b0b3c1263d9029f`.

## Cleanup and unresolved limits

Both owned GJC terminals returned `ptyKilled=true` after graceful `/exit`.
Receiver PID 27680, provider PID 27679, and exact-agent-dir broker PID 27883
were stopped; no owned broker PID or Unix socket remained. The runtime is
retained only as synthetic audit evidence.

The pass does not prove that the product automatically persists answers: the
fixture explicitly carried the known checkpoint and actual answer between
processes. It also does not prove original-child resume, real-model instruction
compliance, a real provider account, physical HID/keyboard behavior, global
installation/services, or compatibility beyond GJC 0.16.4.
