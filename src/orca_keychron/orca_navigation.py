from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


class OrcaNavigationError(RuntimeError):
    pass


@dataclass(frozen=True)
class OrcaWorktreeTab:
    worktree_id: str
    tab_id: str


def terminal_for_pane(payload: Any, pane_key: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise OrcaNavigationError("Orca returned an unsuccessful terminal list response")
    result = payload.get("result")
    terminals = result.get("terminals") if isinstance(result, dict) else None
    if not isinstance(terminals, list):
        raise OrcaNavigationError("Orca response does not contain result.terminals")
    for terminal in terminals:
        if not isinstance(terminal, dict):
            continue
        terminal_pane = f"{terminal.get('tabId', '')}:{terminal.get('leafId', '')}"
        if terminal_pane == pane_key and terminal.get("connected") is True:
            return terminal
    return None


class OrcaWorktreeTabNavigator:
    def __init__(
        self,
        command: Sequence[str],
        timeout_seconds: float = 10.0,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.command = list(command)
        self.timeout_seconds = timeout_seconds
        self.runner = runner

    def open(self, pane_key: str) -> OrcaWorktreeTab:
        payload = self._run_json([*self.command, "terminal", "list", "--json"])
        terminal = terminal_for_pane(payload, pane_key)
        if terminal is None:
            raise OrcaNavigationError(f"No connected Orca terminal matches pane {pane_key}")
        handle = terminal.get("handle")
        if not isinstance(handle, str) or not handle:
            raise OrcaNavigationError("Matched Orca terminal does not have a runtime handle")
        worktree_id = terminal.get("worktreeId")
        tab_id = terminal.get("tabId")
        if not isinstance(worktree_id, str) or not worktree_id:
            raise OrcaNavigationError("Matched Orca terminal does not have a worktree ID")
        if not isinstance(tab_id, str) or not tab_id:
            raise OrcaNavigationError("Matched Orca terminal does not have a tab ID")
        response = self._run_json(
            [*self.command, "terminal", "switch", "--terminal", handle, "--json"]
        )
        result = response.get("result")
        focus = result.get("focus") if isinstance(result, dict) else None
        if not isinstance(focus, dict) or focus.get("navigated") is not True:
            raise OrcaNavigationError("Orca did not navigate to the requested worktree tab")
        if focus.get("worktreeId") != worktree_id or focus.get("tabId") != tab_id:
            raise OrcaNavigationError("Orca navigated to a different worktree tab")
        return OrcaWorktreeTab(worktree_id=worktree_id, tab_id=tab_id)

    def _run_json(self, args: list[str]) -> dict[str, Any]:
        try:
            completed = self.runner(
                args,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OrcaNavigationError(f"Could not run {' '.join(args)}: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
            raise OrcaNavigationError(f"Orca CLI failed: {detail}")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise OrcaNavigationError("Orca CLI returned invalid JSON") from exc
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise OrcaNavigationError("Orca CLI returned an unsuccessful response")
        return payload
