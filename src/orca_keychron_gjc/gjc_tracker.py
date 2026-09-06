"""Thread-safe complete-snapshot aggregation and stable GJC key assignments."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from .gjc_protocol import (
    GjcRoot,
    GjcSnapshot,
    _unique_json_object,
    parse_snapshot,
    valid_clock,
)

MAX_LAUNCHES = 1024
MAX_IDENTITIES = 65536
MAX_REGISTRY_BYTES = 32 * 1024 * 1024
DISPLAY_STATES = frozenset({"waiting", "failed", "working", "unknown", "done", "idle"})


@dataclass(frozen=True)
class GjcIndicator:
    launch_id: str
    state: str
    slot: int
    target_pane_keys: tuple[str, ...]
    agent_count: int
    pending_requests: int
    connected: bool

    @property
    def identity_label(self) -> str:
        return self.launch_id


@dataclass
class _Launch:
    launch_id: str
    producer_id: str
    sequence: int
    root: GjcRoot
    pid: int
    started_at: int
    complete: bool
    state: str
    agent_count: int
    pending_requests: int
    slot: int | None
    received_at: float | None = None
    online: bool = False


def ensure_private_directory(path: Path) -> None:
    """Create a private owned directory; never chmod an unrelated existing one."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise PermissionError(f"A private user-owned directory is required: {path}")


def _root_dict(root: GjcRoot) -> dict[str, str]:
    return {"sessionId": root.session_id, "terminalHandle": root.terminal_handle,
            "paneKey": root.pane_key, "worktreeId": root.worktree_id}


class GjcTracker:
    def __init__(
        self, max_slots: int, registry_path: str | Path | None = None, lease_seconds: float = 8
    ) -> None:
        if type(max_slots) is not int or not 1 <= max_slots <= MAX_LAUNCHES:
            raise ValueError("max_slots must be between 1 and 1024")
        if valid_clock(lease_seconds) <= 0:
            raise ValueError("lease_seconds must be positive")
        self.max_slots = max_slots
        self.lease_seconds = float(lease_seconds)
        self.registry_path = Path(registry_path) if registry_path is not None else None
        self._lock = threading.RLock()
        self._launches: dict[str, _Launch] = {}
        # Explicitly retired identities cannot resurrect from queued old frames.
        self._retired: dict[str, str] = {}
        if self.registry_path is not None:
            ensure_private_directory(self.registry_path.parent)
            self._restore()

    def apply(self, snapshot: GjcSnapshot, now: float | None = None) -> bool:
        if not isinstance(snapshot, GjcSnapshot):
            raise TypeError("apply requires a validated GjcSnapshot")
        clock = valid_clock(time.monotonic() if now is None else now)
        with self._lock:
            launch = self._launches.get(snapshot.launch_id)
            if snapshot.launch_id in self._retired:
                return False
            if launch is not None:
                if (
                    launch.producer_id != snapshot.producer_id
                    or snapshot.sequence <= launch.sequence
                    or launch.pid != snapshot.pid
                    or launch.started_at != snapshot.started_at
                    or launch.root.terminal_handle != snapshot.root.terminal_handle
                    or launch.root.pane_key != snapshot.root.pane_key
                    or launch.root.worktree_id != snapshot.root.worktree_id
                ):
                    return False
            else:
                if (
                    len(self._launches) >= MAX_LAUNCHES
                    or len(self._launches) + len(self._retired) >= MAX_IDENTITIES
                    or snapshot.producer_id in self._retired.values()
                    or any(r.producer_id == snapshot.producer_id for r in self._launches.values())
                ):
                    return False
            if snapshot.closed:
                self._retired[snapshot.launch_id] = snapshot.producer_id
                self._launches.pop(snapshot.launch_id, None)
                self._assign_overflow()
                self._persist()
                return True
            state, count, pending = self._aggregate(snapshot)
            self._launches[snapshot.launch_id] = _Launch(
                snapshot.launch_id, snapshot.producer_id, snapshot.sequence, snapshot.root,
                snapshot.pid, snapshot.started_at, snapshot.complete, state, count, pending,
                launch.slot if launch else None, clock, True,
            )
            self._assign_overflow()
            self._persist()
            return True

    def disconnect(self, producer_id: str, now: float | None = None) -> None:
        if now is not None:
            valid_clock(now)
        with self._lock:
            changed = False
            for launch in self._launches.values():
                if launch.producer_id == producer_id and launch.online:
                    launch.online = False
                    changed = True
            if changed:
                self._persist()

    def clear(self, launch_id: str) -> bool:
        with self._lock:
            launch = self._launches.pop(launch_id, None)
            if launch is None:
                return False
            self._retired[launch_id] = launch.producer_id
            self._assign_overflow()
            self._persist()
            return True

    def indicators(self, now: float | None = None) -> list[GjcIndicator]:
        clock = valid_clock(time.monotonic() if now is None else now)
        with self._lock:
            indicators = []
            for launch in self._launches.values():
                if launch.slot is None:
                    continue
                connected = self._connected(launch, clock)
                indicators.append(GjcIndicator(
                    launch.launch_id, launch.state if connected else "unknown", launch.slot,
                    (launch.root.pane_key,), launch.agent_count, launch.pending_requests, connected,
                ))
            return sorted(indicators, key=lambda item: item.slot)

    def status(self, now: float | None = None) -> dict[str, Any]:
        clock = valid_clock(time.monotonic() if now is None else now)
        with self._lock:
            rows = [self._display_row(launch, clock) for launch in self._launches.values()]
            return {"version": 1, "maxSlots": self.max_slots, "launches": rows,
                    "overflow": [row for row in rows if row["slot"] is None]}

    def _connected(self, launch: _Launch, now: float) -> bool:
        return bool(
            launch.online and launch.received_at is not None
            and launch.received_at <= now < launch.received_at + self.lease_seconds
        )

    @staticmethod
    def _aggregate(snapshot: GjcSnapshot) -> tuple[str, int, int]:
        rows = [row for row in snapshot.sessions if row.state != "closed"]
        states = {row.state for row in rows}
        pending = sum(row.pending_asks + row.pending_decisions for row in snapshot.sessions)
        if pending or "waiting" in states:
            state = "waiting"
        elif "failed" in states:
            state = "failed"
        elif "working" in states:
            state = "working"
        elif not snapshot.complete or states & {"unknown", "paused", "cancelled"}:
            state = "unknown"
        elif "done" in states:
            state = "done"
        elif states == {"idle"}:
            state = "idle"
        else:
            state = "unknown"
        return state, len(rows), pending

    def _assign_overflow(self) -> None:
        used = {row.slot for row in self._launches.values() if row.slot is not None}
        available = iter(slot for slot in range(self.max_slots) if slot not in used)
        for launch in self._launches.values():
            if launch.slot is None:
                launch.slot = next(available, None)

    def _display_row(self, launch: _Launch, now: float) -> dict[str, Any]:
        connected = self._connected(launch, now)
        return {
            "launchId": launch.launch_id, "producerId": launch.producer_id,
            "sequence": launch.sequence, "slot": launch.slot,
            "state": launch.state if connected else "unknown", "connected": connected,
            "agentCount": launch.agent_count, "pendingRequests": launch.pending_requests,
            "targetPaneKeys": [launch.root.pane_key], "root": _root_dict(launch.root),
            "complete": launch.complete, "pid": launch.pid, "startedAt": launch.started_at,
        }

    def _persist(self) -> None:
        if self.registry_path is None:
            return
        path = self.registry_path
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise PermissionError("Refusing to replace an unowned registry")
        rows = []
        for launch in self._launches.values():
            row = self._display_row(launch, time.monotonic())
            # Persist identities and display data only; saved state is always offline.
            row["connected"] = False
            row["state"] = "unknown"
            rows.append(row)
        payload = {"version": 1, "maxSlots": self.max_slots, "launches": rows,
                   "retired": [[launch, producer] for launch, producer in self._retired.items()]}
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_REGISTRY_BYTES:
            raise ValueError("Registry exceeds its bounded storage limit")
        fd, temporary = tempfile.mkstemp(prefix=".gjc-registry-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _restore(self) -> None:
        path = self.registry_path
        assert path is not None
        try:
            # Reject special files after a nonblocking open.  Without
            # O_NONBLOCK, a user-replaced FIFO can hang startup before fstat has
            # a chance to enforce the regular-file registry contract.
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > MAX_REGISTRY_BYTES
            ):
                raise PermissionError("Registry must be a bounded private user-owned file")
            payload = json.load(stream, object_pairs_hook=_unique_json_object)
        try:
            self._restore_payload(payload)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("Invalid GJC slot registry; preserve it and clear explicitly") from exc

    def _restore_payload(self, payload: Any) -> None:
        if not isinstance(payload, dict) or set(payload) != {"version", "maxSlots", "launches", "retired"}:
            raise ValueError("Invalid registry fields")
        if type(payload["version"]) is not int or payload["version"] != 1:
            raise ValueError("Invalid registry version")
        if (type(payload["maxSlots"]) is not int
                or not 1 <= payload["maxSlots"] <= MAX_LAUNCHES):
            raise ValueError("Invalid registry maxSlots")
        rows, retired = payload["launches"], payload["retired"]
        if (
            not isinstance(rows, list) or len(rows) > MAX_LAUNCHES
            or not isinstance(retired, list) or len(rows) + len(retired) > MAX_IDENTITIES
        ):
            raise ValueError("Invalid registry size")
        producers = set()
        for pair in retired:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("Invalid retired identity")
            launch, producer = pair
            if (not isinstance(launch, str) or not isinstance(producer, str)
                    or str(UUID(launch)) != launch or str(UUID(producer)) != producer):
                raise ValueError("Invalid retired UUID")
            if launch in self._retired or producer in producers:
                raise ValueError("Duplicate retired identity")
            self._retired[launch] = producer
            producers.add(producer)
        occupied = set()
        expected = {"launchId", "producerId", "sequence", "slot", "state", "connected",
                    "agentCount", "pendingRequests", "targetPaneKeys", "root", "complete",
                    "pid", "startedAt"}
        for row in rows:
            if not isinstance(row, dict) or set(row) != expected:
                raise ValueError("Invalid registry display fields")
            root = row["root"]
            snapshot = parse_snapshot({
                "version": 1, "type": "snapshot", "producerId": row["producerId"],
                "launchId": row["launchId"], "sequence": row["sequence"], "pid": row["pid"],
                "startedAt": row["startedAt"], "complete": row["complete"], "closed": False,
                "root": root, "sessions": [{"sessionId": root["sessionId"], "role": "root",
                    "state": "unknown", "pendingAsks": 0, "pendingDecisions": 0}],
            })
            slot = row["slot"]
            if slot is not None and (type(slot) is not int or not 0 <= slot < payload["maxSlots"]):
                raise ValueError("Invalid registry slot")
            if slot is not None and slot in occupied:
                raise ValueError("Duplicate registry slot")
            if slot is not None:
                occupied.add(slot)
                if slot >= self.max_slots:
                    slot = None
            if (
                snapshot.launch_id in self._retired or snapshot.launch_id in self._launches
                or snapshot.producer_id in producers
                or not isinstance(row["state"], str) or row["state"] not in DISPLAY_STATES
                or type(row["connected"]) is not bool
                or type(row["agentCount"]) is not int or not 0 <= row["agentCount"] <= 256
                or type(row["pendingRequests"]) is not int
                or not 0 <= row["pendingRequests"] <= 256 * 256
                or row["targetPaneKeys"] != [snapshot.root.pane_key]
            ):
                raise ValueError("Invalid registry display data")
            producers.add(snapshot.producer_id)
            self._launches[snapshot.launch_id] = _Launch(
                snapshot.launch_id, snapshot.producer_id, snapshot.sequence, snapshot.root,
                snapshot.pid, snapshot.started_at, snapshot.complete, "unknown", row["agentCount"],
                row["pendingRequests"], slot,
            )
        self._assign_overflow()
