import pytest

from orca_keychron.models import OrcaAgent
from orca_keychron.worktree_tracker import WorktreeTracker


def agent(
    key: str,
    state: str,
    worktree: str = "repo::/one",
    host: str = "local",
    updated_at: int = 1,
) -> OrcaAgent:
    return OrcaAgent(key, state, "codex", worktree, host, updated_at)


def summary(tracker: WorktreeTracker, agents: list[OrcaAgent], now: float):
    return [
        (
            item.slot,
            item.state,
            item.worktree_id,
            item.agent_count,
            item.target_pane_keys,
        )
        for item in tracker.update(agents, now)
    ]


def test_tracker_groups_agents_by_host_and_worktree():
    tracker = WorktreeTracker()

    rows = summary(
        tracker,
        [
            agent("pane-a", "working", updated_at=1),
            agent("pane-b", "working", updated_at=2),
            agent("pane-c", "waiting", "repo::/two"),
        ],
        1,
    )

    assert rows == [
        (0, "working", "repo::/one", 2, ("pane-b", "pane-a")),
        (1, "waiting", "repo::/two", 1, ("pane-c",)),
    ]


def test_tracker_uses_attention_states_and_magenta_only_for_mixed_attention():
    tracker = WorktreeTracker()
    tracker.update([agent("work", "working"), agent("done", "working")], 1)

    assert summary(
        tracker,
        [agent("work", "working"), agent("done", "done", updated_at=2)],
        2,
    )[0][1:] == ("done", "repo::/one", 2, ("done",))

    assert summary(
        tracker,
        [
            agent("work", "working"),
            agent("done", "done", updated_at=2),
            agent("wait", "waiting", updated_at=3),
        ],
        3,
    )[0][1:] == ("mixed", "repo::/one", 3, ("wait", "done"))


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (("working", "working"), "working"),
        (("working", "blocked"), "error"),
        (("working", "waiting"), "waiting"),
        (("working", "done"), "done"),
        (("blocked", "waiting"), "mixed"),
        (("blocked", "done"), "mixed"),
        (("waiting", "done"), "mixed"),
    ],
)
def test_worktree_state_policy(states: tuple[str, ...], expected: str):
    tracker = WorktreeTracker()
    pane_keys = [f"pane-{index}" for index in range(len(states))]
    tracker.update([agent(key, "working") for key in pane_keys], 1)

    indicators = tracker.update(
        [agent(pane_keys[index], state) for index, state in enumerate(states)],
        2,
    )

    assert indicators[0].state == expected


def test_tracker_orders_mixed_targets_by_action_then_oldest_timestamp():
    tracker = WorktreeTracker()
    tracker.update(
        [
            agent("done", "working"),
            agent("wait-new", "working"),
            agent("error-new", "working"),
            agent("error-old", "working"),
        ],
        1,
    )

    row = summary(
        tracker,
        [
            agent("done", "done", updated_at=1),
            agent("wait-new", "waiting", updated_at=4),
            agent("error-new", "blocked", updated_at=3),
            agent("error-old", "blocked", updated_at=2),
        ],
        2,
    )[0]

    assert row[1] == "mixed"
    assert row[4] == ("error-old", "error-new", "wait-new", "done")


def test_tracker_ignores_preexisting_done_rows_but_keeps_observed_completion():
    tracker = WorktreeTracker()

    assert summary(
        tracker,
        [agent("old", "done"), agent("live", "working", "repo::/two")],
        1,
    ) == [(0, "working", "repo::/two", 1, ("live",))]
    assert summary(
        tracker,
        [agent("old", "done"), agent("live", "working", "repo::/two")],
        1.5,
    ) == [(0, "working", "repo::/two", 1, ("live",))]

    assert summary(tracker, [agent("live", "done", "repo::/two")], 2) == [
        (0, "done", "repo::/two", 1, ("live",))
    ]


def test_tracker_keeps_idle_worktree_and_reuses_oldest_idle_slot():
    tracker = WorktreeTracker(max_slots=2)
    tracker.update(
        [agent("a", "working"), agent("b", "working", "repo::/two")],
        1,
    )

    assert summary(tracker, [], 2) == [
        (0, "idle", "repo::/one", 0, ("a",)),
        (1, "idle", "repo::/two", 0, ("b",)),
    ]
    rows = summary(tracker, [agent("c", "working", "repo::/three")], 3)

    assert rows == [
        (0, "working", "repo::/three", 1, ("c",)),
        (1, "idle", "repo::/two", 0, ("b",)),
    ]


def test_tracker_keeps_same_worktree_ids_separate_across_hosts():
    tracker = WorktreeTracker()

    rows = summary(
        tracker,
        [agent("local", "working"), agent("remote", "waiting", host="ssh:prod")],
        1,
    )

    assert [(row[0], row[1]) for row in rows] == [(0, "working"), (1, "waiting")]
