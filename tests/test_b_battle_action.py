"""Sub-project B1: the pure trainer/gym battle-action brain (no emulator)."""

from dexbot.battle import BattleView, choose_battle_action


def view(**kw):
    base = dict(
        active_index=0,
        active_hp_fraction=1.0,
        best_move_index=1,
        at_type_disadvantage=False,
        better_matchup_index=None,
        has_potion=False,
    )
    base.update(kw)
    return BattleView(**base)


def test_potion_at_low_hp():
    assert choose_battle_action(view(active_hp_fraction=0.2, has_potion=True)) == ("item", None)


def test_no_potion_low_hp_fights_on():
    # no potion in bag → can't heal; fall through to best move (trainers can't flee)
    assert choose_battle_action(view(active_hp_fraction=0.2, has_potion=False)) == ("move", 1)


def test_rotate_on_type_disadvantage():
    act = choose_battle_action(view(at_type_disadvantage=True, better_matchup_index=3))
    assert act == ("rotate", 3)


def test_no_rotate_without_better_matchup():
    act = choose_battle_action(view(at_type_disadvantage=True, better_matchup_index=None))
    assert act == ("move", 1)  # nobody better — just attack


def test_no_rotate_to_self():
    act = choose_battle_action(view(at_type_disadvantage=True, better_matchup_index=0))
    assert act == ("move", 1)


def test_best_move_default():
    assert choose_battle_action(view(best_move_index=2)) == ("move", 2)


def test_move_zero_fallback_when_no_scored_move():
    assert choose_battle_action(view(best_move_index=None)) == ("move", 0)


def test_potion_beats_rotate_priority():
    # critically low + disadvantaged + potion → heal first (survive the turn)
    act = choose_battle_action(view(active_hp_fraction=0.1, has_potion=True,
                                    at_type_disadvantage=True, better_matchup_index=2))
    assert act == ("item", None)
