# Sub-project B — Battle team & gym progression

**Date:** 2026-07-09
**Status:** design (spec) — implementation to follow incrementally
**Part of:** the integrated team-management program (A → C → B). A stocks the
team; C makes catching safe/optimal; **B** makes the team win battles and drives
story gyms so the dex queue keeps refilling. This spec covers **B**.

## Problem

The bot fights gyms with a solo overlevelled Blastoise (+ a fragile L11 mule).
One faint = whiteout (the Koga loss, 2026-07-09). There is no type-aware
switching, no potion/revive use beyond a blunt heal-strategy, no team leveling,
and the living-dex loop (`run.py` → `plan_and_catch_all`) only *catches* — it
never advances the story, so once the reachable dex is exhausted (dex 41, badge
4) the run idles forever. Progress needs the next gym (Koga → Soul Badge →
**Surf**, which reopens most of the water-encounter dex).

## Goals

1. **A battle team that wins gyms**: type-aware lead + mid-battle switching,
   potion/revive use, and a team-wide level floor reached by grinding — using
   the diverse team A assembles (`kind="gym"`), not a solo mon.
2. **Planner drives story**: the loop picks "beat the next needed gym" as an
   objective when catching is blocked, so it progresses instead of idling.
3. **Beat Koga** (the immediate blocker) → Soul Badge → obtain/enable **Surf**.
4. Take over `beat_koga` from the parallel session: capture the missing
   `m7_badge_koga.ss1` fixture so `tests/test_m7_koga.py` goes green.

## Design

### B1 — Type-aware battle brain (pure, unit-tested)
Mirror C's split: a pure `choose_battle_action(view) -> (kind, arg)` where the
view carries the active mon's viable moves with computed damage ranges, the
opponent's types/HP, whether a party member has a better type matchup, and
whether a heal item is warranted. Precedence:
1. Lead/active faint imminent (HP < ~25%) and a potion is in the bag → use it.
2. Active is at a hard type disadvantage (takes super-effective, deals resisted)
   and a benched mon has a favorable matchup → `rotate_lead` to it.
3. Otherwise use the highest-expected-damage move (STAB + type effectiveness via
   the existing `BattleStrategyUtil.calculate_move_damage_range`).
Reuse the type chart / damage calc already in upstream; do not reinvent.

This extends/*replaces* `make_healing_battle_strategy` (which only drinks
potions or flees). Trainers can't be fled, so for gyms the flee branch is
dropped in favor of switch-or-fight.

### B2 — Team leveling to a floor
`ensure_team_level(target)` in the planner: grind (existing `grind_levels`)
until the assembled team's *battlers* (not HM mules / low-level weakeners) reach
`target`. Target = next gym's ace level + a buffer (Koga's ace Weezing is L43 →
floor ~46), read from `data/trainers.json` (KB) — never guessed. XP spreads by
rotating the lead / using Exp. Share if owned. This is also where **Cubone is
levelled to 33** for False Swipe (feeds C).

### B3 — Planner story objective
When `missing_catchable()` is empty but story gates remain, the planner selects
"beat the next gym in the dependency graph" (from `data/dependencies.json`
objectives), assembles the gym team (`assemble_party(kind="gym", ...)` with the
gym's type hints), ensures the level floor, and runs the gym skill. On success
the graph advances and catching resumes with the newly opened maps.

### B4 — Beat Koga + Surf
Run `beat_koga` with the B1 battle brain and a levelled type-diverse team
(Koga = Poison → bring Ground/Psychic/strong physical; avoid frail leads).
Capture `m7_badge_koga.ss1` at the win for the peer's test. Then the Surf HM:
obtain HM03 (Safari Zone Secret House per KB — verify location/flag against
Bulbapedia/pret at implementation) and enable it (Soul Badge gates Surf use).

## Sources of truth (verify at implementation, don't guess)
- Koga's party + ace level, gym trainer parties → `data/trainers.json`.
- Type chart / damage → upstream `BattleStrategyUtil`.
- Surf HM location + badge gate → Bulbapedia / pret map scripts.
- Gym map layouts (Fuchsia teleporter puzzle) → live probe (`scripts/probe_maze.py`) + pret.

## Testing
- **B1 unit**: pure `choose_battle_action` branch tests (potion at low HP;
  rotate on type disadvantage; best-damage move otherwise) — no emulator.
- **B2 unit**: `_team_battlers` / floor logic on synthetic parties.
- **B4 integration**: `test_m7_koga.py` green from the captured fixture; a
  from-checkpoint run of `beat_koga` wins unattended.
- Full suite green.

## Out of scope
Later gyms (Sabrina/Blaine/Giovanni) reuse this machinery once Koga proves it;
Safari Zone bait/rock catching remains its own M8 mechanic.

## Build order
B1 (battle brain) → B2 (leveling) → B4 (Koga + Surf, the payoff) → B3 (planner
auto-drives future gyms). B3 last because Koga can be driven manually once B1/B2
exist, and auto-driving is the generalization.
