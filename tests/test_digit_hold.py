from orca_keychron.digit_hold import DigitHoldListener, HoldSelection
from orca_keychron.models import WorktreeIndicator


def worktree(slot: int, *pane_keys: str) -> WorktreeIndicator:
    return WorktreeIndicator(
        "local",
        "repo::/worktree",
        "done",
        slot,
        pane_keys or ("tab:leaf",),
        len(pane_keys) or 1,
    )


def test_selection_opens_immediately_with_option():
    selection = HoldSelection()
    selection.set_worktrees([worktree(0)])

    selection.press("1", now=10, option_only=True)

    assert selection.pop_ready(10) == "tab:leaf"
    assert selection.pop_ready(12) is None


def test_immediate_selection_survives_key_release_before_poll():
    selection = HoldSelection()
    selection.set_worktrees([worktree(0)])

    selection.press("1", now=10, option_only=True)
    selection.release("1")

    assert selection.pop_ready(10.1) == "tab:leaf"


def test_selection_ignores_empty_slots_modifiers_and_released_keys():
    selection = HoldSelection(hold_seconds=1)
    selection.set_worktrees([worktree(9, "tab:zero")])

    selection.press("1", now=1)
    assert selection.pop_ready(2) is None

    selection.press("0", now=3, option_only=True)
    assert selection.suppress_repeat("0") is True
    selection.release("0")
    assert selection.pop_ready(5) is None


def test_selection_does_not_replay_after_trigger():
    selection = HoldSelection(hold_seconds=1)
    selection.set_worktrees([worktree(0)])
    selection.press("1", now=1, option_only=True)

    assert selection.pop_ready(2) == "tab:leaf"
    selection.release("1")


def test_selection_cancels_when_slot_is_reassigned():
    selection = HoldSelection(hold_seconds=1)
    selection.set_worktrees([worktree(0, "tab:first")])
    selection.press("1", now=1, option_only=True)
    selection.set_worktrees([worktree(0, "tab:second")])

    assert selection.pop_ready(2) is None


def test_selection_cycles_worktree_action_targets():
    selection = HoldSelection()
    selection.set_worktrees([worktree(0, "tab:error", "tab:waiting", "tab:done")])

    selected = []
    for now in range(3):
        selection.press("1", now=now, option_only=True)
        selected.append(selection.pop_ready(now))
        selection.release("1")

    assert selected == ["tab:error", "tab:waiting", "tab:done"]


def test_minus_and_equal_select_worktree_slots_eleven_and_twelve():
    selection = HoldSelection()
    selection.set_worktrees([worktree(10, "tab:minus"), worktree(11, "tab:equal")])

    selection.press("-", now=1, option_only=True)
    assert selection.pop_ready(1) == "tab:minus"
    selection.release("-")
    selection.press("=", now=2, option_only=True)
    assert selection.pop_ready(2) == "tab:equal"


class FakeQuartz:
    kCGEventKeyDown = 1
    kCGEventKeyUp = 2
    kCGKeyboardEventKeycode = 3
    kCGEventFlagMaskShift = 1 << 1
    kCGEventFlagMaskControl = 1 << 2
    kCGEventFlagMaskAlternate = 1 << 3
    kCGEventFlagMaskCommand = 1 << 4

    @staticmethod
    def CGEventGetIntegerValueField(event, _field):
        return event["keycode"]

    @staticmethod
    def CGEventGetFlags(event):
        return event["flags"]


def test_option_digit_passes_through_when_orca_is_not_frontmost():
    selection = HoldSelection()
    selection.set_worktrees([worktree(0)])
    listener = DigitHoldListener(selection, clock=lambda: 10, frontmost_check=lambda: False)
    listener._quartz = FakeQuartz
    event = {"keycode": 18, "flags": FakeQuartz.kCGEventFlagMaskAlternate}

    assert listener._darwin_intercept(FakeQuartz.kCGEventKeyDown, event) is event
    assert selection.pop_ready(10) is None


def test_option_digit_triggers_immediately_when_orca_is_frontmost():
    selection = HoldSelection()
    selection.set_worktrees([worktree(0)])
    listener = DigitHoldListener(selection, clock=lambda: 10, frontmost_check=lambda: True)
    listener._quartz = FakeQuartz
    event = {"keycode": 18, "flags": FakeQuartz.kCGEventFlagMaskAlternate}

    assert listener._darwin_intercept(FakeQuartz.kCGEventKeyDown, event) is None
    assert selection.pop_ready(10) == "tab:leaf"


def test_empty_option_digit_is_suppressed_only_while_orca_is_frontmost():
    selection = HoldSelection()
    listener = DigitHoldListener(selection, clock=lambda: 10, frontmost_check=lambda: True)
    listener._quartz = FakeQuartz
    event = {"keycode": 19, "flags": FakeQuartz.kCGEventFlagMaskAlternate}

    assert listener._darwin_intercept(FakeQuartz.kCGEventKeyDown, event) is None
    assert selection.pop_ready(10) is None


def test_option_minus_and_equal_use_mac_physical_keycodes():
    selection = HoldSelection()
    selection.set_worktrees([worktree(10, "tab:minus"), worktree(11, "tab:equal")])
    listener = DigitHoldListener(selection, clock=lambda: 10, frontmost_check=lambda: True)
    listener._quartz = FakeQuartz

    for keycode, expected in ((27, "tab:minus"), (24, "tab:equal")):
        event = {"keycode": keycode, "flags": FakeQuartz.kCGEventFlagMaskAlternate}
        assert listener._darwin_intercept(FakeQuartz.kCGEventKeyDown, event) is None
        assert selection.pop_ready(10) == expected
        assert listener._darwin_intercept(FakeQuartz.kCGEventKeyUp, event) is None
