import copy
import json
from uuid import uuid4

import pytest

from orca_keychron_gjc.gjc_protocol import GjcProtocolError, parse_snapshot


def frame(state="working", sequence=1):
    return {
        "version": 1, "type": "snapshot", "producerId": str(uuid4()), "sequence": sequence,
        "launchId": str(uuid4()), "pid": 123, "startedAt": 123456, "complete": True,
        "closed": False,
        "root": {"sessionId": "shared-root", "terminalHandle": "term_test",
                 "paneKey": "tab:leaf", "worktreeId": "worktree"},
        "sessions": [{"sessionId": "shared-root", "role": "root", "state": state,
                      "pendingAsks": 0, "pendingDecisions": 0}],
    }


def test_immutable_full_snapshot():
    payload = frame()
    snapshot = parse_snapshot(json.dumps(payload).encode())
    payload["sessions"][0]["state"] = "done"
    assert snapshot.sessions[0].state == "working"
    with pytest.raises(AttributeError):
        snapshot.sequence = 2


@pytest.mark.parametrize("key,value", [
    ("version", True), ("version", 2), ("sequence", 0), ("sequence", True),
    ("sequence", 2**53), ("producerId", "not-a-uuid"), ("pid", 0),
    ("complete", 1), ("closed", "false"), ("startedAt", float("nan")),
    ("sessions", []), ("sessions", {}),
])
def test_invalid_top_level(key, value):
    payload = frame()
    payload[key] = value
    with pytest.raises(GjcProtocolError):
        parse_snapshot(payload)


@pytest.mark.parametrize("key,value", [
    ("state", "success"), ("state", []), ("role", "grandchild"),
    ("pendingAsks", -1), ("pendingDecisions", 129), ("pendingAsks", True),
    ("sessionId", "wrong-root"), ("sessionId", "x" * 513),
])
def test_invalid_session(key, value):
    payload = frame()
    payload["sessions"][0][key] = value
    with pytest.raises(GjcProtocolError):
        parse_snapshot(payload)


def test_no_content_extensions_duplicate_keys_or_sessions():
    payload = frame()
    payload["prompt"] = "private"
    with pytest.raises(GjcProtocolError):
        parse_snapshot(payload)
    payload.pop("prompt")
    with pytest.raises(GjcProtocolError):
        parse_snapshot(json.dumps(payload).replace('"version": 1', '"version": 1,"version": 1'))
    payload["sessions"].append(copy.deepcopy(payload["sessions"][0]))
    with pytest.raises(GjcProtocolError):
        parse_snapshot(payload)


def test_frame_and_session_bounds():
    with pytest.raises(GjcProtocolError):
        parse_snapshot(b" " * (512 * 1024 + 1))
    payload = frame()
    payload["sessions"] += [dict(payload["sessions"][0], role="child", sessionId=str(i))
                            for i in range(256)]
    with pytest.raises(GjcProtocolError):
        parse_snapshot(payload)
    payload["sessions"].pop()
    assert len(parse_snapshot(payload).sessions) == 256


def test_explicit_closed_empty_snapshot():
    payload = frame()
    payload.update(closed=True, sessions=[])
    assert parse_snapshot(payload).closed
