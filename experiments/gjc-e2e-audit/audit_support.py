"""Requirement-derived assertions for the bounded GJC 0.16.4 audit.

This module intentionally knows only metadata from the public bridge contract.  It
must never load prompt, question, answer, or tool-result text into audit evidence.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable


class AuditFailure(AssertionError):
    """Raised when an observed product outcome violates an audit requirement."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def wait_for(
    description: str,
    observe: Callable[[], Any],
    accept: Callable[[Any], bool],
    timeout: float,
) -> Any:
    """Poll a deterministic observable until a predicate holds or a deadline expires."""

    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = observe()
        if accept(last):
            return last
        time.sleep(0.05)
    raise AuditFailure(f"timed out after {timeout:.1f}s waiting for {description}; last={last!r}")


def only_metadata_frame(frame: dict[str, Any]) -> dict[str, Any]:
    """Return the strict bridge metadata allowlist used by the evidence file."""

    return {
        "receiverGeneration": frame.get("receiverGeneration"),
        "producerId": frame.get("producerId"),
        "launchId": frame.get("launchId"),
        "sequence": frame.get("sequence"),
        "pid": frame.get("pid"),
        "startedAt": frame.get("startedAt"),
        "complete": frame.get("complete"),
        "closed": frame.get("closed"),
        "root": {
            key: frame.get("root", {}).get(key)
            for key in ("sessionId", "terminalHandle", "paneKey", "worktreeId")
        },
        "sessions": [
            {
                key: row.get(key)
                for key in ("sessionId", "role", "state", "pendingAsks", "pendingDecisions")
            }
            for row in frame.get("sessions", [])
        ],
    }


def current_matching_frame(
    frames: Iterable[dict[str, Any]],
    terminal_handle: str,
    pane_key: str,
    predicate: Callable[[dict[str, Any]], bool],
    min_sequence: int = -1,
) -> Any:
    """Test only the newest post-fence frame, never stale matching history."""

    relevant = [
        frame
        for frame in frames
        if frame.get("root", {}).get("terminalHandle") == terminal_handle
        and frame.get("root", {}).get("paneKey") == pane_key
        and int(frame.get("sequence", -1)) > min_sequence
    ]
    if not relevant:
        return None
    current = relevant[-1]
    return current if predicate(current) else None


def remaining_child_decision(frame: dict[str, Any], candidate_child_ids: Iterable[str]) -> Any:
    """Return the one surviving candidate child decision; root ask count is independent."""

    candidates = set(candidate_child_ids)
    matches = [
        row.get("sessionId")
        for row in frame.get("sessions", [])
        if row.get("role") == "child"
        and row.get("state") == "waiting"
        and int(row.get("pendingDecisions", 0)) == 1
        and row.get("sessionId") in candidates
    ]
    return matches[0] if len(matches) == 1 else None


def assert_distinct_stable_slots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    before_slots = {
        row["launchId"]: row["slot"]
        for row in before["status"]["launches"]
        if row.get("slot") is not None
    }
    after_slots = {
        row["launchId"]: row["slot"]
        for row in after["status"]["launches"]
        if row.get("slot") is not None
    }
    if len(before_slots) < 2:
        raise AuditFailure(f"REQ-LIFE-1 expected two assigned launches, got {before_slots}")
    if len(set(before_slots.values())) != len(before_slots):
        raise AuditFailure(f"REQ-LIFE-1 slots are not distinct: {before_slots}")
    if any(after_slots.get(launch) != slot for launch, slot in before_slots.items()):
        raise AuditFailure(
            f"REQ-LIFE-2 slot identity changed across receiver restart: {before_slots} -> {after_slots}"
        )
    return before_slots


def assert_mass_waiting(frame: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    sessions = frame.get("sessions", [])
    counts = {
        state: sum(row.get("state") == state for row in sessions)
        for state in ("working", "waiting", "done")
    }
    pending = sum(
        int(row.get("pendingAsks", 0)) + int(row.get("pendingDecisions", 0)) for row in sessions
    )
    if len(sessions) != 12 or counts != {"working": 10, "waiting": 1, "done": 1}:
        raise AuditFailure(
            "REQ-STATE-1 expected 12 sessions (10 working, 1 waiting, 1 done); "
            f"got total={len(sessions)} counts={counts}"
        )
    if pending != 1:
        raise AuditFailure(f"REQ-STATE-1 expected one pending decision, got {pending}")
    launch_id = frame["launchId"]
    expected_identity = {
        "producerId": frame.get("producerId"),
        "launchId": launch_id,
        "sequence": frame.get("sequence"),
    }
    if (
        replay.get("source") != "exact-snapshot-installed-product-replay"
        or replay.get("accepted") is not True
        or replay.get("snapshotIdentity") != expected_identity
    ):
        raise AuditFailure(
            "REQ-STATE-2 renderer evidence is not tied to the exact mass snapshot; "
            f"expected={expected_identity} got={replay.get('snapshotIdentity')}"
        )
    status_rows = replay.get("status", {}).get("launches", [])
    status_row = next(
        (
            row
            for row in status_rows
            if row.get("launchId") == launch_id
            and row.get("producerId") == frame.get("producerId")
            and row.get("sequence") == frame.get("sequence")
        ),
        None,
    )
    if not status_row or any(
        (
            status_row.get("state") != "waiting",
            status_row.get("agentCount") != len(sessions),
            status_row.get("pendingRequests") != pending,
            status_row.get("connected") is not True,
        )
    ):
        raise AuditFailure(
            "REQ-STATE-2 exact mass snapshot did not aggregate to waiting/12/1/connected; "
            f"status={status_row}"
        )
    rendered = next(
        (
            row
            for row in replay.get("colors", [])
            if row.get("launchId") == launch_id
            and row.get("producerId") == frame.get("producerId")
            and row.get("sequence") == frame.get("sequence")
        ),
        None,
    )
    if not rendered or rendered.get("isOrange") is not True:
        raise AuditFailure(f"REQ-STATE-2 waiting launch was not orange: {rendered}")
    return {
        "launchId": launch_id,
        "sequence": frame.get("sequence"),
        "sessionCounts": counts,
        "pendingRequests": pending,
        "rendererEvidence": replay["source"],
    }


def assert_decision_correlations(
    provider_rows: Iterable[dict[str, Any]], actual_child_ids: Iterable[str]
) -> dict[str, Any]:
    rows = list(provider_rows)
    request_ids = ("req_1", "req_2")
    resumes = [row for row in rows if row.get("event") == "parent_child_resume_requested"]
    consumed = [row for row in rows if row.get("event") == "child_answer_consumed"]
    completed = [row for row in rows if row.get("event") == "parent_completion_checked"]
    for request_id in request_ids:
        own_resumes = [row for row in resumes if row.get("request_id") == request_id]
        own_consumed = [row for row in consumed if row.get("request_id") == request_id]
        own_completed = [row for row in completed if row.get("request_id") == request_id]
        if len(own_resumes) != 1 or own_resumes[0].get("actual_child_id_used") is not True:
            raise AuditFailure(
                f"REQ-DECISION-1 missing unique actual-child resume for {request_id}"
            )
        if len(own_consumed) != 1 or not all(
            own_consumed[0].get(key) is True
            for key in ("correlation_valid", "answer_valid", "checkpoint_valid")
        ):
            raise AuditFailure(f"REQ-DECISION-1 invalid/cross-correlated answer for {request_id}")
        if not own_completed or not any(
            row.get("answer_consumed") is True for row in own_completed
        ):
            raise AuditFailure(f"REQ-DECISION-2 parent did not verify completion for {request_id}")
    child_ids = sorted(set(actual_child_ids))
    if len(child_ids) != 2:
        raise AuditFailure(f"REQ-DECISION-1 expected two actual child IDs, got {child_ids}")
    return {"requestIds": list(request_ids), "actualChildIds": child_ids}


def assert_outcomes(frames: Iterable[dict[str, Any]], launches: dict[str, str]) -> dict[str, str]:
    rows = list(frames)
    observed = {}
    for case, launch_id in launches.items():
        states = {
            session.get("state")
            for frame in rows
            if frame.get("launchId") == launch_id
            for session in frame.get("sessions", [])
            if session.get("role") == "root"
        }
        expected = {"success": "done", "failed": "failed", "cancel": "cancelled"}[case]
        if expected not in states:
            raise AuditFailure(f"REQ-STATE-3 {case} missing {expected}; observed={sorted(states)}")
        observed[case] = expected
    return observed


def assert_root_lifecycle(frames: Iterable[dict[str, Any]], launch_id: str) -> dict[str, Any]:
    rows = [row for row in frames if row.get("launchId") == launch_id]
    roots = [row.get("root", {}).get("sessionId") for row in rows if not row.get("closed")]
    roots = [root for root in roots if root]
    unique_roots = list(dict.fromkeys(roots))
    identities = {(row.get("producerId"), row.get("pid"), row.get("startedAt")) for row in rows}
    if len(unique_roots) < 2:
        raise AuditFailure(f"REQ-LIFE-4 /new did not produce a second root: {unique_roots}")
    first_new = next(index for index, root in enumerate(roots) if root != roots[0])
    if roots[0] not in roots[first_new + 1 :]:
        raise AuditFailure(f"REQ-LIFE-4 /resume did not return to original root: {roots}")
    if len(identities) != 1:
        raise AuditFailure(f"REQ-LIFE-4 publisher identity changed: {identities}")
    if not any(row.get("closed") is True for row in rows):
        raise AuditFailure("REQ-LIFE-4 /exit emitted no closed snapshot")
    return {"rootSessionIds": unique_roots, "publisherIdentityStable": True, "closed": True}
