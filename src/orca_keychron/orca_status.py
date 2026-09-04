from __future__ import annotations

import json
import os
import shlex
import subprocess
from collections.abc import Iterable, Sequence
from typing import Any

from .models import ORCA_AGENT_STATES, OrcaAgent


class OrcaStatusError(RuntimeError):
    pass


def default_orca_command() -> list[str]:
    configured = os.environ.get("ORCA_CLI_COMMAND")
    if configured:
        return shlex.split(configured)
    return ["orca-ide" if os.name == "posix" and sys_platform() == "linux" else "orca"]


def sys_platform() -> str:
    import sys

    return sys.platform


def parse_orca_agents(payload: Any, host_ids: Iterable[str] | None = None) -> list[OrcaAgent]:
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise OrcaStatusError("Orca returned an unsuccessful response")
    result = payload.get("result")
    worktrees = result.get("worktrees") if isinstance(result, dict) else None
    if not isinstance(worktrees, list):
        raise OrcaStatusError("Orca response does not contain result.worktrees")

    allowed_hosts = set(host_ids) if host_ids else None
    agents: list[OrcaAgent] = []
    for worktree in worktrees:
        if not isinstance(worktree, dict):
            continue
        host_id = str(worktree.get("hostId") or "unknown")
        if allowed_hosts is not None and host_id not in allowed_hosts:
            continue
        worktree_id = worktree.get("worktreeId")
        if not isinstance(worktree_id, str) or not worktree_id:
            continue
        rows = worktree.get("agents")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            pane_key = row.get("paneKey")
            state = row.get("state")
            if not isinstance(pane_key, str) or not pane_key or state not in ORCA_AGENT_STATES:
                continue
            updated_at = row.get("updatedAt")
            agents.append(
                OrcaAgent(
                    pane_key=pane_key,
                    state=state,
                    agent_type=str(row.get("agentType") or "unknown"),
                    worktree_id=worktree_id,
                    host_id=host_id,
                    updated_at=updated_at if isinstance(updated_at, int) else None,
                )
            )
    return agents


class OrcaStatusSource:
    def __init__(
        self,
        command: Sequence[str] | None = None,
        host_ids: Iterable[str] | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.command = list(command or default_orca_command())
        self.host_ids = tuple(host_ids) if host_ids else None
        self.timeout_seconds = timeout_seconds

    def snapshot(self) -> list[OrcaAgent]:
        args = [*self.command, "worktree", "ps", "--json"]
        try:
            completed = subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OrcaStatusError(f"Could not run {' '.join(args)}: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
            raise OrcaStatusError(f"Orca CLI failed: {detail}")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise OrcaStatusError("Orca CLI returned invalid JSON") from exc
        return parse_orca_agents(payload, self.host_ids)
