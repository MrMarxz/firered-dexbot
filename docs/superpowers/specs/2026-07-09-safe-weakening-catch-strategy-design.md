# Sub-project C — Safe weakening & status (catch strategy)

**Date:** 2026-07-09
**Status:** design approved (program-level), spec for implementation
**Part of:** the integrated team-management program (A → C → B). A stocks the
diverse catch team; **C** makes the catch battle optimal and safe; B levels the
core battlers and drives gyms. This spec covers **C only**.

## Problem

Catching wastes balls and risks KOing the target (a KO loses the catch). The
current `WeakeningCatchStrategy` chips only with the *active* mon and only when
the target is above 40% HP, so an overlevelled Blastoise lead — which has no
non-KO move against a low-level wild — throws at full HP. It never uses the
diverse team A now provides, and never uses False Swipe.

## What upstream already does (build on it, don't reinvent)

`modules/battle_strategies/catch.CatchStrategy.decide_turn` already:
- picks the best Poké Ball in the bag;
- if the target is un-statused and the 1-turn catch chance < 50%, uses the best
  status move via `_get_best_status_changing_move`, which **prefers Sleep (×2)
  over Paralysis (×1.5), weights by accuracy, and respects Insomnia / Vital
  Spirit / Limber**;
- re-applies status once the target wakes (`status_permanent == Healthy`);
- otherwise throws the ball.

**Fact correction (verified):** Grass-types are **not** immune to powder moves
in Gen III (that immunity is Gen VI+), so Sleep Powder works on everything in
FireRed subject to accuracy/ability. No Grass special-casing is needed.

## The gaps C closes

1. **Use the appropriate weakener.** If the active mon is not the best available
   weakener and a conscious benched one is, `rotate_lead(index)` to it (turn
   cost is fine for catching). Priority of "best weakener": a **False Swipe
   user** > a **sleep-move user** > a **low-level safe chipper**. This lets
   Blastoise lead treks (survives trainers) while Cubone/Gloom does the catch.
2. **False Swipe to 1 HP.** When the active mon knows False Swipe and the target
   is above 1 HP, use False Swipe — guaranteed never to KO, maximizing the HP
   term (~×3) safely. (Damaging moves do not wake a sleeping target in Gen III,
   so Sleep-then-False-Swipe is safe.)
3. **Optimal ordering** per turn (once the weakener is active): inflict **Sleep**
   first (if un-statused and it helps), then **False Swipe** to 1 HP, then throw.
   Keep the existing **safe non-KO chip** (max damage whose worst-case crit
   can't KO) for mons without False Swipe.

## Design — `dexbot/catching.py`

Split the decision into a **pure brain** + a thin **Strategy adapter** so the
logic is unit-testable without the emulator.

### Pure decision function
```python
@dataclass(frozen=True)
class CatchView:
    active_index: int
    active_moves: tuple[str, ...]        # move names of the active battler
    active_knows_false_swipe: bool
    party_weakener_index: int | None     # best benched weakener's party index, or None
    opponent_hp_fraction: float
    opponent_is_statused: bool
    one_turn_catch_chance: float
    safe_chip_move_index: int | None     # highest non-KO damaging move, or None
    status_move_index: int | None        # from upstream's picker, or None
    false_swipe_move_index: int | None

def choose_catch_action(v: CatchView) -> tuple[str, int | None]:
    # returns one of:
    #   ("rotate", party_index)   switch to the weakener
    #   ("move", move_index)      status / false_swipe / safe_chip
    #   ("ball", None)            throw
```
Precedence:
1. If `one_turn_catch_chance >= 0.5` → `("ball", None)` (good enough; don't waste turns).
2. If active isn't a weakener and `party_weakener_index` is not None and differs
   → `("rotate", party_weakener_index)`.
3. If `not opponent_is_statused` and `status_move_index is not None`
   → `("move", status_move_index)` (sleep-preferred, from upstream picker).
4. If `active_knows_false_swipe` and `opponent_hp_fraction` above the 1-HP floor
   and `false_swipe_move_index is not None` → `("move", false_swipe_move_index)`.
5. If `opponent_hp_fraction > 0.5` and `safe_chip_move_index is not None`
   → `("move", safe_chip_move_index)`.
6. Else → `("ball", None)`.

### Strategy adapter
`WeakeningCatchStrategy.decide_turn` builds a `CatchView` from `battle_state`
(reusing upstream `_get_best_status_changing_move`, `calculate_catch_success_chance`,
`_get_best_poke_ball`, and `BattleStrategyUtil.calculate_move_damage_range` for
the safe-chip guard, exactly as the current code does), determines the benched
weakener index by scanning `battle_state.own_side` / party for False-Swipe /
sleep / low-level chipper, calls `choose_catch_action`, and maps the result to
`TurnAction.rotate_lead` / `use_move` / falls through to `super().decide_turn()`
for the ball throw (so ball selection stays upstream's).

"Knows False Swipe / is a weakener" reuses `team.SLEEP_MOVES` and a False-Swipe
check on actual known moves (not the learner set — in battle only *known* moves
matter; Cubone must have reached L33).

## Integration

`make_catch_decider(species)` already returns `WeakeningCatchStrategy()` for the
target and `RunAway` for other wilds — unchanged. Only the strategy's internal
decision changes.

**Ball economy — DEFERRED follow-up (not in C's core):** switching the default
restock from Great Balls (×1.5) to **Ultra Balls** (×2) needs verifying which
marts stock Ultra Balls at the current badge stage and that `buy_items`
degrades gracefully if an item is unstocked (else a shop-menu stall). Implement
as a preference ladder Ultra→Great→Poké with a stock check. Marginal gain vs.
stall risk, so it ships after the core rotate/False-Swipe/status work. Upstream's
`_get_best_poke_ball` already throws whatever best ball is in the bag, so this is
purely a purchasing change.

## Out of scope (→ B)

Trainer/gym battle switching, potion/revive policy, and leveling the weakener
(Cubone → L33 for False Swipe). Until Cubone is L33, C uses sleep + safe-chip
(the False Swipe branch simply doesn't fire), degrading gracefully.

## Testing

- **Unit** (`test_c_catch_action.py`, pure, no emulator): each precedence branch
  — rotate when active lacks a weakener move and bench has one; ball when odds
  ≥ 50%; status before False Swipe; False Swipe above 1 HP; safe chip when no
  False Swipe and HP high; ball at low HP.
- **Live smoke** (`test_c_weaken_live.py`): from a fixture, trigger a wild
  encounter of an already-owned species and run a catch with the new strategy;
  assert the target is **caught** and was **statused or below full HP** before
  capture (never fainted). Fixture captured on a grassy route.
- Full suite green.

## Success criteria

Against a wild target, the bot rotates to the best weakener, applies sleep,
False-Swipes to ~1 HP when able (else safe-chips), and catches with Ultra Balls
— no accidental KO. Verified live; unit tests cover every precedence branch.
