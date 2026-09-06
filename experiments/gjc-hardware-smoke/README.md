# GJC Q65 Max HID smoke

This experiment uses the checkout's real `GjcTracker`, `render_zone`, and
`KeychronDevice`. It creates only metadata-only synthetic snapshots inside a
mode-0700 temporary directory, requires the shared device ownership lock, sends
acknowledgement-verified RAM-only RGB frames, and restores the immediately prior
effect and brightness in `finally`.

The configured default zone transmits the exact `render_zone` result, including
SKY_BLUE for vacant slots. Only LEDs outside that configured zone are forced OFF
when the full device-sized frame is assembled.

Preflight only (no HID access):

```bash
PYTHONPATH=src python experiments/gjc-hardware-smoke/run_smoke.py
```

Bounded hardware run (five 0.8-second stages, four seconds planned, eight-second
lighting-control watchdog, absolute validation ceiling of twelve seconds):

```bash
PYTHONPATH=src .venv/bin/python experiments/gjc-hardware-smoke/run_smoke.py \
  --execute-hid \
  --evidence experiments/gjc-hardware-smoke/evidence/q65-max-smoke.json
```

The smoke proves firmware responses and restored firmware effect/brightness. It
does not prove that a person saw the colors, that the printed keycaps correspond
to the firmware LED indices, or that a physical Option+1 keypress works.

Navigation was deliberately not executed during the HID smoke. After creating a
fresh owned test terminal and recording the current pane as the restore target,
the explicit target-equivalent command is:

```bash
PYTHONPATH=src .venv/bin/python experiments/gjc-hardware-smoke/manual_navigation_check.py \
  --target-pane '<fresh-tab-id>:<fresh-leaf-id>' \
  --restore-pane '<original-tab-id>:<original-leaf-id>'
```

That command calls the real `OrcaWorktreeTabNavigator` and restores the original
known pane in `finally`; it never injects input into any terminal. A human must
still perform a separate physical Option+1 check for input-listener E2E evidence.
