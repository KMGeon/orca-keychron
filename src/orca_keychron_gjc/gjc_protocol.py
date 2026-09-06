"""Strict, content-free GJC snapshot wire protocol (version 1)."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

MAX_FRAME_BYTES = 512 * 1024
MAX_SESSIONS = 256
MAX_REQUESTS = 128
MAX_SAFE_INTEGER = 2**53 - 1
STATES = frozenset(
    {"idle", "working", "waiting", "done", "failed", "paused", "cancelled", "unknown", "closed"}
)


class GjcProtocolError(ValueError):
    """A frame does not satisfy the supported protocol."""


@dataclass(frozen=True)
class GjcRoot:
    session_id: str
    terminal_handle: str
    pane_key: str
    worktree_id: str


@dataclass(frozen=True)
class GjcSession:
    session_id: str
    role: str
    state: str
    pending_asks: int
    pending_decisions: int


@dataclass(frozen=True)
class GjcSnapshot:
    producer_id: str
    sequence: int
    launch_id: str
    pid: int
    started_at: int
    complete: bool
    closed: bool
    root: GjcRoot
    sessions: tuple[GjcSession, ...]
    version: int = 1


def _object(value: Any, keys: set[str], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise GjcProtocolError(f"Invalid {name} fields")
    return value


def _identifier(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise GjcProtocolError(f"Invalid {name}")
    return value


def _uuid(value: Any, name: str) -> str:
    text = _identifier(value, name)
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise GjcProtocolError(f"Invalid {name}") from exc
    if str(parsed) != text:
        raise GjcProtocolError(f"Noncanonical {name}")
    return text


def _integer(value: Any, name: str, minimum: int = 0, maximum: int = MAX_SAFE_INTEGER) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise GjcProtocolError(f"Invalid {name}")
    return value


def _boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise GjcProtocolError(f"Invalid {name}")
    return value


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GjcProtocolError("Duplicate JSON field")
        result[key] = value
    return result


def parse_snapshot(payload: Any) -> GjcSnapshot:
    """Validate a JSON frame or mapping without retaining unrecognized content."""
    if isinstance(payload, (str, bytes, bytearray)):
        try:
            if isinstance(payload, str):
                size = len(payload.encode("utf-8"))
            else:
                size = len(payload)
            if size > MAX_FRAME_BYTES:
                raise GjcProtocolError("Snapshot exceeds frame limit")
            if not isinstance(payload, str):
                # json.loads(bytes) autodetects UTF-16/32 and accepts a BOM.
                # JSON Lines frames are strictly UTF-8 and must not contain a
                # BOM, so decode here before handing text to the JSON parser.
                payload = bytes(payload).decode("utf-8")
            payload = json.loads(payload, object_pairs_hook=_unique_json_object)
        except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise GjcProtocolError("Invalid snapshot JSON") from exc
    row = _object(
        payload,
        {"version", "type", "producerId", "sequence", "launchId", "pid", "startedAt",
         "complete", "closed", "root", "sessions"},
        "snapshot",
    )
    if type(row["version"]) is not int or row["version"] != 1 or row["type"] != "snapshot":
        raise GjcProtocolError("Unsupported snapshot protocol")
    root_row = _object(
        row["root"], {"sessionId", "terminalHandle", "paneKey", "worktreeId"}, "root"
    )
    root = GjcRoot(*(_identifier(root_row[key], key) for key in (
        "sessionId", "terminalHandle", "paneKey", "worktreeId"
    )))
    closed = _boolean(row["closed"], "closed")
    rows = row["sessions"]
    if not isinstance(rows, list) or len(rows) > MAX_SESSIONS:
        raise GjcProtocolError("Invalid sessions list")
    sessions = []
    seen = set()
    roots = []
    for raw in rows:
        session_row = _object(
            raw, {"sessionId", "role", "state", "pendingAsks", "pendingDecisions"}, "session"
        )
        session_id = _identifier(session_row["sessionId"], "sessionId")
        role = session_row["role"]
        state = session_row["state"]
        if role not in ("root", "child") or not isinstance(state, str) or state not in STATES:
            raise GjcProtocolError("Invalid session role or state")
        if session_id in seen:
            raise GjcProtocolError("Duplicate session identity")
        seen.add(session_id)
        if role == "root":
            roots.append(session_id)
        sessions.append(GjcSession(
            session_id, role, state,
            _integer(session_row["pendingAsks"], "pendingAsks", maximum=MAX_REQUESTS),
            _integer(session_row["pendingDecisions"], "pendingDecisions", maximum=MAX_REQUESTS),
        ))
    if roots != [root.session_id] and not (closed and not sessions):
        raise GjcProtocolError("Snapshot must contain exactly its declared root")
    return GjcSnapshot(
        producer_id=_uuid(row["producerId"], "producerId"),
        sequence=_integer(row["sequence"], "sequence", minimum=1),
        launch_id=_uuid(row["launchId"], "launchId"),
        pid=_integer(row["pid"], "pid", minimum=1),
        started_at=_integer(row["startedAt"], "startedAt", minimum=1),
        complete=_boolean(row["complete"], "complete"),
        closed=closed, root=root, sessions=tuple(sessions),
    )


def valid_clock(value: float) -> float:
    """Reject bad injected clocks before they can make a lease immortal."""
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError("Clock must be finite")
    return float(value)
