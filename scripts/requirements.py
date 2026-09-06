"""Generate requirement views and verify their links against fresh test executions.

This gate proves structural traceability and execution, not semantic completeness.
No third-party libraries are needed beyond the existing pytest/Bun test runners.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = Path("docs/product")
KINDS = {"functional": "기능", "nonfunctional": "비기능"}
LAYERS = {
    "unit": "단위",
    "integration": "통합",
    "runtime": "실제 실행",
    "hardware": "물리 기기",
    "documentation": "문서 검토",
}
AUTO = {"pytest", "bun"}
GENERATED = ("decisions.md", "functional.md", "nonfunctional.md", "test-map.md")


class TraceabilityError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TraceabilityError(message)


def strings(value: Any, label: str, *, empty: bool = False) -> list[str]:
    require(isinstance(value, list), f"{label}: expected a list")
    require(empty or bool(value), f"{label}: must not be empty")
    require(all(isinstance(x, str) and x.strip() for x in value), f"{label}: blank/nontext item")
    require(len(value) == len(set(value)), f"{label}: duplicate item")
    return value


def text_field(record: dict, key: str, label: str) -> str:
    value = record.get(key)
    require(isinstance(value, str) and bool(value.strip()), f"{label}.{key}: missing text")
    return value


def repo_file(root: Path, value: str) -> Path:
    require(isinstance(value, str) and bool(value), "file reference: expected a path")
    path = Path(value)
    require(not path.is_absolute() and ".." not in path.parts, f"unsafe reference: {value}")
    candidate = root / path
    require(candidate.resolve().is_relative_to(root.resolve()), f"external reference: {value}")
    require(candidate.is_file(), f"missing file: {value}")
    return candidate


def python_selectors(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.add(node.name)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result.add(f"{node.name}::{child.name}")
    return result


def load_registry(root: Path) -> tuple[list[dict], list[dict], dict]:
    def read(name: str) -> dict:
        value = json.loads((root / PRODUCT / name).read_text(encoding="utf-8"))
        require(
            isinstance(value, dict) and value.get("schema_version") == 1,
            f"{name}: unsupported schema",
        )
        return value

    req_data, decision_data = read("requirements.json"), read("decisions.json")
    requirements, decisions = req_data.get("requirements"), decision_data.get("decisions")
    require(isinstance(requirements, list) and bool(requirements), "requirements: empty registry")
    require(isinstance(decisions, list) and bool(decisions), "decisions: empty registry")
    require(all(isinstance(x, dict) for x in requirements + decisions), "record must be an object")
    req_ids = [text_field(r, "id", "requirement") for r in requirements]
    require(len(req_ids) == len(set(req_ids)), "duplicate requirement ID")
    require(all(re.fullmatch(r"R\d{2,}", x) for x in req_ids), "invalid requirement ID")
    require({f"R{i:02}" for i in range(1, 46)} <= set(req_ids), "baseline R01-R45 must be retained")
    decision_ids = [text_field(d, "id", "decision") for d in decisions]
    require(len(decision_ids) == len(set(decision_ids)), "duplicate decision ID")
    require(all(re.fullmatch(r"D\d{2,}", x) for x in decision_ids), "invalid decision ID")
    baseline = req_data.get("baseline")
    require(isinstance(baseline, dict), "missing historical baseline")
    repo_file(root, text_field(baseline, "report", "baseline"))
    text_field(baseline, "note", "baseline")
    selectors: dict[str, set[str]] = {}
    for r in requirements:
        label = r["id"]
        for key in ("area", "title", "statement"):
            text_field(r, key, label)
        kinds = strings(r.get("kinds"), label + ".kinds")
        require(set(kinds) <= KINDS.keys(), f"{label}: invalid requirement kind")
        strings(r.get("acceptance"), label + ".acceptance")
        strings(r.get("limitations"), label + ".limitations", empty=True)
        for value in strings(r.get("implementation"), label + ".implementation", empty=True):
            repo_file(root, value)
        checks = r.get("verification")
        require(
            isinstance(checks, list) and bool(checks), f"{label}: no verification or manual plan"
        )
        seen = set()
        for check in checks:
            require(isinstance(check, dict), f"{label}: verification must be an object")
            kind = check.get("kind")
            require(kind in AUTO | {"scenario", "manual", "document"}, f"{label}: invalid verifier")
            require(check.get("layer") in LAYERS, f"{label}: invalid proof layer")
            target = text_field(check, "target", label)
            path = repo_file(root, target)
            text_field(check, "note", label)
            selector = check.get("selector", "")
            require(isinstance(selector, str), f"{label}: selector must be text")
            identity = kind, target, selector
            require(identity not in seen, f"{label}: duplicate verification {identity}")
            seen.add(identity)
            if kind in AUTO:
                require(bool(selector.strip()), f"{label}: automatic verifier needs exact selector")
                require(
                    check["layer"] in {"unit", "integration"},
                    f"{label}: automated fixture cannot be labeled runtime/hardware proof",
                )
                if kind == "pytest":
                    require(
                        target.startswith("tests/") and path.suffix == ".py",
                        f"{label}: pytest target must be a test file",
                    )
                    if target not in selectors:
                        selectors[target] = python_selectors(path)
                    require(
                        selector.split("[", 1)[0] in selectors[target],
                        f"{label}: missing Python selector {target}::{selector}",
                    )
                else:
                    require(
                        target.startswith("tests/") and target.endswith(".test.ts"),
                        f"{label}: Bun target must be a test file",
                    )
            else:
                require(not selector, f"{label}: selectors are only for automatic tests")
                if kind == "scenario":
                    require(path.suffix == ".py", f"{label}: scenario must name its executable")
    for d in decisions:
        label = d["id"]
        for key in ("title", "decision"):
            text_field(d, key, label)
        require(
            d.get("status") in {"accepted", "rejected", "superseded", "deferred"},
            f"{label}: invalid decision status",
        )
        require(d.get("origin") in {"user", "implementation", "audit"}, f"{label}: invalid origin")
        for key in ("rationale", "alternatives", "consequences"):
            strings(d.get(key), label + "." + key)
        refs = strings(d.get("requirement_ids"), label + ".requirement_ids")
        require(set(refs) <= set(req_ids), f"{label}: unknown requirement reference")
        for value in strings(d.get("references"), label + ".references"):
            repo_file(root, value)
    linked = {rid for d in decisions for rid in d["requirement_ids"]}
    require(
        set(req_ids) <= linked,
        f"requirements without decision context: {sorted(set(req_ids) - linked)}",
    )
    return requirements, decisions, baseline


def link(path: str, label: str | None = None) -> str:
    return f"[{label or Path(path).name}](../../{path})"


def req_link(r: dict) -> str:
    view = "functional" if "functional" in r["kinds"] else "nonfunctional"
    return f"[{r['id']}]({view}.md#{r['id'].lower()})"


def bullet_lines(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] + [""]


def header(title: str, sources: str) -> list[str]:
    return [
        f"# {title}",
        "",
        f"> 자동 생성 문서 · 편집 원본: {sources}",
        "> 수정 후 `python scripts/requirements.py --write`로 갱신합니다.",
        "",
        (
            "[전체 안내](README.md) · [의사결정](decisions.md) · [기능](functional.md) · "
            "[비기능](nonfunctional.md) · [테스트 연결](test-map.md)"
        ),
        "",
    ]


def render(requirements: list[dict], decisions: list[dict], baseline: dict) -> dict[str, str]:
    by_id = {r["id"]: r for r in requirements}
    result = {}
    lines = header("의사결정 기록", "[decisions.json](decisions.json)")
    lines += [
        "최종 선택과 그 이유를 읽는 문서입니다. 검토했던 대안은 채택 여부를 구분해 남깁니다.",
        (
            "`사용자 제약·합의`는 기존 대화/개발 티켓의 합의, `구현 선택`은 구현 과정의 선택, "
            "`검증 후 수정`은 실험·회귀 테스트로 바로잡은 내용입니다."
        ),
        "",
        "| ID | 결정 | 상태 |",
        "|---|---|---|",
    ]
    statuses = {"accepted": "채택", "rejected": "제외", "superseded": "대체됨", "deferred": "보류"}
    origins = {"user": "사용자 제약·합의", "implementation": "구현 선택", "audit": "검증 후 수정"}
    for d in decisions:
        lines.append(
            f"| [{d['id']}](#{d['id'].lower()}) | {d['title']} | {statuses[d['status']]} |"
        )
    for d in decisions:
        lines += [
            "",
            f'<a id="{d["id"].lower()}"></a>',
            f"## {d['id']} · {d['title']}",
            "",
            f"**{statuses[d['status']]} · {origins[d['origin']]}**",
            "",
            d["decision"],
            "",
            "**선택한 이유**",
            "",
        ] + bullet_lines(d["rationale"])
        lines += ["**검토한 대안**", ""] + bullet_lines(d["alternatives"])
        lines += ["**영향과 한계**", ""] + bullet_lines(d["consequences"])
        lines += [
            "관련 요구사항: " + " · ".join(req_link(by_id[x]) for x in d["requirement_ids"]),
            "",
            "근거: " + " · ".join(link(p) for p in d["references"]),
            "",
        ]
    result["decisions.md"] = "\n".join(lines).rstrip() + "\n"
    for kind, label in KINDS.items():
        selected = [r for r in requirements if kind in r["kinds"]]
        lines = header(label + " 요구사항", "[requirements.json](requirements.json)")
        lines += [
            (
                f"이 보기에는 **{len(selected)}개**가 포함됩니다. 같은 요구사항이 기능과 품질 조건을 "
                "함께 가지면 두 보기에 나타나지만 ID와 원본은 하나입니다."
            ),
            "수용 기준은 요구하는 동작입니다. 실제 검증 범위는 각 항목의 테스트 연결과 한계를 함께 읽습니다.",
            "",
            "| ID | 영역 | 요구사항 |",
            "|---|---|---|",
        ]
        for r in selected:
            lines.append(f"| [{r['id']}](#{r['id'].lower()}) | {r['area']} | {r['title']} |")
        for r in selected:
            related = [d for d in decisions if r["id"] in d["requirement_ids"]]
            lines += [
                "",
                f'<a id="{r["id"].lower()}"></a>',
                f"## {r['id']} · {r['title']}",
                "",
                r["statement"],
                "",
                "**수용 기준**",
                "",
            ] + bullet_lines(r["acceptance"])
            if r["limitations"]:
                lines += ["**지원·검증 한계**", ""] + bullet_lines(r["limitations"])
            lines += [
                f"[테스트와 구현 위치](test-map.md#{r['id'].lower()}) · 결정: "
                + " · ".join(f"[{d['id']}](decisions.md#{d['id'].lower()})" for d in related),
                "",
            ]
        result[kind + ".md"] = "\n".join(lines).rstrip() + "\n"
    lines = header("요구사항과 테스트 연결", "[requirements.json](requirements.json)")
    automatic = sum(any(c["kind"] in AUTO for c in r["verification"]) for r in requirements)
    lines += [
        (
            f"총 **{len(requirements)}개 요구사항 중 {automatic}개**에 자동 테스트가 연결되어 있습니다. "
            "이 수치는 연결 범위이며, 모든 수용 기준이 증명되었다는 비율이 아닙니다."
        ),
        (
            "`pytest`와 `bun` 연결은 CI에서 새로 실행한 JUnit 결과로 확인합니다. "
            "시나리오·물리 기기·문서 검토는 별도 검증이며 자동 PASS로 바꾸지 않습니다."
        ),
        "",
        "기준 검증 기록: " + link(baseline["report"]) + ". " + baseline["note"],
        "",
        "역방향 탐색: 테스트 이름으로 이 문서나 `requirements.json`을 검색하면 영향받는 요구사항을 찾습니다.",
        "",
    ]
    names = {
        "pytest": "pytest",
        "bun": "Bun",
        "scenario": "별도 실행 시나리오",
        "manual": "수동 확인",
        "document": "문서 검토",
    }
    for r in requirements:
        lines += [
            f'<a id="{r["id"].lower()}"></a>',
            f"## {r['id']} · {r['title']}",
            "",
            "요구사항: " + req_link(r),
            "",
        ]
        if r["implementation"]:
            lines += ["구현: " + " · ".join(link(p) for p in r["implementation"]), ""]
        for check in r["verification"]:
            lines += [
                f"**{names[check['kind']]} · {LAYERS[check['layer']]}** — " + link(check["target"])
            ]
            if check.get("selector"):
                lines += ["", f"`{check['selector']}`"]
            lines += ["", check["note"], ""]
    result["test-map.md"] = "\n".join(lines).rstrip() + "\n"
    return result


def check_generated(root: Path, rendered: dict[str, str], *, write: bool = False) -> None:
    for name, content in rendered.items():
        path = root / PRODUCT / name
        if write:
            path.write_text(content, encoding="utf-8")
        else:
            require(
                path.is_file() and path.read_text(encoding="utf-8") == content,
                f"stale generated document: {path.relative_to(root)}; run --write",
            )


def junit_cases(path: Path) -> list[dict[str, str]]:
    xml = ET.parse(path).getroot()
    result = []
    for case in xml.iter("testcase"):
        state = "passed"
        if case.find("failure") is not None or case.find("error") is not None:
            state = "failed"
        elif case.find("skipped") is not None:
            state = "skipped"
        result.append(dict(case.attrib, outcome=state))
    require(bool(result), f"empty JUnit report: {path}")
    return result


def verify_links(requirements: list[dict], reports: dict[str, list[dict]]) -> dict[str, int]:
    counts = {"pytest": 0, "bun": 0}
    for requirement in requirements:
        for check in requirement["verification"]:
            kind = check["kind"]
            if kind not in AUTO:
                continue
            selector = check["selector"]
            if kind == "pytest":
                identity, bracket, parameter = selector.partition("[")
                parts = identity.split("::")
                test_name = parts[-1] + bracket + parameter
                classname = check["target"][:-3].replace("/", ".")
                if len(parts) > 1:
                    classname += "." + ".".join(parts[:-1])
                matches = [
                    c
                    for c in reports[kind]
                    if c.get("classname") == classname
                    and (
                        c.get("name") == test_name
                        or (not bracket and c.get("name", "").startswith(test_name + "["))
                    )
                ]
            else:
                matches = [
                    c
                    for c in reports[kind]
                    if c.get("file") == check["target"] and c.get("name") == selector
                ]
            label = f"{requirement['id']} {check['target']}::{selector}"
            require(bool(matches), f"test not executed: {label}")
            require(
                all(c["outcome"] == "passed" for c in matches),
                f"linked test failed or skipped: {label}",
            )
            counts[kind] += 1
    return counts


def input_hashes(root: Path) -> dict[str, str]:
    paths = set()
    for folder in ("src", "tests", "scripts", "docs/product", ".github/workflows"):
        paths.update(
            p
            for p in (root / folder).rglob("*")
            if p.is_file() and p.suffix in {".py", ".ts", ".json", ".md", ".yml"}
        )
    paths.update(
        p
        for p in (root / "experiments").rglob("*")
        if p.is_file()
        and p.suffix in {".py", ".ts"}
        and "evidence" not in p.relative_to(root / "experiments").parts
    )
    paths.update(root / name for name in ("pyproject.toml", "uv.lock") if (root / name).is_file())
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)
    }


def execute_tests(root: Path, requirements: list[dict], report_dir: Path) -> dict:
    require(not report_dir.exists(), f"report directory must be new: {report_dir}")
    wheel_dir = os.environ.get("GJC_TEST_WHEEL_DIR")
    require(bool(wheel_dir), "set GJC_TEST_WHEEL_DIR to a freshly built wheel directory")
    before = input_hashes(root)
    report_dir.mkdir(parents=True, mode=0o700)
    home = report_dir / "home"
    home.mkdir(mode=0o700)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GJC_TEST_WHEEL_DIR": str(Path(wheel_dir).resolve()),
    }
    commands = {
        "pytest": [sys.executable, "-m", "pytest", "-q", f"--junitxml={report_dir / 'pytest.xml'}"],
        "bun": [
            "bun",
            "test",
            "tests/",
            "--reporter=junit",
            f"--reporter-outfile={report_dir / 'bun.xml'}",
        ],
    }
    for name, command in commands.items():
        result = subprocess.run(command, cwd=root, env=env, check=False, timeout=180)
        require(result.returncode == 0, f"{name} exited {result.returncode}; no traceability PASS")
    require(input_hashes(root) == before, "source/registry/docs changed during verification; rerun")
    reports = {name: junit_cases(report_dir / f"{name}.xml") for name in commands}
    counts = verify_links(requirements, reports)
    receipt = {
        "status": "passed",
        "python": sys.version.split()[0],
        "linkedChecks": counts,
        "testCases": {name: len(cases) for name, cases in reports.items()},
        "inputHashes": before,
        "commands": commands,
        "boundary": "fresh unit/integration execution and structural links; "
        "not semantic completeness, actual GJC, physical HID or model compliance",
    }
    (report_dir / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="regenerate the four Markdown views")
    mode.add_argument(
        "--check", action="store_true", help="check links/schema/generated views only"
    )
    mode.add_argument(
        "--verify-tests", action="store_true", help="run pytest/Bun and verify fresh results"
    )
    parser.add_argument("--report-dir", type=Path, help="new directory for fresh test reports")
    args = parser.parse_args(argv)
    try:
        requirements, decisions, baseline = load_registry(ROOT)
        check_generated(ROOT, render(requirements, decisions, baseline), write=args.write)
        print(
            f"Registry: {len(requirements)} requirements, {len(decisions)} decisions; views agree.",
            flush=True,
        )
        if args.verify_tests:
            if args.report_dir:
                report_dir = args.report_dir.resolve()
            else:
                report_dir = Path(tempfile.mkdtemp(prefix="gjc-requirements-")) / "run"
            result = execute_tests(ROOT, requirements, report_dir)
            print(f"Fresh execution links PASS: {result['linkedChecks']}; reports: {report_dir}")
        elif not args.write:
            print(
                "Structural check only; test execution and Bun selector resolution not certified."
            )
        return 0
    except (
        TraceabilityError,
        OSError,
        ValueError,
        SyntaxError,
        ET.ParseError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"Requirement gate failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
