from __future__ import annotations

from dataclasses import dataclass

ORCA_AGENT_STATES = frozenset({"working", "waiting", "blocked", "done"})


@dataclass(frozen=True)
class OrcaAgent:
    pane_key: str
    state: str
    agent_type: str
    worktree_id: str
    host_id: str
    updated_at: int | None = None


@dataclass(frozen=True)
class WorktreeIndicator:
    host_id: str
    worktree_id: str
    state: str
    slot: int
    target_pane_keys: tuple[str, ...]
    agent_count: int
