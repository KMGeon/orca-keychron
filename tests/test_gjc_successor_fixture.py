from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HARNESS_PATH = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "gjc-successor-audit"
    / "harness.py"
)
SPEC = importlib.util.spec_from_file_location("gjc_successor_fixture", HARNESS_PATH)
assert SPEC is not None and SPEC.loader is not None
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


def fixture_data() -> dict:
    return {
        "requestId": "req_restart",
        "question": "Continue the restart-safe synthetic operation?",
        "options": ["Continue with A", "Continue with B"],
        "checkpoint": "checkpoint-restart-v1",
        "actualAnswer": "Continue with A",
        "predecessorChildId": "0-predecessor",
    }


def assistant_call(call_id: str, name: str, arguments: dict) -> dict:
    return {
        "role": "assistant",
        "tool_calls": [{
            "id": call_id,
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }],
    }


def tool_result(call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def task_receipt(child_id: str) -> str:
    return f"- `{child_id}` (job `job_fixture`)\n"


def test_launch_a_asks_only_after_actual_child_and_exact_pending_envelope() -> None:
    fixture = fixture_data()
    fixture.pop("predecessorChildId")
    events = []
    body = {"messages": [{"role": "user", "content": "[SUCCESSOR_ROOT:A]"}]}

    actions, _ = harness.launch_a_plan(body, fixture, events.append)
    assert actions[0][0] == "task"
    body["messages"] += [
        assistant_call("task-1", "task", {"agent": "restart-child"}),
        tool_result("task-1", task_receipt("actual-child-a")),
        assistant_call("await-1", "subagent", {"action": "await", "ids": ["actual-child-a"]}),
        tool_result("await-1", "completed"),
        assistant_call("read-1", "read", {"path": "agent://actual-child-a"}),
        tool_result("read-1", json.dumps(harness.pending_envelope(fixture))),
    ]

    actions, _ = harness.launch_a_plan(body, fixture, events.append)

    assert actions == [("ask", {"questions": [{
        "id": fixture["requestId"],
        "question": fixture["question"],
        "options": [{"label": value} for value in fixture["options"]],
        "multi": False,
    }]})]
    assert events[-1]["actualChildId"] == "actual-child-a"


def test_launch_b_requires_failed_predecessor_resume_before_new_child() -> None:
    fixture = fixture_data()
    events = []
    body = {"messages": [{"role": "user", "content": "[SUCCESSOR_ROOT:B]"}]}

    actions, _ = harness.launch_b_plan(body, fixture, events.append)
    assert actions[0][0] == "subagent"
    body["messages"] += [
        assistant_call("resume-old", "subagent", actions[0][1]),
        tool_result("resume-old", "### 0-predecessor — not_found"),
    ]

    actions, _ = harness.launch_b_plan(body, fixture, events.append)

    assert actions[0][0] == "task"
    assert actions[0][1]["tasks"][0]["id"] == "successor"
    assert events[-1]["event"] == "old_resume_rejected"


def test_launch_b_rejects_successor_identity_collision() -> None:
    fixture = fixture_data()
    events = []
    body = {"messages": [{"role": "user", "content": "[SUCCESSOR_ROOT:B]"}]}
    resume = {
        "action": "resume", "id": "0-predecessor",
        "message": harness.resume_message(fixture, "restart-successor-probe"),
    }
    body["messages"] += [
        assistant_call("resume-old", "subagent", resume),
        tool_result("resume-old", "### 0-predecessor — not_found"),
        assistant_call("task-new", "task", {"agent": "restart-child"}),
        tool_result("task-new", task_receipt("0-predecessor")),
    ]

    actions, message = harness.launch_b_plan(body, fixture, events.append)

    assert actions == []
    assert "SUCCESSOR_ID_COLLISION" in message


def test_actual_gjc_not_found_receipt_requires_successor_path() -> None:
    receipt = (
        "## Subagent resume (1)\n\n"
        "### 0-predecessor — not_found\n"
        "Guidance: No visible detached subagent matches this id."
    )

    assert harness.old_resume_failed(receipt)


def test_successor_rejects_wrong_checkpoint_even_with_known_answer() -> None:
    fixture = fixture_data()
    payload = harness.successor_payload(fixture)
    payload["checkpoint"] = "wrong-checkpoint"
    body = {"messages": [{
        "role": "user",
        "content": "[SUCCESSOR_CHILD] " + json.dumps(payload),
    }]}
    events = []

    actions, _ = harness.successor_child_plan(body, fixture, events.append)

    result = actions[0][1]["result"]["data"]
    assert result == {
        "status": "correlation_error",
        "request_id": "req_restart",
        "answer_consumed": False,
        "outcome": "rejected",
    }
    assert events[-1]["checkpointValid"] is False
    assert events[-1]["answerValid"] is True


def test_successor_accepts_only_all_correlated_fields() -> None:
    fixture = fixture_data()
    body = {"messages": [{
        "role": "user",
        "content": "[SUCCESSOR_CHILD] " + json.dumps(harness.successor_payload(fixture)),
    }]}
    events = []

    actions, _ = harness.successor_child_plan(body, fixture, events.append)

    assert actions[0][1]["result"]["data"] == {
        "status": "completed",
        "request_id": "req_restart",
        "answer_consumed": True,
        "outcome": "successor",
    }


def test_answered_status_cannot_satisfy_pre_answer_lifecycle() -> None:
    waiting = {"state": "waiting", "pendingRequests": 2, "connected": True}
    answered = {"state": "done", "pendingRequests": 0, "connected": True}

    harness.assert_waiting_before_answer(waiting)
    harness.assert_answer_resolved(answered)
    try:
        harness.assert_waiting_before_answer(answered)
    except AssertionError as error:
        assert "waiting" in str(error)
    else:
        raise AssertionError("answered state must not satisfy the pre-answer requirement")
