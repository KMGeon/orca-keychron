from __future__ import annotations

from collections.abc import Iterable, Sequence

from .models import WorktreeIndicator

HsvColor = tuple[int, int, int]
OFF: HsvColor = (0, 0, 0)
YELLOW: HsvColor = (43, 255, 255)
ORANGE: HsvColor = (21, 255, 255)
RED: HsvColor = (0, 255, 255)
GREEN: HsvColor = (85, 255, 255)
MAGENTA: HsvColor = (213, 255, 255)
SKY_BLUE: HsvColor = (145, 150, 255)


def render_zone(
    worktrees: Iterable[WorktreeIndicator],
    zone: Sequence[int],
) -> dict[int, HsvColor]:
    colors = dict.fromkeys(zone, SKY_BLUE)
    for worktree in worktrees:
        if worktree.slot >= len(zone):
            continue
        if worktree.state == "working":
            color = YELLOW
        elif worktree.state == "waiting":
            color = ORANGE
        elif worktree.state == "error":
            color = RED
        elif worktree.state == "done":
            color = GREEN
        elif worktree.state == "mixed":
            color = MAGENTA
        elif worktree.state == "idle":
            color = SKY_BLUE
        else:
            continue
        colors[zone[worktree.slot]] = color
    return colors
