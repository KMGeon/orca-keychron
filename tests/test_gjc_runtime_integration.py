import json
import socket
import time
from tempfile import TemporaryDirectory
from uuid import uuid4

from orca_keychron.indicator import Indicator
from orca_keychron.keychron_hid import EFFECT_MIXED
from orca_keychron.orca_navigation import OrcaWorktreeTab
from orca_keychron.rendering import GREEN, ORANGE, SKY_BLUE, UNKNOWN
from orca_keychron_gjc.gjc_source import GjcStatusSource, request_control


def _snapshot(producer_id, launch_id, sequence, *, complete, pending_decisions=0):
    return {
        "version": 1,
        "type": "snapshot",
        "producerId": producer_id,
        "sequence": sequence,
        "launchId": launch_id,
        "pid": 4242,
        "startedAt": 1788632000000,
        "complete": complete,
        "closed": False,
        "root": {
            "sessionId": "root-session",
            "terminalHandle": "term_gjc",
            "paneKey": "tab-gjc:leaf-root",
            "worktreeId": "repo::/gjc-worktree",
        },
        "sessions": [
            {
                "sessionId": "root-session",
                "role": "root",
                "state": "done",
                "pendingAsks": 0,
                "pendingDecisions": 0,
            },
            {
                "sessionId": "decision-child",
                "role": "child",
                "state": "waiting" if pending_decisions else "done",
                "pendingAsks": 0,
                "pendingDecisions": pending_decisions,
            },
        ],
    }


def _send(client, payload):
    client.sendall(json.dumps(payload, separators=(",", ":")).encode() + b"\n")


def _await_status(endpoint, predicate):
    deadline = time.monotonic() + 3
    latest = None
    while time.monotonic() < deadline:
        latest = request_control(endpoint)["status"]
        if predicate(latest):
            return latest
    raise AssertionError(f"receiver did not reach expected state: {latest}")


class PipelineDevice:
    product = "Fake Keychron HID"

    def __init__(self, on_color):
        self.on_color = on_color
        self.frames = []
        self.restored = None
        self.closed = False

    def supports_per_key_rgb(self):
        return True

    def get_effect(self):
        return EFFECT_MIXED

    def get_brightness(self):
        return 42

    def led_count(self):
        return 4

    def configure_mixed_per_key_indicator(self, _zone, _total):
        pass

    def set_zone(self, colors, _total):
        self.frames.append(dict(colors))
        self.on_color(colors[1])

    def restore_lighting(self, effect, brightness):
        self.restored = effect, brightness

    def close(self):
        self.closed = True


def test_actual_receiver_snapshot_drives_palette_fake_hid_and_navigation(monkeypatch):
    """GJC-STATE/RENDER/NAV: exercise the real receiver, not fabricated indicators."""
    with TemporaryDirectory(prefix="gjc-pipeline-", dir="/tmp") as directory:
        endpoint = f"{directory}/bridge.sock"
        source = GjcStatusSource(endpoint, ("orca",), max_slots=2)
        producer_id, launch_id = str(uuid4()), str(uuid4())
        producer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        holder = {}
        stage = {"value": "waiting"}
        opened = []

        class PublishingListener:
            def __init__(self, selection):
                holder["selection"] = selection

            def start(self):
                producer.connect(endpoint)
                _send(
                    producer,
                    _snapshot(
                        producer_id,
                        launch_id,
                        1,
                        complete=True,
                        pending_decisions=1,
                    ),
                )
                _await_status(
                    endpoint,
                    lambda status: status["launches"]
                    and status["launches"][0]["state"] == "waiting",
                )

            def stop(self):
                producer.close()

        def transition(color):
            if color == ORANGE and stage["value"] == "waiting":
                holder["selection"].press("1", time.monotonic(), option_only=True)
                _send(producer, _snapshot(producer_id, launch_id, 2, complete=False))
                _await_status(
                    endpoint,
                    lambda status: status["launches"][0]["sequence"] == 2,
                )
                stage["value"] = "incomplete"
            elif color == UNKNOWN and stage["value"] == "incomplete":
                _send(producer, _snapshot(producer_id, launch_id, 3, complete=True))
                _await_status(
                    endpoint,
                    lambda status: status["launches"][0]["sequence"] == 3,
                )
                stage["value"] = "done"
            elif color == GREEN and stage["value"] == "done":
                producer.shutdown(socket.SHUT_RDWR)
                producer.close()
                _await_status(
                    endpoint,
                    lambda status: status["launches"][0]["connected"] is False,
                )
                stage["value"] = "disconnected"
            elif color == UNKNOWN and stage["value"] == "disconnected":
                indicator.stop()
                stage["value"] = "stopped"

        def open_pane(_navigator, pane_key):
            opened.append(pane_key)
            return OrcaWorktreeTab("repo::/gjc-worktree", "tab-gjc")

        monkeypatch.setattr("orca_keychron.indicator.signal.signal", lambda *_args: None)
        monkeypatch.setattr("orca_keychron.indicator.OrcaWorktreeTabNavigator.open", open_pane)
        device = PipelineDevice(transition)
        indicator = Indicator(
            source,
            zone=(1, 2),
            led_total=4,
            mode="gjc",
            device_factory=lambda **_kwargs: device,
            listener_factory=PublishingListener,
        )

        indicator.run()

        assert [frame[1] for frame in device.frames] == [ORANGE, UNKNOWN, GREEN, UNKNOWN]
        assert all(frame[2] == SKY_BLUE for frame in device.frames)
        assert opened == ["tab-gjc:leaf-root"]
        assert stage["value"] == "stopped"
        assert device.restored == (EFFECT_MIXED, 42)
        assert device.closed is True
        assert source._thread is None


def test_actual_receiver_promotes_overflow_only_after_explicit_slot_release():
    """GJC-LIFETIME: disconnects retain slots; closed roots fill holes without stealing."""
    with TemporaryDirectory(prefix="gjc-overflow-", dir="/tmp") as directory:
        endpoint = f"{directory}/bridge.sock"
        source = GjcStatusSource(endpoint, ("orca",), max_slots=2)
        clients = []
        identities = [(str(uuid4()), str(uuid4())) for _ in range(3)]
        source.start()
        try:
            for index, (producer_id, launch_id) in enumerate(identities):
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.connect(endpoint)
                clients.append(client)
                _send(
                    client,
                    _snapshot(producer_id, launch_id, 1, complete=True),
                )
                _await_status(endpoint, lambda status, n=index + 1: len(status["launches"]) == n)

            before = _await_status(endpoint, lambda status: len(status["overflow"]) == 1)
            before_slots = {row["launchId"]: row["slot"] for row in before["launches"]}
            assert before_slots == {
                identities[0][1]: 0,
                identities[1][1]: 1,
                identities[2][1]: None,
            }

            closed = _snapshot(*identities[1], 2, complete=True)
            closed["closed"] = True
            closed["sessions"] = []
            _send(clients[1], closed)
            after = _await_status(
                endpoint,
                lambda status: len(status["launches"]) == 2
                and not status["overflow"],
            )
            assert {row["launchId"]: row["slot"] for row in after["launches"]} == {
                identities[0][1]: 0,
                identities[2][1]: 1,
            }
        finally:
            for client in clients:
                client.close()
            source.stop()
