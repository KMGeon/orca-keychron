# GJC Q65 Max hardware validation

## Result

The bounded real-HID smoke succeeded on `Keychron Q65 Max`. The run used the
checkout's actual `GjcTracker`, `render_zone`, and `KeychronDevice`; all lighting
configuration and all five 72-LED frames received firmware acknowledgements.

This is firmware-response validation, not optical validation. Nobody confirmed
the colors by sight and no physical key was pressed. A separate check called
the actual Orca navigator, observed the target pane becoming active, and
observed restoration of the original pane; the physical Option+1 input path
remains unexecuted.

## Exact run

Orca orchestration launched the worker as Codex `gpt-5.6-sol` with effort
`high`, dispatch `ctx_0062818b256b`. Before any HID write, the coordinator
confirmed the corrected four-second plan.

```bash
PYTHONPATH=src .venv/bin/python \
  experiments/gjc-hardware-smoke/run_smoke.py \
  --execute-hid \
  --evidence experiments/gjc-hardware-smoke/evidence/q65-max-smoke-2026-09-06-venv.json
```

The earlier system-Python invocation exited before opening the device because
that interpreter did not contain `hidapi`; it performed no HID writes. Its
separate failure artifact is retained at
`experiments/gjc-hardware-smoke/evidence/q65-max-smoke-2026-09-06.json`.

## Verified state sequence

The snapshots contained only protocol identifiers, lifecycle states, process
metadata, and counters. They were written to a mode-0700 temporary directory as
a mode-0600 JSONL file; the mode-0600 registry was in the same directory, and
the directory was removed after preflight.

| Stage | Actual tracker result | Exact configured-zone rendering |
|---|---|---|
| one waiting child + ten working sessions | `waiting`, 11 agents, 1 pending decision | slot 1 `ORANGE`; vacant configured slots `SKY_BLUE` |
| waiting decision cleared | `working`, 11 agents, 0 pending | slot 1 `YELLOW`; vacant configured slots `SKY_BLUE` |
| all sessions done | `done`, 11 agents | slot 1 `GREEN`; vacant configured slots `SKY_BLUE` |
| producer disconnected | `unknown`, disconnected | slot 1 `UNKNOWN`; vacant configured slots `SKY_BLUE` |
| launch cleared | no indicators | all configured slots `SKY_BLUE` |

The default configured zone was the source constant `DEFAULT_LEDS`, firmware
indices `1..12`. The complete device frame used the actual firmware-reported
LED count of 72 and explicitly wrote every LED outside the configured zone OFF.

## Hardware evidence

- Device: `Keychron Q65 Max`; protocol `2`; KC_RGB per-key response `true`;
  firmware LED count `72`.
- Immediately before the first lighting write: effect `5`, brightness `255`.
- Mixed/per-key configuration was acknowledged and firmware reported effect
  `24`; each of five full frames completed 8 acknowledged chunks.
- Planned display: `4.0s`; measured display: `4.002s`; total temporary lighting
  control including configure and restore: `4.138s`.
- `restore_lighting` ran in `finally`, then firmware reported effect `5` and
  brightness `255`; both matched the captured values, and the HID handle closed.

`KeychronDevice` acquired the process-wide `DeviceOwnershipLock` before HID
enumeration. The constructor succeeded, so there was no lock contention and no
takeover path was used. The experiment made no EEPROM or firmware change.

## Reproducible artifacts

- Harness: `experiments/gjc-hardware-smoke/run_smoke.py`
- Successful evidence: `experiments/gjc-hardware-smoke/evidence/q65-max-smoke-2026-09-06-venv.json`
- No-HID interpreter failure: `experiments/gjc-hardware-smoke/evidence/q65-max-smoke-2026-09-06.json`
- Preflight evidence: `experiments/gjc-hardware-smoke/evidence/preflight.json`
- Operator notes and commands: `experiments/gjc-hardware-smoke/README.md`

## Navigation boundary

Option+1 was not executed. No keyboard input was synthesized into a user
terminal. At `2026-09-05T18:52:50Z`, the coordinator called the actual
`OrcaWorktreeTabNavigator` with a fresh owned test pane and restored the
original known pane in `finally`. Orca visual-layout observations confirmed
both the target and the restoration. The temporary test terminal was then
closed. Evidence is recorded in
`experiments/gjc-hardware-smoke/evidence/navigation-2026-09-06.json`.

The reusable equivalent harness is:

```bash
PYTHONPATH=src .venv/bin/python experiments/gjc-hardware-smoke/manual_navigation_check.py \
  --target-pane '<fresh-tab-id>:<fresh-leaf-id>' \
  --restore-pane '<original-tab-id>:<original-leaf-id>'
```

The check validates Orca navigation response and observed UI restoration,
not a physical Option+1 input event. The separate reusable harness invocation
above was not used for the coordinator's direct check.
