from orca_keychron.models import WorktreeIndicator
from orca_keychron.rendering import (
    CANCELLED,
    GREEN,
    MAGENTA,
    ORANGE,
    PAUSED,
    RED,
    SKY_BLUE,
    UNKNOWN,
    YELLOW,
    render_zone,
)


def worktree(state: str, slot: int) -> WorktreeIndicator:
    return WorktreeIndicator("local", f"repo::{slot}", state, slot, ("tab:leaf",), 1)


def test_render_zone_maps_worktree_states_and_slots():
    zone = [10, 20, 30, 40, 50, 60]
    colors = render_zone(
        [
            worktree("working", 0),
            worktree("waiting", 1),
            worktree("error", 2),
            worktree("done", 3),
            worktree("mixed", 4),
            worktree("idle", 5),
        ],
        zone,
    )
    assert colors == {
        10: YELLOW,
        20: ORANGE,
        30: RED,
        40: GREEN,
        50: MAGENTA,
        60: SKY_BLUE,
    }


def test_render_zone_uses_sky_blue_for_unassigned_number_slots():
    assert render_zone([], [1, 2, 3]) == {1: SKY_BLUE, 2: SKY_BLUE, 3: SKY_BLUE}
    assert render_zone([worktree("working", 0)], [1, 2, 3]) == {
        1: YELLOW,
        2: SKY_BLUE,
        3: SKY_BLUE,
    }


def test_gjc_additional_states_are_distinct_from_orca_and_success():
    states = ("unknown", "failed", "paused", "cancelled", "idle")
    colors = render_zone([worktree(state, i) for i, state in enumerate(states)], range(5))
    assert colors == {0: UNKNOWN, 1: RED, 2: PAUSED, 3: CANCELLED, 4: SKY_BLUE}
    assert len({UNKNOWN, PAUSED, CANCELLED, SKY_BLUE, GREEN, ORANGE, YELLOW, RED}) == 8


def test_overflow_or_negative_slots_cannot_color_a_different_key():
    assert render_zone([worktree("failed", -1), worktree("working", 2)], [10, 20]) == {
        10: SKY_BLUE, 20: SKY_BLUE,
    }
