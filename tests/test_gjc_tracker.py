import json
import math
from uuid import uuid4

import pytest
from test_gjc_protocol import frame

from orca_keychron_gjc.gjc_protocol import parse_snapshot
from orca_keychron_gjc.gjc_tracker import GjcTracker


def apply(tracker, payload, now=0):
    return tracker.apply(parse_snapshot(payload), now=now)


def test_priority_child_asks_survive_root_done_and_full_recovery():
    tracker = GjcTracker(2)
    row = frame("done")
    row["sessions"].append({"sessionId": "child", "role": "child", "state": "failed",
                                 "pendingAsks": 1, "pendingDecisions": 1})
    apply(tracker, row)
    item = tracker.indicators(0)[0]
    assert (item.state, item.pending_requests, item.agent_count) == ("waiting", 2, 2)
    row["sequence"] = 10
    row["sessions"] = row["sessions"][:1]
    apply(tracker, row, 1)
    assert tracker.indicators(1)[0].state == "done"
    assert tracker.indicators(1)[0].pending_requests == 0


@pytest.mark.parametrize("states,complete,expected", [
    (["done", "failed"], True, "failed"), (["failed", "working"], True, "failed"),
    (["working", "paused"], True, "working"), (["done", "cancelled"], True, "unknown"),
    (["done", "paused"], True, "unknown"), (["idle"], True, "idle"),
    (["done"], False, "unknown"), (["working"], False, "working"),
    (["done", "idle"], True, "done"), (["waiting"], True, "waiting"),
])
def test_priority(states, complete, expected):
    row = frame(states[0])
    row["complete"] = complete
    row["sessions"] += [{"sessionId": str(i), "role": "child", "state": s,
                              "pendingAsks": 0, "pendingDecisions": 0}
                         for i, s in enumerate(states[1:])]
    tracker = GjcTracker(1)
    apply(tracker, row)
    assert tracker.indicators(0)[0].state == expected


def test_lease_disconnect_and_no_old_sequence_regression():
    tracker = GjcTracker(1)
    row = frame("waiting", 4)
    apply(tracker, row)
    assert tracker.indicators(7.99)[0].state == "waiting"
    assert tracker.indicators(8)[0].state == "unknown"
    assert tracker.indicators(8)[0].slot == 0
    row["sequence"] = 3
    assert not apply(tracker, row, 8)
    assert tracker.indicators(8)[0].state == "unknown"
    row["sequence"] = 5
    apply(tracker, row, 9)
    assert tracker.indicators(9)[0].state == "waiting"
    tracker.disconnect(row["producerId"])
    assert tracker.indicators(9)[0].state == "unknown"
    assert not apply(tracker, row, 10)
    row["sequence"] += 1
    row["sessions"][0]["state"] = "done"
    assert apply(tracker, row, 10)
    assert tracker.indicators(10)[0].state == "done"


def test_fractional_lease_deadline_uses_absolute_bounds():
    tracker = GjcTracker(1)
    row = frame("working")
    received_at = 0.001
    apply(tracker, row, received_at)
    deadline = received_at + tracker.lease_seconds

    # This cancellation rounds below the lease and exercised the old subtraction check.
    assert deadline - received_at < tracker.lease_seconds
    before = tracker.indicators(math.nextafter(deadline, received_at))[0]
    assert (before.state, before.connected, before.slot) == ("working", True, 0)
    expired = tracker.indicators(deadline)[0]
    assert (expired.state, expired.connected, expired.slot) == ("unknown", False, 0)
    backward = tracker.indicators(math.nextafter(received_at, -math.inf))[0]
    assert (backward.state, backward.connected, backward.slot) == ("unknown", False, 0)


def test_stable_slots_shared_session_id_overflow_clear_and_closure(tmp_path):
    registry = tmp_path / "registry.json"
    tracker = GjcTracker(2, registry)
    first, second, third = frame(), frame(), frame()
    for row in (first, second, third):
        apply(tracker, row)
    assert [r["launchId"] for r in tracker.status(0)["overflow"]] == [third["launchId"]]
    tracker.disconnect(first["producerId"])
    assert [i.slot for i in tracker.indicators(1000)] == [0, 1]
    assert tracker.clear(first["launchId"])
    assert not tracker.clear(first["launchId"])
    assert [(i.launch_id, i.slot) for i in tracker.indicators(0)] == [
        (third["launchId"], 0), (second["launchId"], 1)]
    second.update(sequence=2, closed=True)
    assert apply(tracker, second)
    assert not apply(tracker, second)
    restored = GjcTracker(2, registry)
    assert restored.indicators(0)[0].state == "unknown"
    assert not apply(restored, first)
    assert not apply(restored, third)
    third["sequence"] += 1
    assert apply(restored, third)
    assert restored.indicators(0)[0].state == "working"
    assert registry.stat().st_mode & 0o777 == 0o600
    assert json.loads(registry.read_text())["launches"][0]["state"] == "unknown"


def test_changed_producer_and_launch_metadata_cannot_seize():
    tracker = GjcTracker(1)
    row = frame()
    apply(tracker, row)
    other = dict(row, producerId=str(uuid4()), sequence=2)
    assert not apply(tracker, other)
    assert not apply(tracker, dict(row, pid=456, sequence=3))
    tracker.disconnect(row["producerId"])
    assert not apply(tracker, other)
    assert tracker.indicators(0)[0].state == "unknown"


def test_registry_refuses_nonprivate_and_corrupt_files(tmp_path):
    registry = tmp_path / "registry"
    registry.write_text("{}")
    registry.chmod(0o644)
    with pytest.raises(PermissionError):
        GjcTracker(1, registry)
    registry.chmod(0o600)
    with pytest.raises(ValueError):
        GjcTracker(1, registry)


def test_registry_shrink_preserves_available_assignments_and_overflow(tmp_path):
    path = tmp_path / "registry.json"
    tracker = GjcTracker(3, path)
    rows = [frame(), frame(), frame()]
    for row in rows:
        apply(tracker, row)
    restored = GjcTracker(2, path)
    assert [(i.launch_id, i.slot, i.state) for i in restored.indicators()] == [
        (rows[0]["launchId"], 0, "unknown"), (rows[1]["launchId"], 1, "unknown")]
    assert restored.status()["overflow"][0]["launchId"] == rows[2]["launchId"]


@pytest.mark.parametrize("field,value", [("maxSlots", True), ("maxSlots", 0),
                                          ("maxSlots", 1025)])
def test_registry_validates_saved_capacity(tmp_path, field, value):
    path = tmp_path / "registry.json"
    tracker = GjcTracker(1, path)
    apply(tracker, frame())
    payload = json.loads(path.read_text())
    payload[field] = value
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        GjcTracker(1, path)
