# GJC 0.16.4 actual-runtime second audit

## Result

The final frozen-wheel run passed in 53.336 seconds. It exercised the unmodified
installed `gjc/0.16.4` executable in fresh Orca terminals, the installed product
hook, `GjcStatusSource`, `GjcTracker`, and renderer against the deterministic
loopback provider. Product source was unchanged across the run
(`f2094c535515889e7c010824ab1348c5d60a9f00bbda1eba122907ac9536dda9`).

The audited wheel was
`/tmp/gjc-test-audit/final-dist/orca_keychron-0.1.2.dev1+ga1e844f34.d20260905-py3-none-any.whl`
with SHA-256
`134977ddf53a54903f9af9471cac8b511605539529193bb049f5c6a1cb56e48d`.
The installed hook matched the source hook at
`e29cad5aa8749bff21c1f4c213df96cbe4e6019fa19a22162aac8bf3f822cea1`.

## Requirement cases

| Requirement | Actual-runtime assertion | Final result |
| --- | --- | --- |
| REQ-RUNTIME-1, REQ-INSTALL-1/2 | GJC 0.16.4 direct launch; actual installed hook; duplicate user/project installation has one publisher and launch | PASS |
| REQ-IDENTITY-1, REQ-STATE-3 | Two independent roots receive distinct stable slots; receiver restart restores unknown rows, backfill reconnects without changing slots; killed producer becomes unknown | PASS |
| REQ-STATE-1/2 | Historical transition contains exactly 10 working, 1 waiting, and 1 done sessions with one pending request; that exact producer/launch/sequence is replayed through the installed parser, tracker, and renderer and is orange | PASS at sequence 117 |
| REQ-DECISION-0/1/2 | Two distinct parent decisions use two actual child IDs, retain one pending child after the first answer, do not cross-answer, and each resume/completion is unique | PASS |
| REQ-LIFE-1/2/3/4 | Success, failure, cancellation, initial receiver absence/reconnect, `/new`, `/resume`, `/exit`, and explicit close lifecycle | PASS |

The final evidence records 387 metadata-only wire frames, eight actual GJC pane
identities, the two actual decision child IDs, provenance hashes, and cleanup.
No question, prompt, answer, or tool-result content was recorded.

## A7 oracle correction

The earlier run in `evidence/final-a7-oracle-rejected.json` is retained only as
historical evidence of an invalid PASS. Its mass assertion combined a historical
12-agent frame with a later live orange status, so the observations were not
temporally tied.

`test_mass_oracle_rejects_later_orange_frame_with_different_count` is the
regression: historical sequence 10 with 12 sessions plus sequence 11 with
`agentCount=1` and orange must fail. The corrected runtime selects exactly one
receiver-observed frame and replays its metadata through the installed wheel's
`parse_snapshot`, `GjcTracker.apply/status/indicators`, and `render_zone`; the
oracle requires producer ID, launch ID, sequence, count, pending count, state,
connectivity, and color to agree. Astra independently confirmed the direct
installed replay before the final run.

## Reproduction and gates

```sh
/tmp/gjc-test-audit/final-py313/bin/python -m pytest -q \
  tests/e2e/test_gjc_e2e_audit.py
# 10 passed

/tmp/gjc-test-audit/final-py313/bin/ruff check \
  experiments/gjc-e2e-audit tests/e2e
# All checks passed

/tmp/gjc-test-audit/final-py313/bin/python \
  experiments/gjc-e2e-audit/run_audit.py \
  --wheel /tmp/gjc-test-audit/final-dist/orca_keychron-0.1.2.dev1+ga1e844f34.d20260905-py3-none-any.whl \
  --evidence experiments/gjc-e2e-audit/evidence/final.json
# {"verdict":"pass", ...}
```

The final cleanup closed all 11 owned Orca terminals, terminated eight owned
broker processes, removed the canonical `/private/tmp` runtime, and found no
owned process or listener remaining. No product file was edited; the proven A7
defect was in this audit oracle and is covered by the new regression.

## Owned artifact hashes

| Artifact | SHA-256 |
| --- | --- |
| `audit_support.py` | `1c623ce11f01b17f0d32c7f746f717b41fff43b818a8b1b481e8ecdcec373f17` |
| `runtime_components.py` | `a6c9562ccc85df4c0367454695da3741ba2b7c6a2765967a1c851e138a99a72d` |
| `run_audit.py` | `e1cb26db58fce4dd934c75642ff122a262d33b95dc2b2e20923b499559decfc2` |
| `README.md` | `42fe8872a7cba599ad87d11d8cae37d481b661673acdc52e6147cffa039824ad` |
| `test_gjc_e2e_audit.py` | `0d73e18dd204e6cf1393e04fbe8f498a74309764ca572ae49808eee3c2158663` |
| `evidence/final.json` | `0c376f80a542feb12d212a187c1f4750b87a526b23e5c0e470370de5e0cb2b69` |

## Unresolved limitations

Real model/provider instruction compliance remains unproven. Physical keyboard,
HID, visible LED color, global installation, and login services were not exercised.
Support claims remain limited to GJC 0.16.4, and exact-frame color evidence is an
explicit installed-product metadata replay because the live display may advance
before a transient historical frame is inspected.
