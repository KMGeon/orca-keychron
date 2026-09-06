from __future__ import annotations

from collections.abc import Iterable, Sequence

from .models import DisplayIndicator

HsvColor = tuple[int, int, int]
OFF: HsvColor = (0, 0, 0)
YELLOW: HsvColor = (43, 255, 255)
ORANGE: HsvColor = (21, 255, 255)
RED: HsvColor = (0, 255, 255)
GREEN: HsvColor = (85, 255, 255)
MAGENTA: HsvColor = (213, 255, 255)
SKY_BLUE: HsvColor = (145, 150, 255)
UNKNOWN: HsvColor = (0, 0, 255)
PAUSED: HsvColor = (180, 255, 140)
CANCELLED: HsvColor = (0, 0, 70)


def render_zone(
    worktrees: Iterable[DisplayIndicator],
    zone: Sequence[int],
) -> dict[int, HsvColor]:
    colors = dict.fromkeys(zone, SKY_BLUE)
    for worktree in worktrees:
        if worktree.slot < 0 or worktree.slot >= len(zone):
            continue
        if worktree.state == "working":
            color = YELLOW
        elif worktree.state == "waiting":
            color = ORANGE
        elif worktree.state in ("error", "failed"):
            color = RED
        elif worktree.state == "done":
            color = GREEN
        elif worktree.state == "mixed":
            color = MAGENTA
        elif worktree.state == "idle":
            color = SKY_BLUE
        elif worktree.state == "unknown":
            color = UNKNOWN
        elif worktree.state == "paused":
            color = PAUSED
        elif worktree.state == "cancelled":
            color = CANCELLED
        else:
            continue
        colors[zone[worktree.slot]] = color
    return colors
