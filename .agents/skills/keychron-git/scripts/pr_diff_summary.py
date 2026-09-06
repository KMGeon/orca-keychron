#!/usr/bin/env python3
"""Print a one-row Markdown summary for a pull request diff."""

from __future__ import annotations

import subprocess
import sys


def format_delta(value: int) -> str:
    if value == 0:
        return r"$\color{#656d76}{\mathbf{0}}$"
    color = "#1f883d" if value > 0 else "#cf222e"
    sign = "+" if value > 0 else "−"
    return rf"$\color{{{color}}}{{\mathbf{{{sign}{abs(value)}}}}}$"


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "main"
    result = subprocess.run(
        ["git", "diff", "--numstat", f"{base}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )

    files = 0
    added = 0
    deleted = 0

    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue

        files += 1
        added_text, deleted_text, _ = parts
        if added_text.isdigit():
            added += int(added_text)
        if deleted_text.isdigit():
            deleted += int(deleted_text)

    net = added - deleted
    print("| Files | Added | Deleted | Net |")
    print("| ---: | ---: | ---: | ---: |")
    print(f"| **{files}** | {format_delta(added)} | {format_delta(-deleted)} | {format_delta(net)} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
