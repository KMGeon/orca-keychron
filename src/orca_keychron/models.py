from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

ORCA_AGENT_STATES = frozenset({"working", "waiting", "blocked", "done"})


class DisplayIndicator(Protocol):
    """Shared rendering/navigation view; source identities remain source-specific."""

    @property
    def identity_label(self) -> str: ...

    @property
    def state(self) -> str: ...

    @property
    def slot(self) -> int: ...

    @property
    def target_pane_keys(self) -> tuple[str, ...]: ...

    @property
    def agent_count(self) -> int: ...


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

    @property
    def identity_label(self) -> str:
        return self.worktree_id
