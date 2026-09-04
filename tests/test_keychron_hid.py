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
)


class FakeDevice:
    def __init__(self, per_key=True):
        self.per_key = per_key
        self.writes = []
        self.responses = []

    def open_path(self, _path):
        pass

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
        pass


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


def test_device_uses_report_id_and_32_byte_protocol_payload():
    backend = FakeHid()
    device = KeychronDevice(hid_module=backend)

    device.set_led_colors(7, [(43, 255, 255)])

    report = backend.instance.writes[-1]
    assert len(report) == 33
    assert report[:8] == bytes([0, KC_RGB, CMD_SET_LED_COLOR, 7, 1, 43, 255, 255])


def test_device_opens_when_standard_via_works_but_kc_rgb_is_unsupported():
    device = KeychronDevice(hid_module=FakeHid(per_key=False))

    assert device.protocol_version() == 1
    assert device.supports_per_key_rgb() is False


def test_led_count_uses_kc_rgb_command():
    backend = FakeHid()
    device = KeychronDevice(hid_module=backend)
    backend.instance.responses.append(bytes([KC_RGB, CMD_LED_COUNT, 0, 72]).ljust(32, b"\0"))

    assert device.led_count() == 72


def test_zone_write_clears_full_frame_and_colors_only_selected_leds():
    backend = FakeHid(per_key=False)
    device = KeychronDevice(hid_module=backend)
    backend.instance.writes.clear()

    device.set_zone({1: (85, 255, 255)}, total=10)

    assert len(backend.instance.writes) == 2
    first = backend.instance.writes[0]
    second = backend.instance.writes[1]
    assert first[1:9] == bytes([KC_RGB, CMD_SET_LED_COLOR, 0, 9, 0, 0, 0, 85])
    assert second[1:8] == bytes([KC_RGB, CMD_SET_LED_COLOR, 9, 1, 0, 0, 0])


def test_mixed_zone_assigns_only_selected_leds_to_color_region():
    backend = FakeHid()
    device = KeychronDevice(hid_module=backend)
    backend.instance.writes.clear()

    device.set_mixed_zone((43, 255, 255), [1, 3], total=4)

    effect = backend.instance.writes[0]
    regions = backend.instance.writes[1]
    assert effect[1:10] == bytes([KC_RGB, CMD_SET_MIXED_EFFECTS, 1, 0, 1, 1, 43, 255, 128])
    assert regions[1:9] == bytes([KC_RGB, CMD_SET_MIXED_REGIONS, 0, 4, 0, 1, 0, 1])


def test_mixed_per_key_indicator_keeps_unselected_leds_in_off_region():
    backend = FakeHid()
    device = KeychronDevice(hid_module=backend)
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


def test_clear_rgb_buffer_switches_to_none_effect():
    backend = FakeHid()
    device = KeychronDevice(hid_module=backend)
    backend.instance.writes.clear()

    device.clear_rgb_buffer(settle_seconds=0)

    assert backend.instance.writes[-1][1:5] == bytes([0x07, 3, 2, EFFECT_NONE])


def test_restore_lighting_clears_buffer_then_restores_brightness_and_effect():
    backend = FakeHid()
    device = KeychronDevice(hid_module=backend)
    backend.instance.writes.clear()

    device.restore_lighting(effect=7, brightness=42)

    payloads = [report[1:5] for report in backend.instance.writes]
    assert payloads == [
        bytes([0x07, 3, 2, EFFECT_NONE]),
        bytes([0x07, 3, 1, 42]),
        bytes([0x07, 3, 2, 7]),
    ]
