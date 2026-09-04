from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from math import isfinite

from .models import WorktreeIndicator

KEY_SLOTS = {key: slot for slot, key in enumerate("1234567890-=")}
MAC_KEYCODE_KEYS = {18: "1", 19: "2", 20: "3", 21: "4", 23: "5", 22: "6"}
MAC_KEYCODE_KEYS.update({26: "7", 28: "8", 25: "9", 29: "0", 27: "-", 24: "="})
ORCA_BUNDLE_ID = "com.stablyai.orca"


def orca_is_frontmost() -> bool:
    if sys.platform != "darwin":
        return True
    try:
        from AppKit import NSWorkspace
    except ImportError:
        return False
    frontmost = NSWorkspace.sharedWorkspace().frontmostApplication()
    return frontmost is not None and frontmost.bundleIdentifier() == ORCA_BUNDLE_ID


@dataclass(frozen=True)
class HeldSelection:
    digit: str
    pane_key: str
    started_at: float


class HoldSelection:
    def __init__(self, hold_seconds: float = 0.0) -> None:
        if not isfinite(hold_seconds) or hold_seconds < 0:
            raise ValueError("Hold duration must be a finite non-negative number")
        self.hold_seconds = hold_seconds
        self._targets: dict[int, tuple[str, ...]] = {}
        self._next_target: dict[int, int] = {}
        self._held: HeldSelection | None = None
        self._ready_pane: str | None = None
        self._triggered = False
        self._lock = threading.Lock()

    def set_worktrees(self, worktrees: Iterable[WorktreeIndicator]) -> None:
        with self._lock:
            targets = {
                worktree.slot: worktree.target_pane_keys
                for worktree in worktrees
                if worktree.target_pane_keys
            }
            for slot, pane_keys in targets.items():
                if self._targets.get(slot) != pane_keys:
                    self._next_target[slot] = 0
            self._targets = targets
            self._next_target = {
                slot: index % len(targets[slot])
                for slot, index in self._next_target.items()
                if slot in targets
            }

    def press(self, digit: str, now: float, option_only: bool = False) -> None:
        slot = KEY_SLOTS.get(digit)
        if slot is None or not option_only:
            return
        with self._lock:
            if self._held is not None:
                return
            targets = self._targets.get(slot)
            if targets:
                target_index = self._next_target.get(slot, 0)
                pane_key = targets[target_index]
                self._next_target[slot] = (target_index + 1) % len(targets)
                self._held = HeldSelection(digit, pane_key, now)
                self._triggered = self.hold_seconds == 0
                if self._triggered:
                    self._ready_pane = pane_key

    def release(self, digit: str) -> None:
        with self._lock:
            if self._held is not None and self._held.digit == digit:
                self._held = None
                self._triggered = False

    def pop_ready(self, now: float) -> str | None:
        with self._lock:
            if self._ready_pane is not None:
                pane_key = self._ready_pane
                self._ready_pane = None
                return pane_key
            if (
                self._held is None
                or self._triggered
                or now - self._held.started_at < self.hold_seconds
                or self._held.pane_key not in self._targets.get(KEY_SLOTS[self._held.digit], ())
            ):
                return None
            self._triggered = True
            return self._held.pane_key

    def suppress_repeat(self, digit: str) -> bool:
        with self._lock:
            return self._held is not None and self._held.digit == digit


class DigitHoldListener:
    def __init__(
        self,
        selection: HoldSelection,
        clock: Callable[[], float] = time.monotonic,
        frontmost_check: Callable[[], bool] = orca_is_frontmost,
    ) -> None:
        self.selection = selection
        self.clock = clock
        self.frontmost_check = frontmost_check
        self._listener: object | None = None
        self._modifiers: set[object] = set()
        self._modifier_keys: frozenset[object] = frozenset()
        self._option_keys: frozenset[object] = frozenset()
        self._quartz: object | None = None

    def start(self) -> None:
        try:
            from pynput import keyboard
        except ImportError as exc:
            raise RuntimeError("Keyboard input support requires pynput") from exc

        self._modifier_keys = frozenset(
            {
                keyboard.Key.alt,
                keyboard.Key.alt_l,
                keyboard.Key.alt_r,
                keyboard.Key.cmd,
                keyboard.Key.cmd_l,
                keyboard.Key.cmd_r,
                keyboard.Key.ctrl,
                keyboard.Key.ctrl_l,
                keyboard.Key.ctrl_r,
                keyboard.Key.shift,
                keyboard.Key.shift_l,
                keyboard.Key.shift_r,
            }
        )
        self._option_keys = frozenset({keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r})
        options = {}
        if sys.platform == "darwin":
            import Quartz

            self._quartz = Quartz
            options["darwin_intercept"] = self._darwin_intercept
        callbacks = (
            {}
            if sys.platform == "darwin"
            else {"on_press": self._on_press, "on_release": self._on_release}
        )
        listener = keyboard.Listener(**callbacks, **options)
        listener.start()
        listener.wait()
        self._listener = listener

    def stop(self) -> None:
        listener = self._listener
        if listener is not None:
            listener.stop()
            self._listener = None

    def _on_press(self, key: object) -> None:
        if key in self._modifier_keys:
            self._modifiers.add(key)
            return
        digit = getattr(key, "char", None)
        if isinstance(digit, str):
            option_pressed = bool(self._modifiers & self._option_keys)
            other_modifier_pressed = bool(self._modifiers - self._option_keys)
            self.selection.press(
                digit,
                self.clock(),
                option_only=option_pressed and not other_modifier_pressed,
            )

    def _on_release(self, key: object) -> None:
        if key in self._modifier_keys:
            self._modifiers.discard(key)
            return
        digit = getattr(key, "char", None)
        if isinstance(digit, str):
            self.selection.release(digit)

    def _darwin_intercept(self, event_type: int, event: object) -> object | None:
        quartz = self._quartz
        if quartz is None or event_type not in (quartz.kCGEventKeyDown, quartz.kCGEventKeyUp):
            return event
        keycode = quartz.CGEventGetIntegerValueField(event, quartz.kCGKeyboardEventKeycode)
        digit = MAC_KEYCODE_KEYS.get(keycode)
        if digit is None:
            return event
        modifier_mask = (
            quartz.kCGEventFlagMaskShift
            | quartz.kCGEventFlagMaskControl
            | quartz.kCGEventFlagMaskAlternate
            | quartz.kCGEventFlagMaskCommand
        )
        if event_type == quartz.kCGEventKeyDown:
            modifiers = quartz.CGEventGetFlags(event) & modifier_mask
            if modifiers != quartz.kCGEventFlagMaskAlternate:
                return event
            if not self.frontmost_check():
                print(f"Ignored Option+{digit}: Orca is not frontmost", flush=True)
                return event
            self.selection.press(digit, self.clock(), option_only=True)
            if self.selection.suppress_repeat(digit):
                print(f"Selected worktree slot {digit}", flush=True)
                return None
            print(f"Ignored Option+{digit}: worktree slot is empty", flush=True)
            return None
        if not self.selection.suppress_repeat(digit):
            return event
        self.selection.release(digit)
        return None
