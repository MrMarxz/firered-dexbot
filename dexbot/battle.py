"""M7/B1: trainer & gym battle brain — type-aware switching + potions.

A solo overlevelled lead loses gyms on the first faint (the Koga whiteout). This
adds a pure decision function used by the gym/trainer battle strategy: heal when
low, switch out of a bad type matchup to a benched mon that fares better, else
hit hardest. The pure core is unit-tested; the adapter (built at implementation)
maps a live BattleState → BattleView → upstream TurnAction, reusing
BattleStrategyUtil for damage/type math (no reinventing the type chart).
"""

from dataclasses import dataclass

# Heal when the active mon's HP fraction is at/below this and a potion is in bag.
POTION_HP_THRESHOLD = 0.25


@dataclass(frozen=True)
class BattleView:
    active_index: int
    active_hp_fraction: float
    best_move_index: int | None  # highest expected-damage usable move, or None
    at_type_disadvantage: bool  # active takes super-effective and/or deals resisted
    better_matchup_index: int | None  # party index of a conscious mon with a better matchup
    has_potion: bool


def choose_battle_action(v: BattleView) -> tuple[str, int | None]:
    """Pure trainer/gym policy. Returns one of:
    ("item", None) use a potion | ("rotate", party_index) | ("move", move_index).

    Precedence: survive (heal) → improve the matchup (switch) → deal damage.
    Trainers can't be fled, so there is no flee branch; the ("move", 0) fallback
    covers a mon with no scored move (e.g. only status/struggle)."""
    if v.active_hp_fraction <= POTION_HP_THRESHOLD and v.has_potion:
        return ("item", None)
    if v.at_type_disadvantage and v.better_matchup_index is not None and v.better_matchup_index != v.active_index:
        return ("rotate", v.better_matchup_index)
    if v.best_move_index is not None:
        return ("move", v.best_move_index)
    return ("move", 0)
