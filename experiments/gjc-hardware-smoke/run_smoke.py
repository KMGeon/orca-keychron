"""Bounded, acknowledgement-verified GJC-to-Q65 Max HID smoke.

The synthetic GJC snapshots contain identifiers, lifecycle states, counters, and
process metadata only. No prompt, response, tool argument, or terminal content is
created or retained.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from orca_keychron.config import DEFAULT_LEDS
from orca_keychron.keychron_hid import EFFECT_MIXED, KeychronDevice
from orca_keychron.rendering import (
    GREEN,
    OFF,
    ORANGE,
    SKY_BLUE,
    UNKNOWN,
    YELLOW,
    render_zone,
)
from orca_keychron_gjc.gjc_protocol import parse_snapshot
from orca_keychron_gjc.gjc_tracker import GjcTracker

PRODUCT = "Q65 Max"
EXPECTED_PROTOCOL = 2
STAGE_SECONDS = 0.8
PLANNED_DISPLAY_SECONDS = 4.0
MAX_LIGHTING_CONTROL_SECONDS = 8.0
MAX_ALLOWED_DISPLAY_SECONDS = 12.0
PRODUCER_ID = "00000000-0000-4000-8000-000000000001"
LAUNCH_ID = "00000000-0000-4000-8000-000000000002"
ROOT_SESSION_ID = "smoke-root"


class SmokeFailure(RuntimeError):
    pass


class SmokeInterrupted(BaseException):
    def __init__(self, signum: int) -> None:
        super().__init__(f"Interrupted by signal {signum}")
        self.signum = signum


@dataclass(frozen=True)
class Stage:
    name: str
    state: str
    colors: dict[int, tuple[int, int, int]]
    agent_count: int
    pending_requests: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session(
    session_id: str, role: str, state: str, *, pending_decisions: int = 0
) -> dict[str, Any]:
    return {
        "sessionId": session_id,
        "role": role,
        "state": state,
        "pendingAsks": 0,
        "pendingDecisions": pending_decisions,
    }


def _snapshot(sequence: int, waiting_child: bool = False, done: bool = False) -> dict[str, Any]:
    root_state = "done" if done else "working"
    sessions = [_session(ROOT_SESSION_ID, "root", root_state)]
    sessions.extend(
        _session(f"working-child-{index}", "child", root_state) for index in range(1, 10)
    )
    child_state = "done" if done else "waiting" if waiting_child else "working"
    sessions.append(
        _session(
            "priority-child",
            "child",
            child_state,
            pending_decisions=1 if waiting_child else 0,
        )
    )
    return {
        "version": 1,
        "type": "snapshot",
        "producerId": PRODUCER_ID,
        "sequence": sequence,
        "launchId": LAUNCH_ID,
        "pid": 6500,
        "startedAt": 1_788_630_000_000,
        "complete": True,
        "closed": False,
        "root": {
            "sessionId": ROOT_SESSION_ID,
            "terminalHandle": "term_gjc_hardware_smoke",
            "paneKey": "smoke-tab:smoke-leaf",
            "worktreeId": "gjc-hardware-smoke",
        },
        "sessions": sessions,
    }


def _assert_private(path: Path, kind: str) -> str:
    info = path.lstat()
    mode = stat.S_IMODE(info.st_mode)
    expected = 0o700 if kind == "directory" else 0o600
    valid_type = stat.S_ISDIR(info.st_mode) if kind == "directory" else stat.S_ISREG(info.st_mode)
    if not valid_type or info.st_uid != os.getuid() or mode != expected:
        raise SmokeFailure(f"Private {kind} validation failed for {path}")
    return f"{mode:04o}"


def prepare_plan() -> tuple[list[Stage], dict[str, Any]]:
    zone = tuple(DEFAULT_LEDS)
    snapshots = [
        _snapshot(1, waiting_child=True),
        _snapshot(2),
        _snapshot(3, done=True),
    ]
    expected = [
        ("waiting_priority", "waiting", ORANGE),
        ("waiting_cleared", "working", YELLOW),
        ("all_done", "done", GREEN),
    ]
    stages: list[Stage] = []
    temporary_metadata: dict[str, Any] = {}
    temporary_path = ""
    with tempfile.TemporaryDirectory(prefix="gjc-hid-smoke-") as temporary:
        directory = Path(temporary)
        directory.chmod(0o700)
        temporary_path = str(directory)
        snapshot_path = directory / "metadata-only-snapshots.jsonl"
        snapshot_path.write_text(
            "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in snapshots),
            encoding="utf-8",
        )
        snapshot_path.chmod(0o600)
        tracker = GjcTracker(len(zone), directory / "registry.json")

        for now, (payload, (name, expected_state, expected_color)) in enumerate(
            zip(snapshots, expected), start=1
        ):
            parsed = parse_snapshot(payload)
            if not tracker.apply(parsed, now=float(now)):
                raise SmokeFailure(f"Tracker rejected {name} snapshot")
            indicators = tracker.indicators(float(now))
            if len(indicators) != 1:
                raise SmokeFailure(f"Expected one occupied slot during {name}")
            item = indicators[0]
            rendered = render_zone(indicators, zone)
            colors = rendered
            if item.state != expected_state or colors[zone[0]] != expected_color:
                raise SmokeFailure(
                    f"{name} expected {expected_state}/{expected_color}, "
                    f"got {item.state}/{colors[zone[0]]}"
                )
            if any(colors[led] != SKY_BLUE for led in zone[1:]):
                raise SmokeFailure(f"Vacant LEDs were not SKY_BLUE during {name}")
            stages.append(
                Stage(
                    name=name,
                    state=item.state,
                    colors=colors,
                    agent_count=item.agent_count,
                    pending_requests=item.pending_requests,
                )
            )

        tracker.disconnect(PRODUCER_ID, now=4.0)
        indicators = tracker.indicators(4.0)
        rendered = render_zone(indicators, zone)
        colors = rendered
        if len(indicators) != 1 or indicators[0].state != "unknown":
            raise SmokeFailure("Disconnect did not render the occupied launch as unknown")
        if colors[zone[0]] != UNKNOWN or any(colors[led] != SKY_BLUE for led in zone[1:]):
            raise SmokeFailure("Disconnect color or vacant SKY_BLUE policy was not preserved")
        stages.append(
            Stage(
                name="disconnect",
                state="unknown",
                colors=colors,
                agent_count=indicators[0].agent_count,
                pending_requests=indicators[0].pending_requests,
            )
        )

        if not tracker.clear(LAUNCH_ID):
            raise SmokeFailure("Tracked launch could not be cleared for the vacant stage")
        indicators = tracker.indicators(5.0)
        rendered = render_zone(indicators, zone)
        colors = rendered
        if indicators or any(color != SKY_BLUE for color in colors.values()):
            raise SmokeFailure("Vacant configured zone did not resolve to SKY_BLUE")
        stages.append(Stage("vacant", "vacant", colors, 0, 0))

        temporary_metadata = {
            "directoryMode": _assert_private(directory, "directory"),
            "snapshotsFileMode": _assert_private(snapshot_path, "file"),
            "registryFileMode": _assert_private(directory / "registry.json", "file"),
            "snapshotCount": len(snapshots),
            "snapshotFields": sorted(snapshots[0]),
            "sessionFields": sorted(snapshots[0]["sessions"][0]),
            "containedUserContent": False,
        }
    temporary_metadata.update({"path": temporary_path, "removedAfterPreflight": True})
    return stages, temporary_metadata


def _write_verified_frame(
    device: KeychronDevice,
    zone_colors: dict[int, tuple[int, int, int]],
    total: int,
) -> int:
    frame = [OFF] * total
    for led, color in zone_colors.items():
        if not 0 <= led < total:
            raise SmokeFailure(f"LED {led} is outside the actual {total}-LED frame")
        frame[led] = color
    chunks = 0
    for start in range(0, total, 9):
        # wait_ack=True makes every chunk fail closed unless firmware echoes it.
        device.set_led_colors(start, frame[start : start + 9], wait_ack=True)
        chunks += 1
    return chunks


def _serializable_stage(stage: Stage) -> dict[str, Any]:
    return {
        "name": stage.name,
        "state": stage.state,
        "agentCount": stage.agent_count,
        "pendingRequests": stage.pending_requests,
        "zone": {str(led): list(color) for led, color in stage.colors.items()},
    }


def _install_interrupt_handlers() -> dict[int, Any]:
    previous: dict[int, Any] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, lambda received, _frame: (_ for _ in ()).throw(SmokeInterrupted(received)))
    return previous


def _restore_signal_handlers(previous: dict[int, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def execute_hardware(stages: list[Stage], result: dict[str, Any]) -> None:
    zone = tuple(DEFAULT_LEDS)
    device: KeychronDevice | None = None
    restore_required = False
    previous_handlers = _install_interrupt_handlers()
    alarm_supported = hasattr(signal, "setitimer") and hasattr(signal, "SIGALRM")
    previous_alarm_handler: Any = None
    lighting_started: float | None = None
    try:
        device = KeychronDevice(product=PRODUCT)
        protocol = device.protocol_version()
        per_key = device.supports_per_key_rgb()
        total = device.led_count()
        if protocol != EXPECTED_PROTOCOL:
            raise SmokeFailure(f"Expected protocol {EXPECTED_PROTOCOL}, got {protocol}")
        if per_key is not True:
            raise SmokeFailure("KC_RGB per-key acknowledgement was not available")
        if total is None or any(led >= total for led in zone):
            raise SmokeFailure(f"Default zone {zone} is invalid for reported LED count {total}")

        # These are intentionally the final reads before the first lighting write.
        before_effect = device.get_effect()
        before_brightness = device.get_brightness()
        if before_effect is None or before_brightness is None:
            raise SmokeFailure("Could not capture restorable effect and brightness before writing")
        result["hardware"] = {
            "product": device.product,
            "protocol": protocol,
            "perKeyRgb": per_key,
            "ledCount": total,
            "defaultZone": list(zone),
            "before": {"effect": before_effect, "brightness": before_brightness},
            "writes": [],
        }

        if alarm_supported:
            previous_alarm_handler = signal.getsignal(signal.SIGALRM)
            signal.signal(
                signal.SIGALRM,
                lambda _received, _frame: (_ for _ in ()).throw(
                    SmokeFailure("Lighting-control watchdog expired")
                ),
            )
            signal.setitimer(signal.ITIMER_REAL, MAX_LIGHTING_CONTROL_SECONDS)

        restore_required = True
        lighting_started = time.monotonic()
        device.configure_mixed_per_key_indicator(zone, total)
        configured_effect = device.get_effect()
        if configured_effect != EFFECT_MIXED:
            raise SmokeFailure(
                f"Firmware did not report mixed effect after configuration: {configured_effect}"
            )
        result["hardware"]["writes"].append(
            {
                "operation": "configure_mixed_per_key_indicator",
                "acknowledged": True,
                "firmwareEffect": configured_effect,
            }
        )

        display_started = time.monotonic()
        for index, stage in enumerate(stages, start=1):
            chunks = _write_verified_frame(device, stage.colors, total)
            result["hardware"]["writes"].append(
                {
                    "operation": "set_verified_frame",
                    "stage": stage.name,
                    "chunks": chunks,
                    "acknowledged": True,
                }
            )
            deadline = display_started + index * STAGE_SECONDS
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
        display_elapsed = time.monotonic() - display_started
        if display_elapsed > MAX_ALLOWED_DISPLAY_SECONDS:
            raise SmokeFailure(
                f"Display exceeded {MAX_ALLOWED_DISPLAY_SECONDS:g} seconds: {display_elapsed:.3f}"
            )
        result["display"] = {
            "plannedSeconds": PLANNED_DISPLAY_SECONDS,
            "actualSeconds": round(display_elapsed, 3),
            "maximumAllowedSeconds": MAX_ALLOWED_DISPLAY_SECONDS,
        }
    finally:
        if alarm_supported:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if previous_alarm_handler is not None:
                signal.signal(signal.SIGALRM, previous_alarm_handler)
        # Defer additional interrupts for the short mandatory restore/close path.
        for signum in previous_handlers:
            signal.signal(signum, signal.SIG_IGN)
        try:
            if device is not None and restore_required:
                restore_error: Exception | None = None
                try:
                    before = result["hardware"]["before"]
                    device.restore_lighting(before["effect"], before["brightness"])
                    after_effect = device.get_effect()
                    after_brightness = device.get_brightness()
                    restored = (
                        after_effect == before["effect"]
                        and after_brightness == before["brightness"]
                    )
                    result["hardware"]["after"] = {
                        "effect": after_effect,
                        "brightness": after_brightness,
                    }
                    result["hardware"]["restore"] = {
                        "restoreLightingCalled": True,
                        "firmwareValuesMatch": restored,
                    }
                    if not restored:
                        raise SmokeFailure("Firmware effect/brightness did not match after restore")
                except Exception as exc:  # noqa: BLE001 - preserve cleanup evidence, then re-raise
                    restore_error = exc
                    result.setdefault("hardware", {}).setdefault("restore", {}).update(
                        {
                            "restoreLightingCalled": True,
                            "firmwareValuesMatch": False,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                if restore_error is not None and sys.exc_info()[0] is None:
                    raise restore_error
        finally:
            try:
                if device is not None:
                    device.close()
                    result.setdefault("hardware", {})["closed"] = True
            finally:
                if lighting_started is not None:
                    result.setdefault("hardware", {})["lightingControlSeconds"] = round(
                        time.monotonic() - lighting_started, 3
                    )
                _restore_signal_handlers(previous_handlers)


def _write_evidence(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute-hid",
        action="store_true",
        help="Perform the bounded Q65 Max writes; without this flag only preflight runs",
    )
    parser.add_argument("--evidence", type=Path, help="Write a mode-0600 JSON result")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "startedAt": _utc_now(),
        "command": "execute-hid" if args.execute_hid else "preflight-only",
        "productTarget": PRODUCT,
        "responseBoundary": "Firmware HID acknowledgements; no optical observation",
        "physicalKeypressE2E": False,
        "navigationExecuted": False,
        "orchestrationLaunch": {
            "agent": "codex",
            "model": "gpt-5.6-sol",
            "effort": "high",
            "dispatchId": "ctx_0062818b256b",
        },
    }
    exit_code = 0
    try:
        UUID(PRODUCER_ID)
        UUID(LAUNCH_ID)
        stages, temporary_metadata = prepare_plan()
        result["preflight"] = {
            "ok": True,
            "temporaryStorage": temporary_metadata,
            "stages": [_serializable_stage(stage) for stage in stages],
            "assertions": [
                "one waiting child overrides ten working sessions",
                "cleared waiting child transitions the launch to working",
                "all done sessions transition the launch to done",
                "producer disconnect transitions the occupied launch to unknown",
                "vacant configured slots preserve render_zone SKY_BLUE",
                "LEDs outside the configured zone are written OFF in the full device frame",
            ],
        }
        if args.execute_hid:
            execute_hardware(stages, result)
        result["outcome"] = "succeeded"
    except SmokeInterrupted as exc:
        result["outcome"] = "interrupted"
        result["error"] = f"{type(exc).__name__}: {exc}"
        exit_code = 128 + exc.signum
    except Exception as exc:  # noqa: BLE001 - emit bounded failure evidence for the harness
        result["outcome"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        exit_code = 1
    finally:
        result["finishedAt"] = _utc_now()
        if args.evidence is not None:
            _write_evidence(args.evidence, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
