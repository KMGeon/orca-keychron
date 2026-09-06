#!/usr/bin/env python3
"""Print a Markdown summary from JUnit XML test results."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def find_result_files(arguments: list[str]) -> list[Path]:
    paths = [Path(argument) for argument in arguments]
    if not paths:
        paths = [Path("test-results")]

    result_files: set[Path] = set()
    for path in paths:
        if path.is_file() and path.suffix == ".xml":
            result_files.add(path)
        elif path.is_dir():
            result_files.update(path.rglob("*.xml"))
    return sorted(result_files)


def counts(element: ET.Element) -> tuple[int, int, int, int]:
    tests = int(element.attrib.get("tests", 0))
    failures = int(element.attrib.get("failures", 0))
    errors = int(element.attrib.get("errors", 0))
    skipped = int(element.attrib.get("skipped", 0))
    return tests, failures, errors, skipped


def print_table(status: str, passed: str, failed: str, skipped: str) -> None:
    print("| Test Status | Passed | Failed | Skipped |")
    print("| :--- | ---: | ---: | ---: |")
    print(f"| {status} | {passed} | {failed} | {skipped} |")


def main() -> int:
    result_files = find_result_files(sys.argv[1:])
    if not result_files:
        print_table("⚪ Not run", "-", "-", "-")
        return 0

    total_tests = 0
    total_failures = 0
    total_errors = 0
    total_skipped = 0

    for result_file in result_files:
        root = ET.parse(result_file).getroot()
        if root.tag == "testsuite" or "tests" in root.attrib:
            suites = [root]
        else:
            suites = list(root.findall("./testsuite"))

        for suite in suites:
            tests, failures, errors, skipped = counts(suite)
            total_tests += tests
            total_failures += failures
            total_errors += errors
            total_skipped += skipped

    failed = total_failures + total_errors
    passed = total_tests - failed - total_skipped
    status = "✅ Success" if failed == 0 else "❌ Failed"
    print_table(status, str(passed), str(failed), str(total_skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
