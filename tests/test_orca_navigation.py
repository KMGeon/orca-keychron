import json
import subprocess

import pytest

from orca_keychron.orca_navigation import (
    OrcaNavigationError,
    OrcaWorktreeTab,
    OrcaWorktreeTabNavigator,
    terminal_for_pane,
)


def terminal_payload():
    return {
        "ok": True,
        "result": {
            "terminals": [
                {
                    "handle": "term-1",
                    "worktreeId": "worktree-1",
                    "tabId": "tab-1",
                    "leafId": "leaf-1",
                    "connected": True,
                }
            ]
        },
    }


def test_terminal_for_pane_matches_tab_and_leaf():
    assert terminal_for_pane(terminal_payload(), "tab-1:leaf-1")["handle"] == "term-1"
    assert terminal_for_pane(terminal_payload(), "tab-1:other") is None


def test_navigator_refreshes_handle_and_switches_worktree_tab():
    calls = []

    def runner(args, **_kwargs):
        calls.append(args)
        payload = (
            terminal_payload()
            if args[1:3] == ["terminal", "list"]
            else {
                "ok": True,
                "result": {
                    "focus": {
                        "navigated": True,
                        "worktreeId": "worktree-1",
                        "tabId": "tab-1",
                    }
                },
            }
        )
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    navigator = OrcaWorktreeTabNavigator(["orca"], runner=runner)

    assert navigator.open("tab-1:leaf-1") == OrcaWorktreeTab("worktree-1", "tab-1")
    assert calls == [
        ["orca", "terminal", "list", "--json"],
        ["orca", "terminal", "switch", "--terminal", "term-1", "--json"],
    ]


def test_navigator_rejects_missing_terminal():
    def runner(args, **_kwargs):
        return subprocess.CompletedProcess(args, 0, json.dumps(terminal_payload()), "")

    with pytest.raises(OrcaNavigationError, match="No connected"):
        OrcaWorktreeTabNavigator(["orca"], runner=runner).open("missing:pane")


def test_navigator_rejects_wrong_worktree_tab_response():
    def runner(args, **_kwargs):
        payload = (
            terminal_payload()
            if args[1:3] == ["terminal", "list"]
            else {
                "ok": True,
                "result": {
                    "focus": {
                        "navigated": True,
                        "worktreeId": "other-worktree",
                        "tabId": "other-tab",
                    }
                },
            }
        )
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    with pytest.raises(OrcaNavigationError, match="different worktree tab"):
        OrcaWorktreeTabNavigator(["orca"], runner=runner).open("tab-1:leaf-1")
