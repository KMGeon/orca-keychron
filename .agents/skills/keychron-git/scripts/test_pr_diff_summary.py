from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).with_name("pr_diff_summary.py")
SPEC = importlib.util.spec_from_file_location("pr_diff_summary", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_format_delta_uses_colored_sign_without_circle_emoji() -> None:
    assert MODULE.format_delta(22) == r"$\color{#1f883d}{\mathbf{+22}}$"
    assert MODULE.format_delta(-13) == r"$\color{#cf222e}{\mathbf{−13}}$"
    assert MODULE.format_delta(0) == r"$\color{#656d76}{\mathbf{0}}$"
