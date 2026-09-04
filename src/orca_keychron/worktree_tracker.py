from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .models import OrcaAgent, WorktreeIndicator

WorktreeKey = tuple[str, str]
ATTENTION_STATES = frozenset({"blocked", "waiting", "done"})
TARGET_PRIORITY = {"blocked": 0, "waiting": 1, "done": 2, "working": 3}


@dataclass
class TrackedWorktree:
    host_id: str
    worktree_id: str
    slot: int
    agents: dict[str, OrcaAgent] = field(default_factory=dict)
    last_pane_key: str | None = None
    idle_since: float | None = None


class WorktreeTracker:
    """Aggregates Orca agents into stable, action-oriented worktree slots."""

    def __init__(self, max_slots: int = 10) -> None:
        if max_slots < 1:
            raise ValueError("At least one worktree slot is required")
        self.max_slots = max_slots
        self._worktrees: dict[WorktreeKey, TrackedWorktree] = {}
        self._observed_live_panes: set[tuple[str, str, str]] = set()

    def update(self, agents: Iterable[OrcaAgent], now: float) -> list[WorktreeIndicator]:
        grouped: dict[WorktreeKey, dict[str, OrcaAgent]] = {}
        for agent in agents:
            key = (agent.host_id, agent.worktree_id)
            pane_identity = (*key, agent.pane_key)
            if agent.state != "done":
                self._observed_live_panes.add(pane_identity)
            elif pane_identity not in self._observed_live_panes:
                continue
            grouped.setdefault(key, {})[agent.pane_key] = agent

        for key, tracked in self._worktrees.items():
            rows = grouped.get(key)
            if rows:
                tracked.agents = rows
                tracked.last_pane_key = self._most_recent(rows.values()).pane_key
                tracked.idle_since = None
            else:
                tracked.agents = {}
                if tracked.idle_since is None:
                    tracked.idle_since = now

        for key, rows in grouped.items():
            if key in self._worktrees or not rows:
                continue
            slot = self._allocate_slot(now)
            if slot is None:
                continue
            latest = self._most_recent(rows.values())
            self._worktrees[key] = TrackedWorktree(
                host_id=key[0],
                worktree_id=key[1],
                slot=slot,
                agents=rows,
                last_pane_key=latest.pane_key,
            )

        indicators = [self._indicator(tracked) for tracked in self._worktrees.values()]
        return sorted(indicators, key=lambda indicator: indicator.slot)

    def _indicator(self, tracked: TrackedWorktree) -> WorktreeIndicator:
        agents = list(tracked.agents.values())
        states = {agent.state for agent in agents}
        attention = states & ATTENTION_STATES
        if len(attention) >= 2:
            state = "mixed"
            target_states = ATTENTION_STATES
        elif "blocked" in attention:
            state = "error"
            target_states = frozenset({"blocked"})
        elif "waiting" in attention:
            state = "waiting"
            target_states = frozenset({"waiting"})
        elif "done" in attention:
            state = "done"
            target_states = frozenset({"done"})
        elif "working" in states:
            state = "working"
            target_states = frozenset({"working"})
        else:
            state = "idle"
            target_states = frozenset()

        targets = [agent for agent in agents if agent.state in target_states]
        targets.sort(key=self._target_sort_key)
        pane_keys = tuple(agent.pane_key for agent in targets)
        if not pane_keys and tracked.last_pane_key is not None:
            pane_keys = (tracked.last_pane_key,)
        return WorktreeIndicator(
            host_id=tracked.host_id,
            worktree_id=tracked.worktree_id,
            state=state,
            slot=tracked.slot,
            target_pane_keys=pane_keys,
            agent_count=len(agents),
        )

    @staticmethod
    def _target_sort_key(agent: OrcaAgent) -> tuple[int, int, str]:
        timestamp = agent.updated_at if agent.updated_at is not None else 0
        if agent.state == "working":
            timestamp = -timestamp
        return TARGET_PRIORITY[agent.state], timestamp, agent.pane_key

    @staticmethod
    def _most_recent(agents: Iterable[OrcaAgent]) -> OrcaAgent:
        return max(
            agents,
            key=lambda agent: (
                agent.updated_at if agent.updated_at is not None else 0,
                agent.pane_key,
            ),
        )

    def _allocate_slot(self, now: float) -> int | None:
        used = {tracked.slot for tracked in self._worktrees.values()}
        for slot in range(self.max_slots):
            if slot not in used:
                return slot
        idle = [tracked for tracked in self._worktrees.values() if not tracked.agents]
        if not idle:
            return None
        evicted = min(
            idle,
            key=lambda tracked: (
                tracked.idle_since if tracked.idle_since is not None else now,
                tracked.slot,
            ),
        )
        del self._worktrees[(evicted.host_id, evicted.worktree_id)]
        return evicted.slot
