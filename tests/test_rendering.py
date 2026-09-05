from orca_keychron.models import WorktreeIndicator
from orca_keychron.rendering import (
    GREEN,
    MAGENTA,
    ORANGE,
    RED,
    SKY_BLUE,
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
