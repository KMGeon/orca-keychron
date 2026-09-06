"""Regression guards for false-positive documentation/test traceability gates."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "requirement_gate", Path(__file__).resolve().parents[1] / "scripts" / "requirements.py"
)
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


@pytest.fixture
def registry(tmp_path):
    product = tmp_path / "docs/product"
    product.mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_behavior.py").write_text("def test_waiting():\n    pass\n")
    (tmp_path / "docs/baseline.md").write_text("Historical audit, not current proof.\n")
    reqs = [
        {
            "id": f"R{i:02}",
            "kinds": ["functional"],
            "area": "상태",
            "title": "사람 호출",
            "statement": "사람 호출이 우선한다.",
            "acceptance": ["대기 1개가 작업 10개보다 우선한다."],
            "implementation": [],
            "limitations": [],
            "verification": [
                {
                    "kind": "pytest",
                    "target": "tests/test_behavior.py",
                    "selector": "test_waiting",
                    "layer": "unit",
                    "note": "모의 이벤트",
                }
            ],
        }
        for i in range(1, 46)
    ]
    decisions = [
        {
            "id": "D01",
            "title": "사람 호출 우선",
            "status": "accepted",
            "origin": "user",
            "decision": "다수결을 사용하지 않는다.",
            "rationale": ["한 명의 질문도 조치가 필요하다."],
            "alternatives": ["다수결 제외"],
            "consequences": ["주황색을 우선한다."],
            "requirement_ids": [r["id"] for r in reqs],
            "references": ["docs/baseline.md"],
        }
    ]

    def save():
        (product / "requirements.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "requirements": reqs,
                    "baseline": {"report": "docs/baseline.md", "note": "과거 검증"},
                }
            )
        )
        (product / "decisions.json").write_text(
            json.dumps({"schema_version": 1, "decisions": decisions})
        )

    save()
    return tmp_path, reqs, decisions, save


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("removed", "R01-R45"),
        ("duplicate", "duplicate requirement"),
        ("renamed", "missing Python selector"),
        ("orphan", "unknown requirement"),
        ("no_context", "without decision context"),
        ("fake_hardware", "cannot be labeled"),
    ],
)
def test_registry_refuses_lost_history_broken_links_and_overclaimed_proof(
    registry, fault, expected
):
    root, reqs, decisions, save = registry
    if fault == "removed":
        reqs.pop()
    elif fault == "duplicate":
        reqs.append(dict(reqs[0]))
    elif fault == "renamed":
        reqs[0]["verification"][0]["selector"] = "test_removed"
    elif fault == "orphan":
        decisions[0]["requirement_ids"].append("R999")
    elif fault == "no_context":
        decisions[0]["requirement_ids"].pop()
    else:
        reqs[0]["verification"][0]["layer"] = "hardware"
    save()
    with pytest.raises(gate.TraceabilityError, match=expected):
        gate.load_registry(root)


def test_generated_text_must_follow_the_single_registry(registry):
    root, _, _, _ = registry
    requirements, decisions, baseline = gate.load_registry(root)
    rendered = gate.render(requirements, decisions, baseline)
    gate.check_generated(root, rendered, write=True)
    gate.check_generated(root, rendered)
    page = root / "docs/product/functional.md"
    page.write_text(page.read_text().replace("사람 호출이 우선한다", "작업 수가 우선한다"))
    with pytest.raises(gate.TraceabilityError, match="stale generated"):
        gate.check_generated(root, rendered)


def one_check(kind="pytest", selector="test_waiting"):
    target = "tests/test_behavior.py" if kind == "pytest" else "tests/behavior.test.ts"
    return [{"id": "R39", "verification": [{"kind": kind, "target": target, "selector": selector}]}]


@pytest.mark.parametrize("outcome", ["failed", "skipped"])
def test_a_passing_parameter_cannot_hide_a_failed_or_skipped_parameter(outcome):
    cases = [
        {"classname": "tests.test_behavior", "name": "test_waiting[0]", "outcome": "passed"},
        {"classname": "tests.test_behavior", "name": "test_waiting[1]", "outcome": outcome},
    ]
    with pytest.raises(gate.TraceabilityError, match="failed or skipped"):
        gate.verify_links(one_check(), {"pytest": cases})


def test_same_name_from_another_file_cannot_satisfy_a_requirement():
    cases = [{"classname": "tests.test_other", "name": "test_waiting", "outcome": "passed"}]
    with pytest.raises(gate.TraceabilityError, match="not executed"):
        gate.verify_links(one_check(), {"pytest": cases})


def test_bun_requires_the_exact_executed_title_and_file():
    check = one_check("bun", "waiting 0")
    cases = [{"file": "tests/behavior.test.ts", "name": "waiting 1", "outcome": "passed"}]
    with pytest.raises(gate.TraceabilityError, match="not executed"):
        gate.verify_links(check, {"bun": cases})
    cases[0]["name"] = "waiting 0"
    assert gate.verify_links(check, {"bun": cases}) == {"pytest": 0, "bun": 1}


def test_real_junit_shapes_keep_skip_failure_and_param_identity(tmp_path):
    report = tmp_path / "pytest.xml"
    report.write_text(
        '<testsuites><testsuite><testcase classname="tests.test_behavior" '
        'name="test_waiting[0]"/><testcase classname="tests.test_behavior" '
        'name="test_waiting[1]"><skipped/></testcase>'
        '<testcase name="failure"><failure/></testcase></testsuite></testsuites>'
    )
    cases = gate.junit_cases(report)
    assert [c["outcome"] for c in cases] == ["passed", "skipped", "failed"]
    with pytest.raises(gate.TraceabilityError, match="failed or skipped"):
        gate.verify_links(one_check(), {"pytest": cases})


def test_old_report_directory_is_never_reused(tmp_path, monkeypatch):
    report_dir = tmp_path / "old-run"
    report_dir.mkdir()
    (report_dir / "pytest.xml").write_text("old passing report")
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: pytest.fail("must not start"))
    with pytest.raises(gate.TraceabilityError, match="must be new"):
        gate.execute_tests(tmp_path, one_check(), report_dir)


def test_input_receipt_detects_added_tests_and_ignores_bytecode(tmp_path):
    source = tmp_path / "tests"
    source.mkdir()
    (source / "test_behavior.py").write_text("pass\n")
    original = gate.input_hashes(tmp_path)
    (source / "cache.pyc").write_bytes(b"bytecode")
    assert gate.input_hashes(tmp_path) == original
    (source / "test_added.py").write_text("pass\n")
    assert gate.input_hashes(tmp_path) != original


def test_exact_parameter_id_can_contain_double_colons():
    selector = "test_waiting[case::value]"
    cases = [{"classname": "tests.test_behavior", "name": selector, "outcome": "passed"}]
    assert gate.verify_links(one_check(selector=selector), {"pytest": cases}) == {
        "pytest": 1,
        "bun": 0,
    }


def test_input_receipt_tracks_executed_experiment_helpers_not_old_evidence(tmp_path):
    folder = tmp_path / "experiments/gjc-e2e-audit"
    folder.mkdir(parents=True)
    helper = folder / "audit_support.py"
    helper.write_text("def verify(): return True\n")
    before = gate.input_hashes(tmp_path)
    helper.write_text("def verify(): return False\n")
    assert gate.input_hashes(tmp_path) != before
    after = gate.input_hashes(tmp_path)
    evidence = folder / "evidence"
    evidence.mkdir()
    (evidence / "old.py").write_text("historical transcript\n")
    assert gate.input_hashes(tmp_path) == after
