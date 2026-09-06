import pytest

from orca_keychron import device_lock, keychron_hid
from orca_keychron.device_lock import DeviceLockError, DeviceOwnershipLock
from orca_keychron.keychron_hid import (
    CMD_LED_COUNT,
    CMD_SET_LED_COLOR,
    CMD_SET_MIXED_EFFECTS,
    CMD_SET_MIXED_REGIONS,
    EFFECT_NONE,
    EFFECT_PER_KEY,
    KC_PROTOCOL_VERSION,
    KC_RGB,
    KeychronDevice,
    KeychronError,
)


class FakeDevice:
    def __init__(self, per_key=True):
        self.per_key = per_key
        self.writes = []
        self.responses = []
        self.opened = False
        self.closed = 0

    def open_path(self, _path):
        self.opened = True

    def write(self, report):
        self.writes.append(report)
        payload = report[1:]
        if payload[0] == KC_PROTOCOL_VERSION:
            self.responses.append(bytes([KC_PROTOCOL_VERSION, 1]).ljust(32, b"\0"))
        elif payload[:2] == bytes([KC_RGB, 1]) and not self.per_key:
            self.responses.append(bytes([0xFF, 1]).ljust(32, b"\0"))
        else:
            self.responses.append(bytes(payload))

    def read(self, _length, _timeout):
        return self.responses.pop(0) if self.responses else b""

    def close(self):
        self.closed += 1


class FakeHid:
    def __init__(self, per_key=True):
        self.instance = FakeDevice(per_key)

    def enumerate(self, _vid, _pid):
        return [
            {
                "path": b"raw",
                "usage_page": 0xFF60,
                "usage": 0x61,
                "product_string": "Keychron Q65 Max",
                "product_id": 0x08B0,
            }
        ]

    def device(self):
        return self.instance


@pytest.fixture(autouse=True)
def isolated_device_lock(monkeypatch, tmp_path):
    path = tmp_path / "private" / "device.lock"
    monkeypatch.setattr(device_lock, "_default_lock_path", lambda: path)
    return path


@pytest.fixture
def device_factory():
    devices = []

    def create(**kwargs):
        device = KeychronDevice(**kwargs)
        devices.append(device)
        return device

    yield create
    for device in reversed(devices):
        device.close()


def test_device_uses_report_id_and_32_byte_protocol_payload(device_factory):
    backend = FakeHid()
    device = device_factory(hid_module=backend)

    device.set_led_colors(7, [(43, 255, 255)])

    report = backend.instance.writes[-1]
    assert len(report) == 33
    assert report[:8] == bytes([0, KC_RGB, CMD_SET_LED_COLOR, 7, 1, 43, 255, 255])


def test_device_opens_when_standard_via_works_but_kc_rgb_is_unsupported(device_factory):
    device = device_factory(hid_module=FakeHid(per_key=False))

    assert device.protocol_version() == 1
    assert device.supports_per_key_rgb() is False


def test_led_count_uses_kc_rgb_command(device_factory):
    backend = FakeHid()
    device = device_factory(hid_module=backend)
    backend.instance.responses.append(bytes([KC_RGB, CMD_LED_COUNT, 0, 72]).ljust(32, b"\0"))

    assert device.led_count() == 72


def test_zone_write_clears_full_frame_and_colors_only_selected_leds(device_factory):
    backend = FakeHid(per_key=False)
    device = device_factory(hid_module=backend)
    backend.instance.writes.clear()

    device.set_zone({1: (85, 255, 255)}, total=10)

    assert len(backend.instance.writes) == 2
    first = backend.instance.writes[0]
    second = backend.instance.writes[1]
    assert first[1:9] == bytes([KC_RGB, CMD_SET_LED_COLOR, 0, 9, 0, 0, 0, 85])
    assert second[1:8] == bytes([KC_RGB, CMD_SET_LED_COLOR, 9, 1, 0, 0, 0])


def test_mixed_zone_assigns_only_selected_leds_to_color_region(device_factory):
    backend = FakeHid()
    device = device_factory(hid_module=backend)
    backend.instance.writes.clear()

    device.set_mixed_zone((43, 255, 255), [1, 3], total=4)

    effect = backend.instance.writes[0]
    regions = backend.instance.writes[1]
    assert effect[1:10] == bytes([KC_RGB, CMD_SET_MIXED_EFFECTS, 1, 0, 1, 1, 43, 255, 128])
    assert regions[1:9] == bytes([KC_RGB, CMD_SET_MIXED_REGIONS, 0, 4, 0, 1, 0, 1])


def test_mixed_per_key_indicator_keeps_unselected_leds_in_off_region(device_factory):
    backend = FakeHid()
    device = device_factory(hid_module=backend)
    backend.instance.writes.clear()

    device.configure_mixed_per_key_indicator([1, 3], total=4)

    per_key_effect = next(
        report
        for report in backend.instance.writes
        if report[1:6] == bytes([KC_RGB, CMD_SET_MIXED_EFFECTS, 1, 0, 1])
    )
    regions = next(
        report
        for report in backend.instance.writes
        if report[1:5] == bytes([KC_RGB, CMD_SET_MIXED_REGIONS, 0, 4])
    )
    assert per_key_effect[6] == EFFECT_PER_KEY
    assert regions[5:9] == bytes([0, 1, 0, 1])


def test_clear_rgb_buffer_switches_to_none_effect(device_factory):
    backend = FakeHid()
    device = device_factory(hid_module=backend)
    backend.instance.writes.clear()

    device.clear_rgb_buffer(settle_seconds=0)

    assert backend.instance.writes[-1][1:5] == bytes([0x07, 3, 2, EFFECT_NONE])


def test_restore_lighting_clears_buffer_then_restores_brightness_and_effect(device_factory):
    backend = FakeHid()
    device = device_factory(hid_module=backend)
    backend.instance.writes.clear()

    device.restore_lighting(effect=7, brightness=42)

    payloads = [report[1:5] for report in backend.instance.writes]
    assert payloads == [
        bytes([0x07, 3, 2, EFFECT_NONE]),
        bytes([0x07, 3, 1, 42]),
        bytes([0x07, 3, 2, 7]),
    ]


def test_contender_is_rejected_before_hid_enumeration_or_open(device_factory, monkeypatch):
    device_factory(hid_module=FakeHid())
    contender = FakeHid()
    monkeypatch.setattr(contender, "enumerate", lambda *_: pytest.fail("HID enumeration attempted"))

    with pytest.raises(KeychronError, match="Another orca-keychron process owns the keyboard"):
        device_factory(hid_module=contender)

    assert not contender.instance.opened
    assert not contender.instance.writes


def test_close_releases_ownership_and_prevents_later_writes(device_factory):
    backend = FakeHid()
    device = device_factory(hid_module=backend)
    device.close()
    device.close()

    assert backend.instance.closed == 1
    with pytest.raises(KeychronError, match="closed"):
        device.set_brightness(12)
    assert device_factory(hid_module=FakeHid()).protocol_version() == 1


def test_close_exception_still_releases_ownership(device_factory, monkeypatch):
    backend = FakeHid()
    device = device_factory(hid_module=backend)

    def broken_close():
        raise OSError("fake HID close failure")

    monkeypatch.setattr(backend.instance, "close", broken_close)
    with pytest.raises(OSError, match="fake HID close failure"):
        device.close()
    assert device_factory(hid_module=FakeHid()).protocol_version() == 1


@pytest.mark.parametrize("phase", ["enumerate", "device", "open_path", "write", "read"])
def test_constructor_failure_releases_lock_and_closes_created_handle(
    device_factory, monkeypatch, phase
):
    backend = FakeHid()

    def broken(*_args):
        raise RuntimeError(f"fake {phase} failure")

    target = backend if phase in {"enumerate", "device"} else backend.instance
    monkeypatch.setattr(target, phase, broken)
    with pytest.raises(RuntimeError, match=f"fake {phase} failure"):
        device_factory(hid_module=backend)
    assert backend.instance.closed == (0 if phase in {"enumerate", "device"} else 1)
    assert device_factory(hid_module=FakeHid()).protocol_version() == 1


def test_missing_hid_dependency_releases_lock(device_factory, monkeypatch):
    def missing_hid():
        raise KeychronError("fake missing hidapi")

    monkeypatch.setattr(keychron_hid, "load_hid", missing_hid)
    with pytest.raises(KeychronError, match="fake missing hidapi"):
        device_factory()
    assert device_factory(hid_module=FakeHid()).protocol_version() == 1


@pytest.mark.parametrize("failure", ["open", "no_response", "no_match", "close"])
def test_no_responding_interface_releases_lock(device_factory, monkeypatch, failure):
    backend = FakeHid()
    kwargs = {}
    if failure == "open":
        def broken_open(_path):
            raise OSError("fake missing interface")
        monkeypatch.setattr(backend.instance, "open_path", broken_open)
    elif failure == "no_match":
        kwargs["product"] = "not this keyboard"
    else:
        monkeypatch.setattr(backend.instance, "read", lambda *_: b"")
        if failure == "close":
            def broken_close():
                raise OSError("fake HID close failure")
            monkeypatch.setattr(backend.instance, "close", broken_close)
    with pytest.raises(OSError if failure == "close" else KeychronError):
        device_factory(hid_module=backend, **kwargs)
    assert device_factory(hid_module=FakeHid()).protocol_version() == 1


def test_ownership_is_held_before_open_and_across_candidate_fallback(device_factory, monkeypatch):
    backend = FakeHid()
    candidates = backend.enumerate(0, 0) * 2
    monkeypatch.setattr(backend, "enumerate", lambda *_: candidates)
    first, second = FakeDevice(), FakeDevice()
    monkeypatch.setattr(first, "read", lambda *_: b"")
    devices = iter([first, second])
    monkeypatch.setattr(backend, "device", lambda: next(devices))
    opened = []

    def checked_open(_path):
        contender = DeviceOwnershipLock()
        with pytest.raises(DeviceLockError, match="owns the keyboard"):
            contender.acquire()
        opened.append(True)

    monkeypatch.setattr(first, "open_path", checked_open)
    monkeypatch.setattr(second, "open_path", checked_open)
    device = device_factory(hid_module=backend)
    assert device.protocol_version() == 1
    assert len(opened) == 2
    assert first.closed == 1
    assert second.closed == 0
