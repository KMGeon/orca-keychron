import pytest

from orca_keychron.indicator import Indicator
from orca_keychron.keychron_hid import EFFECT_MIXED, KeychronError
from orca_keychron.orca_status import OrcaStatusError
from orca_keychron.rendering import OFF


class UnsupportedDevice:
    product = "Keychron Q65 Max"

    def __init__(self):
        self.closed = False

    def supports_per_key_rgb(self):
        return False

    def close(self):
        self.closed = True


def test_indicator_rejects_firmware_without_per_key_rgb():
    device = UnsupportedDevice()
    indicator = Indicator(source=object(), device_factory=lambda **_kwargs: device)

    with pytest.raises(KeychronError, match="does not enable KC_RGB"):
        indicator.run()

    assert device.closed is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"zone": [-1]},
        {"poll_interval": 0},
        {"poll_interval": float("nan")},
        {"led_total": 0},
        {"led_total": 257},
    ],
)
def test_indicator_rejects_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        Indicator(source=object(), **kwargs)


class SupportedDevice:
    product = "Keychron Q65 Max"

    def __init__(self):
        self.configured = False
        self.restored = None
        self.closed = False

    def supports_per_key_rgb(self):
        return True

    def get_effect(self):
        return 7

    def get_brightness(self):
        return 42

    def led_count(self):
        return 100

    def configure_mixed_per_key_indicator(self, _zone, _total):
        self.configured = True

    def restore_lighting(self, effect, brightness):
        self.restored = (effect, brightness)

    def close(self):
        self.closed = True


class StopListener:
    def __init__(self, indicator):
        self.indicator = indicator
        self.stopped = False

    def start(self):
        self.indicator.stop()

    def stop(self):
        self.stopped = True


class Source:
    command = ("orca",)


def test_indicator_restores_previous_lighting_on_exit():
    device = SupportedDevice()
    indicator = Indicator(source=Source(), device_factory=lambda **_kwargs: device)
    listener = StopListener(indicator)
    indicator.listener_factory = lambda _selection: listener

    indicator.run()

    assert device.configured is True
    assert device.restored == (7, 42)
    assert device.closed is True
    assert listener.stopped is True


def test_indicator_turns_zone_off_when_orca_status_is_unavailable():
    class PollingDevice(SupportedDevice):
        def __init__(self):
            super().__init__()
            self.colors = None

        def get_effect(self):
            return EFFECT_MIXED

        def set_zone(self, colors, total):
            self.colors = (colors, total)

    class PassiveListener:
        def start(self):
            pass

        def stop(self):
            pass

    class FailingSource:
        command = ("orca",)

        def snapshot(self):
            indicator.stop()
            raise OrcaStatusError("offline")

    device = PollingDevice()
    indicator = Indicator(
        source=FailingSource(),
        zone=(1, 2),
        device_factory=lambda **_kwargs: device,
        listener_factory=lambda _selection: PassiveListener(),
    )

    indicator.run()

    assert device.colors == ({1: OFF, 2: OFF}, 100)
