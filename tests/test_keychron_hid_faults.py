import pytest

from orca_keychron import device_lock
from orca_keychron.device_lock import DeviceOwnershipLock
from orca_keychron.indicator import Indicator
from orca_keychron.keychron_hid import (
    CMD_SET_LED_COLOR,
    EFFECT_MIXED,
    KC_PROTOCOL_VERSION,
    KC_RGB,
    KeychronDevice,
    KeychronError,
)


class ShortWriteDevice:
    def __init__(self):
        self.responses = []
        self.short_write = False
        self.closed = False

    def open_path(self, _path):
        pass

    def write(self, report):
        if self.short_write:
            return len(report) - 1
        payload = report[1:]
        if payload[0] == KC_PROTOCOL_VERSION:
            self.responses.append(bytes([KC_PROTOCOL_VERSION, 1]).ljust(32, b"\0"))
        else:
            self.responses.append(bytes(payload))
        return len(report)

    def read(self, _length, _timeout):
        return self.responses.pop(0) if self.responses else b""

    def close(self):
        self.closed = True


class ShortWriteHid:
    def __init__(self):
        self.instance = ShortWriteDevice()

    def enumerate(self, _vid, _pid):
        return [{
            "path": b"raw",
            "usage_page": 0xFF60,
            "usage": 0x61,
            "product_string": "Keychron Q65 Max",
            "product_id": 0x08B0,
        }]

    def device(self):
        return self.instance


def test_partial_usb_write_is_a_hard_failure_and_close_releases_lock(monkeypatch, tmp_path):
    lock_path = tmp_path / "private" / "device.lock"
    monkeypatch.setattr(device_lock, "_default_lock_path", lambda: lock_path)
    backend = ShortWriteHid()
    device = KeychronDevice(hid_module=backend)
    backend.instance.short_write = True

    with pytest.raises(KeychronError, match="complete HID report"):
        device.set_led_colors(0, [(43, 255, 255)], wait_ack=False)

    device.close()
    contender = DeviceOwnershipLock()
    contender.acquire()
    contender.release()
    assert backend.instance.closed is True


def test_indicator_short_usb_write_restores_lighting_stops_source_and_releases_lock(
    monkeypatch, tmp_path
):
    lock_path = tmp_path / "private" / "device.lock"
    monkeypatch.setattr(device_lock, "_default_lock_path", lambda: lock_path)

    class RuntimeDevice(ShortWriteDevice):
        def __init__(self):
            super().__init__()
            self.short_seen = False
            self.restoring = False
            self.restore_effect_seen = False

        def write(self, report):
            payload = report[1:]
            if payload[:3] == bytes([0x08, 3, 2]):
                self.responses.append(bytes([0x08, 3, 2, EFFECT_MIXED]).ljust(32, b"\0"))
                return len(report)
            if (
                payload[:2] == bytes([KC_RGB, CMD_SET_LED_COLOR])
                and not self.short_seen
            ):
                self.short_seen = True
                return len(report) - 1
            result = super().write(report)
            if self.short_seen and payload[:4] == bytes([0x07, 3, 2, EFFECT_MIXED]):
                self.restore_effect_seen = True
            return result

    class RuntimeHid(ShortWriteHid):
        def __init__(self):
            self.instance = RuntimeDevice()

    class Source:
        command = ("orca",)

        def __init__(self):
            self.started = False
            self.stopped = False

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

        def indicators(self, _now):
            if backend.instance.short_seen:
                indicator.stop()
            return []

    class Listener:
        stopped = False

        def start(self):
            pass

        def stop(self):
            self.stopped = True

    backend = RuntimeHid()
    device = KeychronDevice(hid_module=backend)
    source = Source()
    listener = Listener()
    monkeypatch.setattr("orca_keychron.indicator.signal.signal", lambda *_args: None)
    indicator = Indicator(
        source,
        zone=(1,),
        led_total=4,
        mode="gjc",
        device_factory=lambda **_kwargs: device,
        listener_factory=lambda _selection: listener,
    )

    with pytest.raises(KeychronError, match="complete HID report"):
        indicator.run()

    assert backend.instance.short_seen is True
    assert backend.instance.restore_effect_seen is True
    assert backend.instance.closed is True
    assert source.started is True and source.stopped is True
    assert listener.stopped is True
    contender = DeviceOwnershipLock()
    contender.acquire()
    contender.release()
