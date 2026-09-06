"""Requirement-driven invariants for the GJC protocol and launch tracker.

These tests deliberately use an independent oracle instead of duplicating the
tracker's branch order.  The generated traces are deterministic so a failure
can be replayed as one ordinary pytest node.
"""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

from orca_keychron_gjc.gjc_protocol import (
    MAX_REQUESTS,
    MAX_SAFE_INTEGER,
    MAX_SESSIONS,
    GjcProtocolError,
    parse_snapshot,
)
from orca_keychron_gjc.gjc_tracker import GjcTracker

PRIORITY = ("waiting", "failed", "working", "unknown", "done", "idle")
UNCERTAIN_STATES = frozenset({"unknown", "paused", "cancelled"})
REPO_ROOT = Path(__file__).resolve().parents[1]


def canonical_uuid(number: int) -> str:
    return str(UUID(int=number))


def wire_frame(
    launch_number: int = 1,
    *,
    states: tuple[str, ...] = ("working",),
    sequence: int = 1,
    complete: bool = True,
    closed: bool = False,
    pending: tuple[tuple[int, int], ...] | None = None,
) -> dict[str, object]:
    root_id = f"root-{launch_number}"
    counters = pending or tuple((0, 0) for _ in states)
    sessions = []
    for index, (state, (asks, decisions)) in enumerate(zip(states, counters)):
        sessions.append(
            {
                "sessionId": root_id if index == 0 else f"child-{launch_number}-{index}",
                "role": "root" if index == 0 else "child",
                "state": state,
                "pendingAsks": asks,
                "pendingDecisions": decisions,
            }
        )
    return {
        "version": 1,
        "type": "snapshot",
        "producerId": canonical_uuid(10_000 + launch_number),
        "sequence": sequence,
        "launchId": canonical_uuid(20_000 + launch_number),
        "pid": 1_000 + launch_number,
        "startedAt": 1_000_000 + launch_number,
        "complete": complete,
        "closed": closed,
        "root": {
            "sessionId": root_id,
            "terminalHandle": f"term-{launch_number}",
            "paneKey": f"tab:{launch_number}",
            "worktreeId": "worktree",
        },
        "sessions": sessions,
    }


def apply_wire(tracker: GjcTracker, payload: dict[str, object], now: float = 0) -> bool:
    return tracker.apply(parse_snapshot(payload), now=now)


def oracle_state(
    states: tuple[str, ...], *, complete: bool = True, pending_requests: int = 0
) -> str:
    active = {state for state in states if state != "closed"}
    if pending_requests or "waiting" in active:
        return "waiting"
    if "failed" in active:
        return "failed"
    if "working" in active:
        return "working"
    if not complete or active & UNCERTAIN_STATES:
        return "unknown"
    if "done" in active:
        return "done"
    if active == {"idle"}:
        return "idle"
    return "unknown"


def test_all_priority_subsets_and_order_permutations_match_independent_oracle():
    """STATE-1: every ordering of every priority subset has one stable result."""
    tracker = GjcTracker(1)
    sequence = 0
    for size in range(1, len(PRIORITY) + 1):
        for subset in itertools.combinations(PRIORITY, size):
            expected = oracle_state(subset)
            for states in itertools.permutations(subset):
                sequence += 1
                payload = wire_frame(states=states, sequence=sequence)
                assert apply_wire(tracker, payload)
                assert tracker.indicators(0)[0].state == expected, states


def test_priority_is_unchanged_by_session_multiplicity_and_waiting_position():
    """STATE-1: ten working sessions cannot drown out one waiting session."""
    tracker = GjcTracker(1)
    for position in range(11):
        states = ["working"] * 10
        states.insert(position, "waiting")
        payload = wire_frame(states=tuple(states), sequence=position + 1)
        assert apply_wire(tracker, payload)
        assert tracker.indicators(0)[0].state == "waiting"


@pytest.mark.parametrize("uncertain", ["unknown", "paused", "cancelled"])
def test_incomplete_and_uncertain_states_obey_the_same_priority_boundary(uncertain):
    """STATE-2: failed/working outrank incomplete; incomplete outranks done/idle."""
    cases = (
        (("failed", uncertain, "done"), False, "failed"),
        (("working", uncertain, "done"), False, "working"),
        (("done", "idle"), False, "unknown"),
        ((uncertain, "done"), True, "unknown"),
    )
    tracker = GjcTracker(1)
    for sequence, (states, complete, expected) in enumerate(cases, 1):
        assert apply_wire(
            tracker,
            wire_frame(states=states, complete=complete, sequence=sequence),
        )
        assert tracker.indicators(0)[0].state == expected


def test_closed_session_pending_request_retains_human_priority_but_not_agent_count():
    """STATE-3: shutdown does not silently resolve an outstanding human request."""
    tracker = GjcTracker(1)
    payload = wire_frame(
        states=("done", "closed"),
        pending=((0, 0), (1, 1)),
    )
    assert apply_wire(tracker, payload)
    indicator = tracker.indicators(0)[0]
    assert (indicator.state, indicator.agent_count, indicator.pending_requests) == (
        "waiting",
        1,
        2,
    )


def test_explicit_root_closure_reclaims_slot_even_with_a_pending_child():
    """LIFE-1: only the frame-level explicit closure retires the launch."""
    tracker = GjcTracker(1)
    payload = wire_frame(states=("done", "waiting"), pending=((0, 0), (1, 0)))
    assert apply_wire(tracker, payload)
    payload.update(sequence=2, closed=True)
    assert apply_wire(tracker, payload)
    assert tracker.status(0)["launches"] == []
    assert not apply_wire(tracker, payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("version",), True),
        (("sequence",), 1.0),
        (("sequence",), MAX_SAFE_INTEGER + 1),
        (("pid",), False),
        (("startedAt",), 0),
        (("complete",), 1),
        (("closed",), 0),
        (("root", "terminalHandle"), b"term"),
        (("sessions", 0, "role"), ["root"]),
        (("sessions", 0, "state"), "WAITING"),
        (("sessions", 0, "pendingAsks"), 1.0),
        (("sessions", 0, "pendingDecisions"), True),
    ],
)
def test_malformed_wire_scalar_types_are_rejected(path, value):
    """WIRE-1: JSON-looking Python scalars cannot exploit bool/int coercions."""
    payload = wire_frame()
    target = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index,assignment]
    target[path[-1]] = value  # type: ignore[index]
    with pytest.raises(GjcProtocolError):
        parse_snapshot(payload)


@pytest.mark.parametrize("counter", ["pendingAsks", "pendingDecisions"])
def test_request_counter_bounds_are_exact(counter):
    """WIRE-2: per-session pending counters accept 0..128 and nothing else."""
    for value in (0, MAX_REQUESTS):
        payload = wire_frame()
        payload["sessions"][0][counter] = value  # type: ignore[index]
        assert getattr(parse_snapshot(payload).sessions[0], counter.replace("pending", "pending_").lower()) == value
    for value in (-1, MAX_REQUESTS + 1, False, 1.5):
        payload = wire_frame()
        payload["sessions"][0][counter] = value  # type: ignore[index]
        with pytest.raises(GjcProtocolError):
            parse_snapshot(payload)


def test_session_and_total_counter_boundaries_are_preserved_without_overflow():
    """WIRE-2: 256 sessions x two 128 counters has an exact bounded total."""
    states = ("waiting",) + ("working",) * (MAX_SESSIONS - 1)
    counters = tuple((MAX_REQUESTS, MAX_REQUESTS) for _ in states)
    snapshot = parse_snapshot(wire_frame(states=states, pending=counters))
    tracker = GjcTracker(1)
    assert tracker.apply(snapshot, now=0)
    indicator = tracker.indicators(0)[0]
    assert indicator.agent_count == MAX_SESSIONS
    assert indicator.pending_requests == MAX_SESSIONS * MAX_REQUESTS * 2


def test_identifier_and_collection_limits_are_exact():
    """WIRE-3: 512-byte identifiers and 256 sessions are the inclusive maxima."""
    payload = wire_frame(states=("working",) + ("idle",) * (MAX_SESSIONS - 1))
    payload["root"]["terminalHandle"] = "t" * 512  # type: ignore[index]
    assert len(parse_snapshot(payload).sessions) == MAX_SESSIONS
    payload["root"]["terminalHandle"] = "t" * 513  # type: ignore[index]
    with pytest.raises(GjcProtocolError):
        parse_snapshot(payload)
    payload = wire_frame(states=("working",) + ("idle",) * MAX_SESSIONS)
    with pytest.raises(GjcProtocolError):
        parse_snapshot(payload)


def test_duplicate_sessions_and_nonunique_or_missing_root_are_rejected():
    """WIRE-4: session IDs are launch-global and exactly one matches root."""
    duplicate = wire_frame(states=("working", "done"))
    duplicate["sessions"][1]["sessionId"] = duplicate["sessions"][0]["sessionId"]  # type: ignore[index]
    with pytest.raises(GjcProtocolError):
        parse_snapshot(duplicate)

    second_root = wire_frame(states=("working", "done"))
    second_root["sessions"][1]["role"] = "root"  # type: ignore[index]
    with pytest.raises(GjcProtocolError):
        parse_snapshot(second_root)

    missing_root = wire_frame(states=("working",))
    missing_root["sessions"][0]["role"] = "child"  # type: ignore[index]
    with pytest.raises(GjcProtocolError):
        parse_snapshot(missing_root)


def test_complete_snapshot_recovers_an_incomplete_gap_but_replays_cannot_regress():
    """SEQ-1: a high complete sequence replaces the model; older frames are inert."""
    tracker = GjcTracker(1)
    incomplete = wire_frame(states=("done",), sequence=2, complete=False)
    assert apply_wire(tracker, incomplete, now=1)
    assert tracker.indicators(1)[0].state == "unknown"

    recovered = wire_frame(states=("done",), sequence=100, complete=True)
    assert apply_wire(tracker, recovered, now=2)
    assert tracker.indicators(2)[0].state == "done"

    for stale_sequence in (100, 99, 3, 2, 1):
        stale = wire_frame(states=("failed",), sequence=stale_sequence, complete=True)
        assert not apply_wire(tracker, stale, now=3)
        assert tracker.indicators(3)[0].state == "done"


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("producerId",), canonical_uuid(999_001)),
        (("pid",), 99_001),
        (("startedAt",), 99_002),
        (("root", "terminalHandle"), "term-replaced"),
        (("root", "paneKey"), "tab:replaced"),
        (("root", "worktreeId"), "worktree-replaced"),
    ],
)
def test_stale_generation_metadata_cannot_seize_a_launch(path, replacement):
    """SEQ-2: sequence alone cannot authorize a different process or pane generation."""
    tracker = GjcTracker(1)
    original = wire_frame(sequence=1)
    assert apply_wire(tracker, original)
    changed = wire_frame(states=("failed",), sequence=2)
    target = changed
    for key in path[:-1]:
        target = target[key]  # type: ignore[index,assignment]
    target[path[-1]] = replacement  # type: ignore[index]
    assert not apply_wire(tracker, changed)
    assert tracker.indicators(0)[0].state == "working"


def test_root_session_switch_is_not_mistaken_for_a_new_process_generation():
    """SEQ-3: /new changes current root session, while pane/process identity stays fixed."""
    tracker = GjcTracker(1)
    original = wire_frame(sequence=1)
    assert apply_wire(tracker, original)
    switched = wire_frame(states=("done", "working"), sequence=2)
    switched["root"]["sessionId"] = "new-root"  # type: ignore[index]
    switched["sessions"][0]["sessionId"] = "new-root"  # type: ignore[index]
    assert apply_wire(tracker, switched)
    indicator = tracker.indicators(0)[0]
    assert (indicator.state, indicator.slot, indicator.target_pane_keys) == (
        "working",
        0,
        ("tab:1",),
    )


def test_generated_launch_trace_preserves_slots_overflow_and_tombstones(tmp_path):
    """LIFE-2: disconnect, clear, restart, closure and overflow have one stable oracle."""
    registry = tmp_path / "registry.json"
    tracker = GjcTracker(2, registry)
    frames = [wire_frame(number, states=("working",)) for number in range(1, 6)]
    for payload in frames:
        assert apply_wire(tracker, payload)

    rows = tracker.status(0)["launches"]
    assert [(row["launchId"], row["slot"]) for row in rows] == [
        (frames[0]["launchId"], 0),
        (frames[1]["launchId"], 1),
        (frames[2]["launchId"], None),
        (frames[3]["launchId"], None),
        (frames[4]["launchId"], None),
    ]

    tracker.disconnect(frames[0]["producerId"])
    assert tracker.status(100)["launches"][0]["slot"] == 0
    assert tracker.clear(frames[0]["launchId"])
    assert [(row["launchId"], row["slot"]) for row in tracker.status(0)["launches"]] == [
        (frames[1]["launchId"], 1),
        (frames[2]["launchId"], 0),
        (frames[3]["launchId"], None),
        (frames[4]["launchId"], None),
    ]

    restored = GjcTracker(2, registry)
    assert all(row["state"] == "unknown" for row in restored.status(0)["launches"])
    assert not apply_wire(restored, frames[0])
    frames[2]["sequence"] = 2
    assert apply_wire(restored, frames[2], now=10)
    assert restored.status(10)["launches"][1]["slot"] == 0

    frames[1].update(sequence=2, closed=True)
    assert apply_wire(restored, frames[1], now=11)
    final = restored.status(11)["launches"]
    assert [(row["launchId"], row["slot"]) for row in final] == [
        (frames[2]["launchId"], 0),
        (frames[3]["launchId"], 1),
        (frames[4]["launchId"], None),
    ]
    assert not apply_wire(restored, frames[1], now=12)


def test_fractional_lease_disconnect_and_reconnection_trace():
    """LEASE-1: exact deadlines expire, clocks cannot run backward, reconnect revives."""
    tracker = GjcTracker(1, lease_seconds=0.25)
    payload = wire_frame(states=("working",), sequence=1)
    assert apply_wire(tracker, payload, now=10.125)
    assert tracker.indicators(10.374999999)[0].connected
    assert not tracker.indicators(10.375)[0].connected
    assert not tracker.indicators(10.124999999)[0].connected

    tracker.disconnect(payload["producerId"], now=10.2)
    tracker.disconnect(payload["producerId"], now=10.3)
    assert tracker.indicators(10.2)[0].state == "unknown"
    payload.update(sequence=2)
    assert apply_wire(tracker, payload, now=20.5)
    assert tracker.indicators(20.5)[0].state == "working"


@pytest.mark.parametrize(
    "content",
    [
        b'{"version":1',
        b"not-json",
        b'{"version":1,"version":1}',
        b"\xff\xfe\x00\x00",
    ],
)
def test_partial_corrupt_and_duplicate_registry_input_is_rejected(tmp_path, content):
    """REG-1: corrupt registry input never becomes display state."""
    registry = tmp_path / "registry.json"
    registry.write_bytes(content)
    registry.chmod(0o600)
    with pytest.raises((ValueError, UnicodeError)):
        GjcTracker(1, registry)


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-32-le"])
def test_snapshot_bytes_require_utf8_json_lines_encoding(encoding):
    """WIRE-5: byte frames use strict UTF-8, never JSON's UTF-16/32 autodetection."""
    encoded = json.dumps(wire_frame()).encode(encoding)
    with pytest.raises(GjcProtocolError):
        parse_snapshot(encoded)


def test_snapshot_bytes_reject_utf8_bom():
    """WIRE-5: JSON Lines forbids a UTF-8 byte-order mark."""
    encoded = b"\xef\xbb\xbf" + json.dumps(wire_frame()).encode("utf-8")
    with pytest.raises(GjcProtocolError):
        parse_snapshot(encoded)


def test_registry_fifo_is_rejected_without_blocking_startup(tmp_path):
    """REG-2: a malicious special-file registry cannot hang process startup."""
    registry = tmp_path / "registry.fifo"
    os.mkfifo(registry, 0o600)
    script = """
import sys
sys.path.insert(0, sys.argv[1])
from orca_keychron_gjc.gjc_tracker import GjcTracker
try:
    GjcTracker(1, sys.argv[2])
except PermissionError:
    raise SystemExit(0)
raise SystemExit(9)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT / "src"), str(registry)],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
    )
    assert result.returncode == 0, result.stderr


def test_failed_registry_replace_leaves_no_partial_file_and_next_frame_recovers(
    tmp_path, monkeypatch
):
    """REG-3: pre-commit persistence failure is clean and a later frame can recover."""
    registry = tmp_path / "registry.json"
    tracker = GjcTracker(1, registry)
    real_replace = os.replace
    attempts = 0

    def fail_once(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("injected pre-commit failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_once)
    payload = wire_frame(sequence=1)
    with pytest.raises(OSError, match="injected pre-commit failure"):
        apply_wire(tracker, payload)
    assert not registry.exists()
    assert list(tmp_path.glob(".gjc-registry-*")) == []

    payload.update(sequence=2)
    assert apply_wire(tracker, payload)
    restored = GjcTracker(1, registry)
    assert restored.status(0)["launches"][0]["state"] == "unknown"


def test_semantic_mutation_guards_detect_wrong_priority_and_slot_reclaim(monkeypatch):
    """MUT-1: the suite kills representative priority and reclaim mutations."""
    waiting = parse_snapshot(
        wire_frame(states=("working", "waiting"), pending=((0, 0), (1, 0)))
    )
    original_aggregate = GjcTracker._aggregate
    monkeypatch.setattr(
        GjcTracker,
        "_aggregate",
        staticmethod(lambda snapshot: ("working", 2, 1)),
    )
    mutated_priority = GjcTracker(1)
    assert mutated_priority.apply(waiting, now=0)
    with pytest.raises(AssertionError):
        assert mutated_priority.indicators(0)[0].state == oracle_state(
            ("working", "waiting"), pending_requests=1
        )
    monkeypatch.setattr(GjcTracker, "_aggregate", staticmethod(original_aggregate))

    original_assign = GjcTracker._assign_overflow
    monkeypatch.setattr(GjcTracker, "_assign_overflow", lambda self: None)
    mutated_reclaim = GjcTracker(1)
    first, second = wire_frame(1), wire_frame(2)
    assert apply_wire(mutated_reclaim, first)
    assert apply_wire(mutated_reclaim, second)
    with pytest.raises(AssertionError):
        assert [item.slot for item in mutated_reclaim.indicators(0)] == [0]
    monkeypatch.setattr(GjcTracker, "_assign_overflow", original_assign)
