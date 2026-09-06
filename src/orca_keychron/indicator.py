from __future__ import annotations

import signal
import threading
import time
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from math import isfinite
from typing import Callable, Literal, Protocol

from .digit_hold import DigitHoldListener, HoldSelection
from .keychron_hid import EFFECT_MIXED, KeychronDevice, KeychronError
from .models import DisplayIndicator, OrcaAgent
from .orca_navigation import (
    OrcaNavigationError,
    OrcaWorktreeTab,
    OrcaWorktreeTabNavigator,
)
from .orca_status import OrcaStatusError, OrcaStatusSource
from .rendering import OFF, render_zone
from .worktree_tracker import WorktreeTracker


class PushedStatusSource(Protocol):
    command: Sequence[str]

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def indicators(self, now: float | None = None) -> Sequence[DisplayIndicator]: ...


class Indicator:
    def __init__(
        self,
        source: OrcaStatusSource | PushedStatusSource,
        zone: Sequence[int] = tuple(range(1, 13)),
        product: str | None = None,
        poll_interval: float = 0.75,
        open_hold_seconds: float = 0.0,
        led_total: int = 100,
        device_factory: Callable[..., KeychronDevice] = KeychronDevice,
        listener_factory: Callable[[HoldSelection], DigitHoldListener] = DigitHoldListener,
        mode: Literal["orca", "gjc"] = "orca",
    ) -> None:
        if not zone:
            raise ValueError("At least one indicator LED is required")
        if any(led < 0 or led > 255 for led in zone):
            raise ValueError("Indicator LEDs must be between 0 and 255")
        if not isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError("Poll interval must be a finite number greater than zero")
        if led_total < 1 or led_total > 256:
            raise ValueError("LED total must be between 1 and 256")
        if mode not in ("orca", "gjc"):
            raise ValueError("Indicator mode must be 'orca' or 'gjc'")
        self.source = source
        self.mode = mode
        self.zone = tuple(dict.fromkeys(zone))
        self.product = product
        self.poll_interval = poll_interval
        self.led_total = led_total
        self.tracker = WorktreeTracker(max_slots=len(self.zone)) if mode == "orca" else None
        self.selection = HoldSelection(open_hold_seconds)
        self.device_factory = device_factory
        self.listener_factory = listener_factory
        self.stop_event = threading.Event()

    def stop(self, *_args: object) -> None:
        self.stop_event.set()

    def run(self) -> None:
        device = self.device_factory(product=self.product)
        restore_required = False
        listener = None
        last_colors: dict[int, tuple[int, int, int]] | None = None
        last_worktree_signature: tuple[tuple[int, str, str, int], ...] | None = None
        worktrees: Sequence[DisplayIndicator] = []
        source_available = False
        source_started = False
        next_poll = 0.0
        next_health_check = 0.0
        focus_future: Future[OrcaWorktreeTab] | None = None
        poll_future: Future[list[OrcaAgent]] | None = None
        poll_executor = (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="orca-status")
            if self.mode == "orca"
            else None
        )
        try:
            if not device.supports_per_key_rgb():
                raise KeychronError(
                    "This keyboard firmware does not enable KC_RGB per-key control (0xA8)"
                )
            previous_effect = device.get_effect()
            previous_brightness = device.get_brightness()
            total = device.led_count() or self.led_total
            invalid_leds = [led for led in self.zone if led >= total]
            if invalid_leds:
                raise KeychronError(
                    f"Indicator LEDs {invalid_leds} are outside this keyboard's {total}-LED range"
                )
            listener = self.listener_factory(self.selection)
            navigator = OrcaWorktreeTabNavigator(self.source.command)
            signal.signal(signal.SIGINT, self.stop)
            signal.signal(signal.SIGTERM, self.stop)
            print(f"Connected to {device.product}; indicator LEDs: {','.join(map(str, self.zone))}")
            if self.mode == "gjc":
                # Even a partially failed start must get its matching cleanup call.
                source_started = True
                self.source.start()
                source_available = True
            listener.start()
            restore_required = True
            device.configure_mixed_per_key_indicator(self.zone, total)
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="orca-focus") as executor:
                while not self.stop_event.is_set():
                    now = time.monotonic()
                    refreshed = False
                    if self.mode == "gjc":
                        # Read only the receiver's local model and expire its lease.
                        # This tick never queries GJC or polls a file/CLI snapshot.
                        worktrees = self.source.indicators(now)
                        refreshed = True
                    if poll_future is not None and poll_future.done():
                        try:
                            assert self.tracker is not None
                            worktrees = self.tracker.update(poll_future.result(), now)
                            source_available = True
                            refreshed = True
                        except OrcaStatusError as exc:
                            print(f"Orca status unavailable: {exc}", flush=True)
                            self.selection.set_worktrees([])
                            source_available = False
                        poll_future = None
                    # Never queue another request while one is in flight. Consume every
                    # result on this thread before starting the next snapshot.
                    if poll_executor is not None and poll_future is None and now >= next_poll:
                        poll_future = poll_executor.submit(self.source.snapshot)
                        next_poll = now + self.poll_interval
                    if refreshed:
                        self.selection.set_indicators(worktrees)
                        signature = tuple(
                            (item.slot, item.state, item.identity_label, item.agent_count)
                            for item in worktrees
                        )
                        if signature != last_worktree_signature:
                            summary = ", ".join(
                                f"{slot + 1}={state}:{identity}({count} agents)"
                                for slot, state, identity, count in signature
                            )
                            label = "GJC sessions" if self.mode == "gjc" else "Worktree slots"
                            print(f"{label}: {summary or 'none'}", flush=True)
                            last_worktree_signature = signature
                    if focus_future is None:
                        ready_pane = self.selection.pop_ready(now)
                        if ready_pane is not None:
                            focus_future = executor.submit(navigator.open, ready_pane)
                    if focus_future is not None and focus_future.done():
                        try:
                            destination = focus_future.result()
                            print(
                                "Opened Orca worktree tab "
                                f"{destination.worktree_id} / {destination.tab_id}",
                                flush=True,
                            )
                        except OrcaNavigationError as exc:
                            print(f"Could not open Orca worktree tab: {exc}", flush=True)
                        focus_future = None
                    if now >= next_health_check:
                        if device.get_effect() != EFFECT_MIXED:
                            device.configure_mixed_per_key_indicator(self.zone, total)
                            last_colors = None
                        next_health_check = now + 10.0
                    colors = (
                        render_zone(worktrees, self.zone)
                        if source_available
                        else dict.fromkeys(self.zone, OFF)
                    )
                    if colors != last_colors:
                        device.set_zone(colors, total)
                        last_colors = colors
                    self.stop_event.wait(0.05)
        finally:
            try:
                if listener is not None:
                    listener.stop()
            finally:
                try:
                    if restore_required:
                        device.restore_lighting(previous_effect, previous_brightness)
                finally:
                    try:
                        device.close()
                    finally:
                        # Restore lighting before waiting for an in-flight CLI request.
                        # snapshot() bounds that wait with its subprocess timeout.
                        try:
                            if source_started:
                                self.source.stop()
                        finally:
                            if poll_executor is not None:
                                poll_executor.shutdown(wait=True, cancel_futures=True)
