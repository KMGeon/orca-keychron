"""Manual Option+1 target-equivalent check with mandatory UI restoration.

This does not synthesize a keypress. The operator must provide a fresh owned test
terminal pane and the original known pane to restore.
"""

from __future__ import annotations

import argparse

from orca_keychron.orca_navigation import OrcaWorktreeTabNavigator


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-pane", required=True, help="Fresh owned test paneKey")
    parser.add_argument("--restore-pane", required=True, help="Original known UI paneKey")
    args = parser.parse_args()
    if args.target_pane == args.restore_pane:
        parser.error("target and restore panes must differ")
    navigator = OrcaWorktreeTabNavigator(["orca"])
    try:
        target = navigator.open(args.target_pane)
        print(f"target={target.worktree_id} tab={target.tab_id}")
    finally:
        restored = navigator.open(args.restore_pane)
        print(f"restored={restored.worktree_id} tab={restored.tab_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
