"""Sub-project C: the pure catch-action decision brain (no emulator)."""

from dexbot.catching import CatchView, choose_catch_action


def view(**kw):
    base = dict(
        active_index=0,
        active_knows_false_swipe=False,
        party_weakener_index=None,
        opponent_hp_fraction=1.0,
        opponent_is_statused=False,
        one_turn_catch_chance=0.1,
        safe_chip_move_index=None,
        status_move_index=None,
        false_swipe_move_index=None,
    )
    base.update(kw)
    return CatchView(**base)


def test_high_odds_just_throws():
    assert choose_catch_action(view(one_turn_catch_chance=0.6)) == ("ball", None)


def test_rotates_to_weakener_when_active_is_not_one():
    # active has no weakener move; a benched weakener exists at index 3
    assert choose_catch_action(view(party_weakener_index=3)) == ("rotate", 3)


def test_no_rotate_when_active_is_the_weakener():
    # active already knows False Swipe → don't rotate away
    act = choose_catch_action(view(active_knows_false_swipe=True, party_weakener_index=0,
                                   false_swipe_move_index=2))
    assert act[0] != "rotate"


def test_status_before_false_swipe():
    act = choose_catch_action(view(active_knows_false_swipe=True, false_swipe_move_index=2,
                                   status_move_index=1, party_weakener_index=0))
    assert act == ("move", 1)  # sleep first


def test_false_swipe_when_statused_and_hp_high():
    act = choose_catch_action(view(active_knows_false_swipe=True, false_swipe_move_index=2,
                                   opponent_is_statused=True, opponent_hp_fraction=0.9,
                                   party_weakener_index=0))
    assert act == ("move", 2)


def test_false_swipe_stops_at_one_hp():
    # already at the 1-HP floor → don't False Swipe again, throw
    act = choose_catch_action(view(active_knows_false_swipe=True, false_swipe_move_index=2,
                                   opponent_is_statused=True, opponent_hp_fraction=0.01,
                                   party_weakener_index=0))
    assert act == ("ball", None)


def test_safe_chip_when_no_false_swipe_and_hp_high():
    act = choose_catch_action(view(opponent_is_statused=True, opponent_hp_fraction=0.9,
                                   safe_chip_move_index=1, party_weakener_index=0))
    assert act == ("move", 1)


def test_ball_at_low_hp_without_false_swipe():
    act = choose_catch_action(view(opponent_is_statused=True, opponent_hp_fraction=0.2,
                                   safe_chip_move_index=1, party_weakener_index=0))
    assert act == ("ball", None)
