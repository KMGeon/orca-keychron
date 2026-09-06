"""Fast contract tests for the actual-runtime audit's independent oracle."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

AUDIT = Path(__file__).resolve().parents[2] / "experiments" / "gjc-e2e-audit"
sys.path.insert(0, str(AUDIT))

from audit_support import (
    AuditFailure,
    assert_decision_correlations,
    assert_distinct_stable_slots,
    assert_mass_waiting,
    assert_root_lifecycle,
    current_matching_frame,
    only_metadata_frame,
    remaining_child_decision,
)


def status(*slots: tuple[str, int]) -> dict:
    return {
        "status": {
            "launches": [
                {"launchId": launch, "slot": slot, "connected": True, "state": "done"}
                for launch, slot in slots
            ]
        }
    }


def frame(launch: str, root: str, sequence: int, closed: bool = False) -> dict:
    return {
        "receiverGeneration": 1,
        "producerId": "producer-a",
        "launchId": launch,
        "sequence": sequence,
        "pid": 123,
        "startedAt": 456,
        "complete": True,
        "closed": closed,
        "root": {
            "sessionId": root,
            "terminalHandle": "term-owned",
            "paneKey": "tab:leaf",
            "worktreeId": "repo::/worktree",
        },
        "sessions": [],
    }


def test_slots_require_independent_launches_and_survive_restart() -> None:
    assert assert_distinct_stable_slots(status(("a", 0), ("b", 1)), status(("a", 0), ("b", 1))) == {
        "a": 0,
        "b": 1,
    }
    with pytest.raises(AuditFailure, match="slots are not distinct"):
        assert_distinct_stable_slots(status(("a", 0), ("b", 0)), status(("a", 0), ("b", 0)))
    with pytest.raises(AuditFailure, match="slot identity changed"):
        assert_distinct_stable_slots(status(("a", 0), ("b", 1)), status(("a", 1), ("b", 0)))


def test_mass_oracle_checks_distribution_pending_count_and_renderer() -> None:
    sessions = [
        {
            "sessionId": f"working-{index}",
            "state": "working",
            "pendingAsks": 0,
            "pendingDecisions": 0,
        }
        for index in range(10)
    ] + [
        {"sessionId": "waiting", "state": "waiting", "pendingAsks": 0, "pendingDecisions": 1},
        {"sessionId": "done", "state": "done", "pendingAsks": 0, "pendingDecisions": 0},
    ]
    observed = {
        "producerId": "producer-a",
        "launchId": "mass",
        "sequence": 10,
        "sessions": sessions,
    }
    replay = {
        "source": "exact-snapshot-installed-product-replay",
        "snapshotIdentity": {
            "producerId": "producer-a",
            "launchId": "mass",
            "sequence": 10,
        },
        "accepted": True,
        "status": {
            "launches": [
                {
                    "producerId": "producer-a",
                    "launchId": "mass",
                    "sequence": 10,
                    "state": "waiting",
                    "agentCount": 12,
                    "pendingRequests": 1,
                    "connected": True,
                }
            ]
        },
        "colors": [
            {
                "producerId": "producer-a",
                "launchId": "mass",
                "sequence": 10,
                "isOrange": True,
            }
        ],
    }
    assert assert_mass_waiting(observed, replay)["pendingRequests"] == 1
    observed["sessions"][0]["state"] = "done"
    with pytest.raises(AuditFailure, match="10 working"):
        assert_mass_waiting(observed, replay)


def test_mass_oracle_rejects_later_orange_frame_with_different_count() -> None:
    sessions = [
        {
            "sessionId": f"working-{index}",
            "state": "working",
            "pendingAsks": 0,
            "pendingDecisions": 0,
        }
        for index in range(10)
    ] + [
        {"sessionId": "waiting", "state": "waiting", "pendingAsks": 1, "pendingDecisions": 0},
        {"sessionId": "done", "state": "done", "pendingAsks": 0, "pendingDecisions": 0},
    ]
    historical = {
        "producerId": "producer-a",
        "launchId": "mass",
        "sequence": 10,
        "sessions": sessions,
    }
    later_orange = {
        "source": "exact-snapshot-installed-product-replay",
        "snapshotIdentity": {
            "producerId": "producer-a",
            "launchId": "mass",
            "sequence": 11,
        },
        "accepted": True,
        "status": {
            "launches": [
                {
                    "producerId": "producer-a",
                    "launchId": "mass",
                    "sequence": 11,
                    "state": "waiting",
                    "agentCount": 1,
                    "pendingRequests": 1,
                    "connected": True,
                }
            ]
        },
        "colors": [
            {
                "producerId": "producer-a",
                "launchId": "mass",
                "sequence": 11,
                "isOrange": True,
            }
        ],
    }
    with pytest.raises(AuditFailure, match="exact mass snapshot"):
        assert_mass_waiting(historical, later_orange)


def test_decision_oracle_rejects_cross_answer_and_duplicate_resume() -> None:
    rows = []
    for request_id in ("req_1", "req_2"):
        rows.extend(
            [
                {
                    "event": "parent_child_resume_requested",
                    "request_id": request_id,
                    "actual_child_id_used": True,
                },
                {
                    "event": "child_answer_consumed",
                    "request_id": request_id,
                    "correlation_valid": True,
                    "answer_valid": True,
                    "checkpoint_valid": True,
                },
                {
                    "event": "parent_completion_checked",
                    "request_id": request_id,
                    "answer_consumed": True,
                },
            ]
        )
    result = assert_decision_correlations(rows, ["child-a", "child-b"])
    assert result["actualChildIds"] == ["child-a", "child-b"]
    rows.append(
        {"event": "parent_completion_checked", "request_id": "req_1", "answer_consumed": True}
    )
    assert_decision_correlations(rows, ["child-a", "child-b"])
    rows[4]["correlation_valid"] = False
    with pytest.raises(AuditFailure, match="cross-correlated"):
        assert_decision_correlations(rows, ["child-a", "child-b"])


def test_root_lifecycle_requires_new_resume_same_publisher_and_close() -> None:
    rows = [
        frame("launch", "old", 1),
        frame("launch", "new", 2),
        frame("launch", "old", 3),
        frame("launch", "old", 4, closed=True),
    ]
    assert assert_root_lifecycle(rows, "launch")["closed"] is True
    with pytest.raises(AuditFailure, match="resume"):
        assert_root_lifecycle(rows[:2] + [frame("launch", "new", 3, closed=True)], "launch")


def test_evidence_allowlist_drops_content_and_arbitrary_fields() -> None:
    observed = frame("launch", "root", 1)
    observed["prompt"] = "must not survive"
    observed["sessions"] = [
        {
            "sessionId": "root",
            "role": "root",
            "state": "working",
            "pendingAsks": 0,
            "pendingDecisions": 0,
            "question": "must not survive",
        }
    ]
    sanitized = only_metadata_frame(observed)
    assert "prompt" not in sanitized
    assert "question" not in sanitized["sessions"][0]


def test_current_frame_oracle_accepts_root_ask_but_rejects_cleared_child() -> None:
    pending = frame("launch", "root", 10)
    pending["sessions"] = [
        {
            "sessionId": "child-1",
            "role": "child",
            "state": "waiting",
            "pendingAsks": 0,
            "pendingDecisions": 1,
        },
        {
            "sessionId": "child-2",
            "role": "child",
            "state": "waiting",
            "pendingAsks": 0,
            "pendingDecisions": 1,
        },
    ]
    stable = frame("launch", "root", 11)
    stable["sessions"] = [
        {
            "sessionId": "child-2",
            "role": "child",
            "state": "waiting",
            "pendingAsks": 0,
            "pendingDecisions": 1,
        },
        {
            "sessionId": "root",
            "role": "root",
            "state": "waiting",
            "pendingAsks": 1,
            "pendingDecisions": 0,
        },
    ]
    cleared = frame("launch", "root", 12)
    cleared["sessions"] = [
        {
            "sessionId": "child-2",
            "role": "child",
            "state": "unknown",
            "pendingAsks": 0,
            "pendingDecisions": 0,
        }
    ]
    candidates = {"child-1", "child-2"}
    has_remaining = lambda value: remaining_child_decision(value, candidates) is not None
    assert remaining_child_decision(stable, candidates) == "child-2"
    assert (
        current_matching_frame(
            [pending, stable], "term-owned", "tab:leaf", has_remaining, min_sequence=10
        )
        == stable
    )
    assert (
        current_matching_frame(
            [pending, stable, cleared],
            "term-owned",
            "tab:leaf",
            has_remaining,
            min_sequence=10,
        )
        is None
    )


def test_tree_hash_ignores_generated_cache_but_tracks_source(tmp_path: Path) -> None:
    from run_audit import tree_hash

    source = tmp_path / "module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    before = tree_hash(tmp_path)
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "module.cpython-39.pyc").write_bytes(b"generated")
    assert tree_hash(tmp_path) == before
    source.write_text("VALUE = 2\n", encoding="utf-8")
    assert tree_hash(tmp_path) != before


def test_runtime_prepare_is_idempotent_after_minimal_env_creation(tmp_path: Path) -> None:
    from run_audit import minimal_environment, prepare_runtime

    runtime = tmp_path / "runtime"
    minimal_environment(runtime / "component-home")
    prepare_runtime(runtime)
    prepare_runtime(runtime)
    assert runtime.is_dir()
    assert (runtime / "component-home" / "tmp").is_dir()


def test_mass_transition_history_is_scoped_to_unique_terminal(tmp_path: Path) -> None:
    from run_audit import Audit

    audit = Audit(tmp_path / "runtime", tmp_path / "evidence.json", None)
    terminal = {"handle": "term-owned", "paneKey": "tab:leaf"}
    transition = frame("launch", "root", 10)
    transition["sessions"] = [{"state": "waiting"}]
    latest = frame("launch", "root", 11)
    latest["sessions"] = [{"state": "done"}]
    audit.frames = lambda: [
        {**transition, "root": {**transition["root"], "terminalHandle": "term-other"}},
        transition,
        latest,
    ]
    assert (
        audit.historical_terminal_frame(
            terminal, lambda value: value["sessions"][0]["state"] == "waiting", min_sequence=9
        )
        == transition
    )
