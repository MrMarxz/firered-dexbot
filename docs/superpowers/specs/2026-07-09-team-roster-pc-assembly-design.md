# Sub-project A — Team roster & PC assembly

**Date:** 2026-07-09
**Status:** design approved, spec under review
**Part of:** the integrated team-management program (A → C → B). A stocks a
diverse party from the PC; C (safe weakening & status) picks the gentle hitter
off it when catching; B (battle team & gym progression) levels the core
battlers and drives gyms. This spec covers **A only**.

## Problem

The planner deposits everything except the single strongest party member
(`deposit_party_fodder(keep=1)`, kept only for HM mules). The bot therefore
fights and catches with a solo L53 Blastoise plus a L11 Cut mule. Two failures
follow directly:

- **Catching wastes balls / risks KO** — an overleveled lead has no move that
  chips a low-level wild target without threatening a knockout, so it throws at
  full HP and burns balls (a dead target loses the catch entirely).
- **Gyms are lost on the first faint** — with no real second battler, one
  Blastoise faint sends out the L11 mule, which dies instantly (the Koga
  whiteout, 2026-07-09).

We own 40 species, but only Blastoise is trained; the rest sit in boxes at
capture level (L3–29). The raw material for a diverse team exists; nothing
assembles it.

## Goal

A skill that, given the current objective, assembles the best available ≤6-mon
party from party + PC boxes: mandatory HM-mule holders, then the highest
battle-viability mons under a type-diversity constraint, and — for catch
objectives — at least one status/False-Swipe holder aboard. This replaces the
"deposit down to one" behavior.

**Explicitly out of scope for A** (owned by later sub-projects):
- Leveling under-levelled members → **B**.
- Choosing which party member/move to use in a catch battle → **C**.
- In-battle switching / potion use for gyms → **B**.

**Outstanding follow-ups this investigation surfaced** (not A's code, but
recorded so they aren't lost):
- **C's per-turn policy** (its own spec): Sleep if catchable-and-unstatused
  (re-apply on wake) → else non-powder Paralysis → chip to low HP under the
  no-KO damage-range guard → throw. Handle powder-immune Grass targets and
  fleers (sleep before they flee).
- **Ball economy:** switch the default restock purchase from Great Balls to
  **Ultra Balls** (×2 vs ×1.5) once affordable — a one-line change in
  `restock_pokeballs_if_low`, to land with C.
- **False Swipe acquisition = level our Cubone to 33** (B's leveling job): it
  learns False Swipe by level-up (Marowak L39), no breeding/TM/trade. Scyther
  (Safari, False Swipe @ L16) is a backup/upgrade caught for the dex anyway.
  No move-*teaching* skill is needed — the sleep/paralysis moves are already
  known by owned mons, and False Swipe comes from Cubone's natural level-up.
- **Safari Zone** species use bait/rock + Safari Balls with no weakening — a
  separate M8 mechanic, untouched here.

A only decides *who is in the party* and physically realizes it at a PC. It is
correct for A to leave the party under-levelled; C benefits from low-level
members (safe weakeners) and B raises the core battlers.

## The objective interface

```python
@dataclass(frozen=True)
class TeamObjective:
    kind: str                     # "catch" | "gym" | "travel"
    field_moves: tuple[str, ...]  # HM field moves the route needs (e.g. ("Cut",))
    prefer_offense_types: tuple[str, ...] = ()  # types strong to bring (gym: what beats its type)
    avoid_defense_types: tuple[str, ...] = ()   # types to resist (gym: its attacking type)
```

Callers build this cheaply from data they already have:
- **catch**: `field_moves` from the route's dependency annotation; no type bias.
- **gym**: `prefer_offense_types` / `avoid_defense_types` from the gym's type
  (a small static map, e.g. Koga=Poison → prefer Ground/Psychic, avoid Poison).
- **travel/default**: just `field_moves`; balanced diversity otherwise.

## Components — `dexbot/team.py`

### `enumerate_roster() -> list[RosterMon]`
All owned individuals across party and PC boxes. Party from `get_party()`; boxes
from `get_pokemon_storage().boxes[i].slots` (confirmed present). Each `RosterMon`
carries: a stable identity (`bytes(data[:4])`), location (`"party"` | `(box,
slot)`), species name, level, type tuple, known move names, and
`is_hm_mule(field_moves)`. Pure read; advances no frames.

### `select_party(objective, roster) -> list[RosterMon]`
Pure function (no emulator), unit-testable. Policy, in order:
1. **Mandatory:** every holder of a move in `objective.field_moves` (all of
   them — HM access must never be deposited away). If mandatory > 6, keep the
   highest-level holder per distinct field move.
2. **Fill remaining slots** by descending viability score, subject to a
   diversity rule: don't add a mon whose primary type is already represented
   twice, unless nothing else remains. Viability = `level * evolution_stage`
   (stage from species data; ties broken by level then dex number for
   determinism — never by wall-clock/RNG).
3. **Catch-rate-optimized kit** (the point of a catch team, per the Gen III
   math — HP ×~3 at 1 HP, sleep ×2, Ultra Ball ×2, all multiplicative). For
   `kind == "catch"`, guarantee these roles are aboard, adding the best roster
   mon for each missing role (displacing the lowest-viability non-mandatory
   fill):
   - **A sleep user** (×2, the strongest status) — Sleep Powder / Hypnosis /
     Sing / Spore, preferring higher accuracy (Spore 100 > Sleep Powder 75 >
     Hypnosis 60 > Sing 55). We already own several (Gloom knows Sleep Powder).
   - **A non-powder status backup** — Thunder Wave (paralysis ×1.5) for targets
     immune to powder moves (Grass-types resist Sleep Powder/Stun Spore).
     Owned learners exist (Pikachu, Voltorb).
   - **A False Swipe user** — the ideal safe weakener: False Swipe always
     leaves the target at exactly 1 HP, never KOs, maximizing the HP term
     (~×3) with zero risk. It is **not a Gen III TM**, but **Cubone learns it
     by level-up at L33 (Marowak L39)** — and we already own a Cubone (L15,
     boxed). A keeps that Cubone on the catch bench; B levels it to ≥33 so it
     learns the move. (Backup/upgrade: **Scyther** learns False Swipe at L16
     and is a Safari-Zone catch we need for the dex anyway.)
   - **A low-level safe chipper** — fallback for before Cubone reaches L33, for
     Ghost targets (False Swipe is Normal, no effect on Ghost), and for
     powder-immune cases: a weak neutral attacker that chips as low as the
     damage-range guard allows without a KO. A deliberately-low-level mon is
     the safest chipper — another reason A keeps some under-levelled mons on
     the bench.
   (C consumes these; A only guarantees the roles are present. The kit
   degrades gracefully: full power once Cubone knows False Swipe and a sleeper
   is aboard; sleep + safe-chip until then.)
4. Return ≤6, order irrelevant (the game auto-orders; C/B choose the active mon).

### `assemble_party(objective) -> Generator`
Realize `select_party` at the nearest reachable PC:
1. `ensure` we're at a PC — reuse `_pick_reachable_center` + `navigate_to`, then
   walk to the PC tile (existing `_find_pc_tile` in `boxes.py`).
2. Diff current party vs target. Deposit party mons not in target
   (`PCAction.deposit_pokemon_to_box`), withdraw target mons in boxes
   (`PCAction.withdraw_pokemon_from_box`).
3. **Ordering constraint:** never drop below one conscious, HM-capable mon
   mid-swap, and never overflow 6 — deposit surplus before withdrawing. One
   `interact_with_pc` batch is fragile across a shrinking party (see the
   existing note in `boxes.py`); do withdrawals/deposits as discrete PC
   interactions, re-reading storage between them, and `state_cache.reset()`
   after because party shape changed outside battle.
4. Assert the resulting party equals the target identity set; raise `SkillError`
   otherwise (feeds the standard defer/retry).

## Integration

`dexbot/planner.py`: replace the post-catch
`deposit_party_fodder(keep=1)` block with
`assemble_party(TeamObjective(kind="catch", field_moves=<route mules>))` before
each catch route. `deposit_party_fodder` stays as the primitive
`assemble_party` builds on (or is subsumed — decide in the plan). Gym callers in
`gyms.py`/planner pass `kind="gym"` with the type hints; wiring the gym driver
itself is **B**, so for A the gym path is just the new function available for B
to call.

## Error handling & edge cases

- **No PC reachable** — reuse C's just-landed fix: step out of a pocket, retry;
  else `SkillError` (deferred by the planner).
- **Box full on deposit** — FRLG auto-advances boxes; if truly full, keep the
  mon in party and log (we are far from 14×30 capacity).
- **Target unchanged** — no-op fast return (don't walk to a PC to do nothing).
- **Mandatory HM holder is the only mon** — never deposit it; party may stay
  smaller than ideal.

## Testing

- **`select_party` unit tests** (pure, no emulator): solo→diverse fill; HM mule
  always kept; diversity cap respected; catch-objective status guarantee;
  determinism (same roster → same selection).
- **`assemble_party` integration test** from a fixture where the party is
  solo-Blastoise and boxes hold diverse mons: run headless, assert the resulting
  party matches `select_party`'s plan and still contains the Cut mule. New
  fixture captured during a play-through, documented in `fixtures/`.
- Full suite stays green (`.venv/bin/python -m pytest tests/ -q`).

## Success criteria

From the current live save (solo Blastoise + Cut mule, boxes full of L3–29
dex mons), `assemble_party(TeamObjective(kind="catch", field_moves=("Cut",)))`
produces a 6-mon party that keeps the Cut mule, spans ≥4 distinct types, and
includes a status/False-Swipe holder — verified headless, suite green.
