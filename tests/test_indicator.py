import threading
from types import SimpleNamespace

import pytest

from orca_keychron.indicator import Indicator
from orca_keychron.keychron_hid import EFFECT_MIXED, KeychronError
from orca_keychron.models import OrcaAgent
from orca_keychron.orca_navigation import OrcaWorktreeTab
from orca_keychron.orca_status import OrcaStatusError
from orca_keychron.rendering import GREEN, OFF, YELLOW


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
        {"mode": "unsupported"},
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


class PassiveListener:
    def start(self):
        pass

    def stop(self):
        pass


class RecordingDevice(SupportedDevice):
    def __init__(self):
        super().__init__()
        self.frames = []

    def get_effect(self):
        return EFFECT_MIXED

    def set_zone(self, colors, total):
        self.frames.append(colors)


def agent(state):
    return OrcaAgent("pane", state, "codex", "repo::/one", "local")


def run_bounded(indicator):
    # Fail instead of hanging pytest if a regression prevents loop progress.
    timer = threading.Timer(3, indicator.stop)
    timer.start()
    try:
        indicator.run()
    finally:
        timer.cancel()
        timer.join()


@pytest.mark.parametrize("failure", ["offline", "CLI request timed out"])
def test_indicator_clears_failed_snapshot_and_recovers(failure):
    class RecoveringSource:
        command = ("orca",)
        calls = 0

        def snapshot(self):
            self.calls += 1
            if self.calls == 2:
                raise OrcaStatusError(failure)
            return [agent("working" if self.calls == 1 else "done")]

    class Device(RecordingDevice):
        def set_zone(self, colors, total):
            super().set_zone(colors, total)
            if colors[1] == OFF and any(frame[1] == YELLOW for frame in self.frames):
                assert indicator.selection.pop_ready(0) is None
            if colors[1] == GREEN:
                indicator.stop()

    device = Device()
    source = RecoveringSource()
    indicator = Indicator(
        source=source, zone=(1,), poll_interval=0.01,
        device_factory=lambda **_kwargs: device,
        listener_factory=lambda _selection: PassiveListener(),
    )
    run_bounded(indicator)

    assert [frame[1] for frame in device.frames] == [OFF, YELLOW, OFF, GREEN]
    assert source.calls in (3, 4)  # A fourth request may start before the green frame stops us.
    assert device.restored == (EFFECT_MIXED, 42)
    assert device.closed


def test_slow_poll_does_not_block_navigation_health_checks_or_restore(monkeypatch):
    started = threading.Event()
    released = threading.Event()
    navigated = threading.Event()
    source_finished = threading.Event()
    clock = [0.0]

    class SlowSource:
        command = ("orca",)
        calls = 0

        def snapshot(self):
            self.calls += 1
            started.set()
            assert released.wait(3), "Lighting was not restored while the request was pending"
            source_finished.set()
            return []

    class Device(RecordingDevice):
        health_checks = 0

        def get_effect(self):
            self.health_checks += 1
            if self.health_checks == 4:
                assert started.is_set()
                assert not source_finished.is_set()
                assert navigated.is_set()
                indicator.stop()
            return EFFECT_MIXED

        def restore_lighting(self, effect, brightness):
            super().restore_lighting(effect, brightness)
            assert not source_finished.is_set()
            released.set()

    class Selection:
        calls = 0

        def pop_ready(self, now):
            self.calls += 1
            if self.calls == 1:
                assert started.wait(1)
                return "pane"
            assert navigated.wait(1)
            # Cross two lighting health-check deadlines without a real 20s wait.
            clock[0] += 11.0
            return None

    def open_pane(_self, pane):
        assert pane == "pane"
        assert not source_finished.is_set()
        navigated.set()
        return OrcaWorktreeTab("repo::/one", "tab")

    monkeypatch.setattr("orca_keychron.indicator.time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr("orca_keychron.indicator.OrcaWorktreeTabNavigator.open", open_pane)
    device = Device()
    source = SlowSource()
    indicator = Indicator(
        source=source, zone=(1,), poll_interval=0.01,
        device_factory=lambda **_kwargs: device,
        listener_factory=lambda _selection: PassiveListener(),
    )
    indicator.selection = Selection()
    run_bounded(indicator)

    assert source.calls == 1
    assert device.health_checks == 4
    assert device.frames == [{1: OFF}]
    assert navigated.is_set()
    assert source_finished.is_set()
    assert device.restored == (EFFECT_MIXED, 42)
    assert device.closed
    assert not any(t.name.startswith("orca-status") for t in threading.enumerate())


def gjc_indicator(state):
    # Deliberately has no worktree_id/host_id; GJC identity is its launch.
    return SimpleNamespace(
        launch_id="launch-one", identity_label="launch-one", state=state,
        slot=0, target_pane_keys=("gjc-tab:leaf",), agent_count=3,
    )


def test_gjc_consumes_pushed_model_and_expires_lease_without_orca_polling(monkeypatch):
    from orca_keychron.rendering import ORANGE, UNKNOWN

    class PushSource:
        command = ("orca",)
        calls = 0
        started = False
        stopped = False

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

        def indicators(self, now):
            assert self.started
            assert isinstance(now, float)
            state = ("waiting", "unknown", "working", "done")[min(self.calls, 3)]
            self.calls += 1
            return [gjc_indicator(state)]

        def snapshot(self):
            pytest.fail("GJC mode must never poll Orca or GJC snapshots")

    class Device(RecordingDevice):
        def set_zone(self, colors, total):
            super().set_zone(colors, total)
            if colors[1] == ORANGE:
                indicator.selection.press("1", 0, option_only=True)
            if colors[1] == GREEN:
                indicator.stop()

    def no_worktree_tracker(*_args, **_kwargs):
        pytest.fail("GJC launches must not be aggregated as Orca worktrees")

    opened = []

    def open_pane(_self, pane):
        opened.append(pane)
        return OrcaWorktreeTab("actual-worktree", "gjc-tab")

    monkeypatch.setattr("orca_keychron.indicator.WorktreeTracker", no_worktree_tracker)
    monkeypatch.setattr("orca_keychron.indicator.OrcaWorktreeTabNavigator.open", open_pane)
    source = PushSource()
    device = Device()
    indicator = Indicator(
        source, zone=(1,), mode="gjc", device_factory=lambda **_: device,
        listener_factory=lambda _: PassiveListener(),
    )

    run_bounded(indicator)

    assert [frame[1] for frame in device.frames] == [ORANGE, UNKNOWN, YELLOW, GREEN]
    assert opened == ["gjc-tab:leaf"]
    assert source.calls == 4
    assert source.started and source.stopped
    assert indicator.tracker is None
    assert device.restored == (EFFECT_MIXED, 42)
    assert device.closed
    assert not any(t.name.startswith("orca-status") for t in threading.enumerate())


@pytest.mark.parametrize("failure_at", ["start", "indicators", "stop"])
def test_gjc_runtime_failure_always_closes_source_and_device(failure_at):
    class FailingSource:
        command = ("orca",)
        stops = 0

        def start(self):
            if failure_at == "start":
                raise RuntimeError("start failed")

        def indicators(self, now):
            if failure_at == "indicators":
                raise RuntimeError("indicators failed")
            indicator.stop()
            return []

        def stop(self):
            self.stops += 1
            # Source cleanup must not delay restoring the device lighting.
            assert device.closed
            if failure_at == "stop":
                raise RuntimeError("stop failed")

    source = FailingSource()
    device = RecordingDevice()
    indicator = Indicator(
        source, mode="gjc", device_factory=lambda **_: device,
        listener_factory=lambda _: PassiveListener(),
    )

    with pytest.raises(RuntimeError, match=f"{failure_at} failed"):
        run_bounded(indicator)

    assert source.stops == 1
    assert device.closed
    if failure_at == "start":
        assert not device.configured
    else:
        assert device.restored == (EFFECT_MIXED, 42)
