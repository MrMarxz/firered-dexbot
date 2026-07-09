"""Sub-project A Task 2: select_party — pure, no emulator."""

from dexbot.team import RosterMon, TeamObjective, select_party


def mon(name, dex, level, types, moves, loc="box:0:0"):
    return RosterMon(bytes([dex % 256, dex // 256, 0, 0]), loc, name, dex, level, tuple(types), tuple(moves))


def _catch(**kw):
    return TeamObjective(kind="catch", field_moves=("Cut",), **kw)


def test_hm_mule_always_kept():
    roster = [
        mon("Blastoise", 9, 53, ["Water"], ["Tackle"], "party"),
        mon("Paras", 46, 11, ["Bug", "Grass"], ["Cut", "Stun Spore"], "party"),
        mon("Snorlax", 143, 30, ["Normal"], ["Body Slam"]),
    ]
    picked = select_party(_catch(), roster)
    assert any("Cut" in m.moves for m in picked)


def test_catch_kit_guarantees_sleep_and_false_swipe_roles():
    roster = [
        mon("Blastoise", 9, 53, ["Water"], ["Tackle"], "party"),
        mon("Paras", 46, 11, ["Bug", "Grass"], ["Cut", "Stun Spore"], "party"),
        mon("Gloom", 44, 28, ["Grass", "Poison"], ["Sleep Powder", "Absorb"]),
        mon("Cubone", 104, 15, ["Ground"], ["Bone Club"]),
        mon("Pidgey", 16, 4, ["Normal", "Flying"], ["Tackle"]),
        mon("Rattata", 19, 3, ["Normal"], ["Tackle"]),
        mon("Voltorb", 100, 16, ["Electric"], ["Thunder Wave"]),
    ]
    picked = select_party(_catch(), roster)
    names = {m.species_name for m in picked}
    assert len(picked) <= 6
    assert "Gloom" in names  # sleep user
    assert "Cubone" in names  # False Swipe learner
    assert "Paras" in names  # Cut mule


def test_type_diversity_prefers_spread():
    roster = [
        mon("Blastoise", 9, 53, ["Water"], ["Tackle"], "party"),
        mon("Rattata", 19, 20, ["Normal"], ["Tackle"]),
        mon("Raticate", 20, 22, ["Normal"], ["Tackle"]),
        mon("Pidgey", 16, 18, ["Normal", "Flying"], ["Tackle"]),
        mon("Meowth", 52, 16, ["Normal"], ["Scratch"]),
        mon("Spearow", 21, 14, ["Normal", "Flying"], ["Peck"]),
        mon("Doduo", 84, 12, ["Normal", "Flying"], ["Peck"]),
    ]
    picked = select_party(TeamObjective(kind="travel"), roster)
    assert "Blastoise" in {m.species_name for m in picked}  # lone Water survives the Normal flood


def test_deterministic():
    roster = [
        mon("Blastoise", 9, 53, ["Water"], ["Tackle"], "party"),
        mon("Gloom", 44, 28, ["Grass", "Poison"], ["Sleep Powder"]),
        mon("Cubone", 104, 15, ["Ground"], ["Bone Club"]),
        mon("Voltorb", 100, 16, ["Electric"], ["Thunder Wave"]),
    ]
    assert select_party(_catch(), roster) == select_party(_catch(), list(reversed(roster)))
