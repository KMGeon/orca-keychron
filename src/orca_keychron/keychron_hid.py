from __future__ import annotations

import time
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from .device_lock import DeviceLockError, DeviceOwnershipLock

VID_KEYCHRON = 0x3434
RAW_USAGE_PAGE = 0xFF60
RAW_USAGE = 0x61
REPORT_LENGTH = 32
KC_RGB = 0xA8
KC_PROTOCOL_VERSION = 0xA0
KC_SUPPORT_FEATURE = 0xA2
CMD_LED_COUNT = 5
CMD_LED_NUMBER = 6
CMD_SET_LED_COLOR = 10
CMD_SET_MIXED_REGIONS = 13
CMD_SET_MIXED_EFFECTS = 15
EFFECT_PER_KEY = 23
EFFECT_MIXED = 24
EFFECT_NONE = 0
EFFECT_SOLID_COLOR = 1
LIGHTING_CHANNEL = 3
LIGHT_BRIGHTNESS = 1
LIGHT_EFFECT = 2


class KeychronError(RuntimeError):
    pass


@dataclass(frozen=True)
class KeychronInterface:
    path: Any
    product: str
    product_id: int


def load_hid() -> Any:
    try:
        import hid
    except ImportError as exc:
        raise KeychronError("hidapi is not installed; run: python -m pip install hidapi") from exc
    return hid


def enumerate_keychron_interfaces(hid_module: Any = None) -> list[KeychronInterface]:
    hid_module = hid_module or load_hid()
    interfaces = []
    for item in hid_module.enumerate(VID_KEYCHRON, 0):
        if item.get("usage_page") != RAW_USAGE_PAGE or item.get("usage") != RAW_USAGE:
            continue
        interfaces.append(
            KeychronInterface(
                path=item.get("path"),
                product=str(item.get("product_string") or "Unknown Keychron"),
                product_id=int(item.get("product_id") or 0),
            )
        )
    return interfaces


class KeychronDevice:
    def __init__(self, product: str | None = None, hid_module: Any = None) -> None:
        self._device = None
        self.product = ""
        self._ownership = DeviceOwnershipLock()
        try:
            self._ownership.acquire()
        except DeviceLockError as exc:
            raise KeychronError(str(exc)) from exc
        try:
            self._hid = hid_module or load_hid()
            candidates = enumerate_keychron_interfaces(self._hid)
            for candidate in candidates:
                if product and product.lower() not in candidate.product.lower():
                    continue
                device = self._hid.device()
                self._device = device
                try:
                    device.open_path(candidate.path)
                    self.product = candidate.product
                    if self.protocol_version() is not None:
                        return
                except OSError:
                    pass
                # A failing close must not leave this instance with a handle
                # that is later reused or prevent the ownership lock releasing.
                self._device = None
                device.close()
            suffix = f" matching {product!r}" if product else ""
            raise KeychronError(f"No responding Keychron raw HID interface found{suffix}")
        except BaseException:
            with suppress(Exception):
                self.close()
            raise

    def close(self) -> None:
        device, self._device = self._device, None
        try:
            if device is not None:
                device.close()
        finally:
            self._ownership.release()

    def _write(self, payload: Sequence[int]) -> None:
        if self._device is None:
            raise KeychronError("Keychron device is closed")
        if len(payload) > REPORT_LENGTH:
            raise ValueError("HID payload exceeds 32 bytes")
        report = bytes([0]) + bytes(payload).ljust(REPORT_LENGTH, b"\x00")
        written = self._device.write(report)
        # hidapi returns the transferred byte count. Some test/dummy backends
        # return None, but a reported short write must never be treated as a
        # successfully rendered frame because the caller then suppresses retry.
        if written is not None and written != len(report):
            raise KeychronError(
                f"Keychron did not accept the complete HID report ({written}/{len(report)} bytes)"
            )

    def _xfer(self, payload: Sequence[int], timeout_ms: int = 1000) -> bytes:
        self._write(payload)
        expected = bytes(payload[:2])
        deadline = time.monotonic() + timeout_ms / 1000
        for _ in range(32):
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                break
            response = bytes(self._device.read(REPORT_LENGTH, remaining_ms))
            if not response:
                break
            if response[: len(expected)] == expected:
                return response
        return b""

    def led_count(self) -> int | None:
        response = self._xfer([KC_RGB, CMD_LED_COUNT], timeout_ms=500)
        return response[3] if len(response) > 3 else None

    def protocol_version(self) -> int | None:
        response = self._xfer([KC_PROTOCOL_VERSION], timeout_ms=500)
        return response[1] if len(response) > 1 else None

    def support_features(self) -> int | None:
        response = self._xfer([KC_SUPPORT_FEATURE], timeout_ms=500)
        return response[2] if len(response) > 2 else None

    def supports_per_key_rgb(self) -> bool:
        response = self._xfer([KC_RGB, 1], timeout_ms=500)
        return response[:2] == bytes([KC_RGB, 1])

    def led_matrix(self, max_rows: int = 10) -> list[list[int]]:
        rows = []
        for row in range(max_rows):
            response = self._xfer([KC_RGB, CMD_LED_NUMBER, row, 0xFF, 0xFF, 0xFF])
            if len(response) < 4:
                break
            values = [-1 if value == 0xFF else value for value in response[3:26]]
            if all(value == -1 for value in values):
                break
            rows.append(values)
        return rows

    def get_effect(self) -> int | None:
        return self._get_light_value(LIGHT_EFFECT)

    def set_effect(self, effect: int) -> None:
        self._set_light_value(LIGHT_EFFECT, effect)

    def set_brightness(self, brightness: int) -> None:
        self._set_light_value(LIGHT_BRIGHTNESS, brightness)

    def get_brightness(self) -> int | None:
        return self._get_light_value(LIGHT_BRIGHTNESS)

    def _get_light_value(self, value: int) -> int | None:
        response = self._xfer([0x08, LIGHTING_CHANNEL, value])
        return response[3] if len(response) > 3 else None

    def _set_light_value(self, value: int, *data: int) -> None:
        if not self._xfer([0x07, LIGHTING_CHANNEL, value, *data]):
            raise KeychronError("Keychron did not acknowledge the lighting change")

    def set_led_colors(
        self, start: int, colors: Sequence[tuple[int, int, int]], wait_ack: bool = True
    ) -> None:
        if not colors or len(colors) > 9:
            raise ValueError("colors must contain between 1 and 9 entries")
        payload = [KC_RGB, CMD_SET_LED_COLOR, start, len(colors)]
        for color in colors:
            payload.extend(color)
        if wait_ack and not self._xfer(payload):
            raise KeychronError("Keychron did not acknowledge the LED color change")
        if not wait_ack:
            self._write(payload)
            if self._device is not None:
                self._device.read(REPORT_LENGTH, 5)

    def set_frame(self, colors: Sequence[tuple[int, int, int]]) -> None:
        for start in range(0, len(colors), 9):
            self.set_led_colors(start, colors[start : start + 9], wait_ack=False)

    def set_zone(self, colors: dict[int, tuple[int, int, int]], total: int = 100) -> None:
        frame = [(0, 0, 0)] * total
        for led, color in colors.items():
            if 0 <= led < total:
                frame[led] = color
        self.set_frame(frame)

    def clear_rgb_buffer(self, settle_seconds: float = 0.05) -> None:
        self.set_effect(EFFECT_NONE)
        if settle_seconds > 0:
            time.sleep(settle_seconds)

    def restore_lighting(self, effect: int | None, brightness: int | None) -> None:
        self.clear_rgb_buffer()
        if brightness is not None:
            self.set_brightness(brightness)
        if effect is not None:
            self.set_effect(effect)

    def configure_mixed_indicator(self, total: int, brightness: int = 255) -> None:
        self.clear_rgb_buffer()
        empty = [(0, 0, 0, 0, 0)] * 5
        self._set_mixed_effects(0, empty)
        self._set_mixed_effects(1, empty)
        self._set_mixed_regions([0] * total)
        self.set_brightness(brightness)
        self.set_effect(EFFECT_MIXED)

    def configure_mixed_per_key_indicator(
        self, leds: Sequence[int], total: int, brightness: int = 255
    ) -> None:
        self.clear_rgb_buffer()
        empty = [(0, 0, 0, 0, 0)] * 5
        self._set_mixed_effects(0, empty)
        self._set_mixed_effects(1, [(EFFECT_PER_KEY, 0, 0, 128, 0)])
        regions = [0] * total
        for led in leds:
            if 0 <= led < total:
                regions[led] = 1
        self._set_mixed_regions(regions)
        self.set_brightness(brightness)
        self.set_effect(EFFECT_MIXED)

    def set_mixed_zone(
        self, color: tuple[int, int, int] | None, leds: Sequence[int], total: int
    ) -> None:
        regions = [0] * total
        if color is not None:
            for led in leds:
                if 0 <= led < total:
                    regions[led] = 1
            hue, saturation, _value = color
            self._set_mixed_effects(1, [(EFFECT_SOLID_COLOR, hue, saturation, 128, 0)])
        self._set_mixed_regions(regions)

    def _set_mixed_regions(self, regions: Sequence[int]) -> None:
        for start in range(0, len(regions), 28):
            chunk = regions[start : start + 28]
            if not self._xfer([KC_RGB, CMD_SET_MIXED_REGIONS, start, len(chunk), *chunk]):
                raise KeychronError("Keychron did not acknowledge the mixed RGB regions")

    def _set_mixed_effects(
        self, region: int, effects: Sequence[tuple[int, int, int, int, int]]
    ) -> None:
        for start in range(0, len(effects), 3):
            chunk = effects[start : start + 3]
            payload = [KC_RGB, CMD_SET_MIXED_EFFECTS, region, start, len(chunk)]
            for effect, hue, saturation, speed, duration in chunk:
                payload.extend(
                    [
                        effect,
                        hue,
                        saturation,
                        speed,
                        duration & 0xFF,
                        duration >> 8 & 0xFF,
                        duration >> 16 & 0xFF,
                        duration >> 24 & 0xFF,
                    ]
                )
            if not self._xfer(payload):
                raise KeychronError("Keychron did not acknowledge the mixed RGB effects")
