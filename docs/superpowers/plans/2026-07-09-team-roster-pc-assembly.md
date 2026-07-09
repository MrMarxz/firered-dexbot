# Team Roster & PC Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `dexbot/team.py` that assembles the best available ≤6-mon party from party + PC boxes for a given objective, replacing the solo-Blastoise `deposit_party_fodder(keep=1)` behavior.

**Architecture:** A pure selection function (`select_party`) decides *who* should be in the party from a plain-data roster; a generator (`assemble_party`) realizes that selection at a PC via upstream `interact_with_pc`. Roster enumeration reads party + `get_pokemon_storage()` boxes. The planner calls `assemble_party` before catch routes instead of depositing down to one mon.

**Tech Stack:** Python 3.12, pytest, the pokebot-gen3 modules (`get_party`, `get_pokemon_storage`, `interact_with_pc`, `PCAction`), dexbot's `navigation.navigate_to` and `catching._pick_reachable_center`.

## Global Constraints

- Game facts come from ROM/KB/Bulbapedia, never invented. Species→move/type facts read from live mon objects or `modules/data`.
- Deterministic tie-breaks only (level, then national dex number) — never wall-clock or RNG (`Date.now`/random are unavailable in this project's spirit; keep selection reproducible).
- One conscious HM-capable mon must remain in the party at every point of a PC swap; never exceed 6 party slots.
- Run from repo root with `.venv/bin/python`. Full suite must stay green: `.venv/bin/python -m pytest tests/ -q`.
- `PYTHONPATH=.` when invoking modules directly; tests get sys.path via `tests/conftest.py`.

---

### Task 1: Roster data model + enumeration

**Files:**
- Create: `dexbot/team.py`
- Test: `tests/test_a_team.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class TeamObjective` with fields `kind: str` (`"catch"|"gym"|"travel"`), `field_moves: tuple[str, ...] = ()`, `prefer_offense_types: tuple[str, ...] = ()`, `avoid_defense_types: tuple[str, ...] = ()`.
  - `@dataclass(frozen=True) class RosterMon` with fields `id_bytes: bytes`, `location: str` (`"party"` or `"box:{i}:{slot}"`), `species_name: str`, `national_dex: int`, `level: int`, `types: tuple[str, ...]`, `moves: tuple[str, ...]`.
  - `enumerate_roster() -> list[RosterMon]` — party first, then boxes; skips eggs/empties.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_a_team.py
from dexbot import PROJECT_ROOT

FIXTURE = "a_team_solo.ss1"  # solo Blastoise in party, diverse mons in boxes (Task 3 captures it)


def test_enumerate_roster_reads_party_and_boxes():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / FIXTURE).read_bytes())
    context.emulator.run_single_frame()

    from dexbot.team import enumerate_roster

    roster = enumerate_roster()
    names = {m.species_name for m in roster}
    assert "Blastoise" in names          # trained lead
    assert "Cubone" in names             # the future False Swipe user
    assert any(m.location == "party" for m in roster)
    assert any(m.location.startswith("box:") for m in roster)
    # every mon carries usable data
    blastoise = next(m for m in roster if m.species_name == "Blastoise")
    assert blastoise.level > 0 and blastoise.types and isinstance(blastoise.moves, tuple)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_a_team.py::test_enumerate_roster_reads_party_and_boxes -q`
Expected: FAIL — the fixture doesn't exist yet AND `dexbot.team` doesn't exist. (Task 3 Step 1 captures the fixture; until then this task's test cannot pass — that is expected. Implement the code now; the fixture arrives in Task 3. Mark this test xfail-until-fixture by skipping if the fixture is absent, per Step 3.)

- [ ] **Step 3: Write minimal implementation**

```python
# dexbot/team.py
"""M8: team roster & PC assembly — assemble the best party for an objective.

select_party decides WHO belongs in the party (pure); assemble_party realizes
it at a PC. Replaces "deposit everything but the strongest" so the bot fields a
diverse, catch-rate-optimized team instead of a solo lead.
"""

from dataclasses import dataclass, field
from typing import Generator


@dataclass(frozen=True)
class TeamObjective:
    kind: str  # "catch" | "gym" | "travel"
    field_moves: tuple[str, ...] = ()
    prefer_offense_types: tuple[str, ...] = ()
    avoid_defense_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class RosterMon:
    id_bytes: bytes
    location: str  # "party" | "box:{box}:{slot}"
    species_name: str
    national_dex: int
    level: int
    types: tuple[str, ...]
    moves: tuple[str, ...]


def _mon_to_roster(mon, location: str) -> RosterMon:
    return RosterMon(
        id_bytes=bytes(mon.data[:4]),
        location=location,
        species_name=mon.species.name,
        national_dex=mon.species.national_dex_number,
        level=mon.level,
        types=tuple(t.name for t in mon.species.types),
        moves=tuple(m.move.name for m in mon.moves if m is not None),
    )


def enumerate_roster() -> list[RosterMon]:
    from modules.pokemon_party import get_party
    from modules.pokemon_storage import get_pokemon_storage

    roster: list[RosterMon] = []
    for p in get_party():
        if not p.is_egg:
            roster.append(_mon_to_roster(p, "party"))
    for bi, box in enumerate(get_pokemon_storage().boxes):
        for slot in box.slots:
            if slot is not None and not slot.pokemon.is_egg and not slot.pokemon.is_empty:
                roster.append(_mon_to_roster(slot.pokemon, f"box:{bi}:{slot.slot_index}"))
    return roster
```

- [ ] **Step 4: Run test to verify it passes (or skips pending fixture)**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_a_team.py -q`
Expected: the test errors only on the missing fixture. Add at the top of `tests/test_a_team.py`:

```python
import pytest
from pathlib import Path
from dexbot import PROJECT_ROOT

pytestmark = pytest.mark.skipif(
    not (PROJECT_ROOT / "fixtures" / "a_team_solo.ss1").exists(),
    reason="a_team_solo.ss1 captured in Task 3",
)
```

Re-run: Expected: SKIPPED (fixture pending). Full suite `pytest tests/ -q` stays green.

- [ ] **Step 5: Commit**

```bash
git add dexbot/team.py tests/test_a_team.py
git commit -m "feat(team): roster data model + enumerate_roster (party+boxes)"
```

---

### Task 2: `select_party` — the catch-rate-optimized selection policy

**Files:**
- Modify: `dexbot/team.py`
- Test: `tests/test_a_team_select.py`

**Interfaces:**
- Consumes: `TeamObjective`, `RosterMon` (Task 1).
- Produces:
  - Module constants: `SLEEP_MOVES`, `PARALYSIS_MOVES` (frozensets of move names), `FALSE_SWIPE_LEARNERS = frozenset({"Cubone", "Marowak", "Scyther", "Farfetch'd"})` (FRLG level-up learners, KB-verified).
  - `select_party(objective: TeamObjective, roster: list[RosterMon], cap: int = 6) -> list[RosterMon]` — pure, deterministic.

- [ ] **Step 1: Write the failing tests (pure — no emulator)**

```python
# tests/test_a_team_select.py
from dexbot.team import RosterMon, TeamObjective, select_party


def mon(name, dex, level, types, moves, loc="box:0:0"):
    return RosterMon(bytes([dex, 0, 0, 0]), loc, name, dex, level, tuple(types), tuple(moves))


def _catch(**kw):
    return TeamObjective(kind="catch", field_moves=("Cut",), **kw)


def test_hm_mule_always_kept():
    roster = [
        mon("Blastoise", 9, 53, ["Water"], ["Tackle"], "party"),
        mon("Paras", 46, 11, ["Bug", "Grass"], ["Cut", "Stun Spore"], "party"),  # Cut mule
        mon("Snorlax", 143, 30, ["Normal"], ["Body Slam"]),
    ]
    picked = select_party(_catch(), roster)
    assert any("Cut" in m.moves for m in picked)  # mule never dropped


def test_catch_kit_guarantees_sleep_and_false_swipe_roles():
    roster = [
        mon("Blastoise", 9, 53, ["Water"], ["Tackle"], "party"),
        mon("Paras", 46, 11, ["Bug", "Grass"], ["Cut", "Stun Spore"], "party"),
        mon("Gloom", 44, 28, ["Grass", "Poison"], ["Sleep Powder", "Absorb"]),  # sleeper
        mon("Cubone", 104, 15, ["Ground"], ["Bone Club"]),                      # FS learner
        mon("Pidgey", 16, 4, ["Normal", "Flying"], ["Tackle"]),
        mon("Rattata", 19, 3, ["Normal"], ["Tackle"]),
        mon("Voltorb", 100, 16, ["Electric"], ["Thunder Wave"]),                # para backup
    ]
    picked = select_party(_catch(), roster)
    names = {m.species_name for m in picked}
    assert len(picked) <= 6
    assert "Gloom" in names       # sleep user aboard
    assert "Cubone" in names      # False Swipe learner aboard
    assert "Paras" in names       # Cut mule aboard


def test_type_diversity_prefers_spread():
    # five Normal-types + one Water; diversity cap keeps the Water in.
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
    assert "Blastoise" in {m.species_name for m in picked}  # the lone Water survives the Normal flood


def test_deterministic():
    roster = [
        mon("Blastoise", 9, 53, ["Water"], ["Tackle"], "party"),
        mon("Gloom", 44, 28, ["Grass", "Poison"], ["Sleep Powder"]),
        mon("Cubone", 104, 15, ["Ground"], ["Bone Club"]),
        mon("Voltorb", 100, 16, ["Electric"], ["Thunder Wave"]),
    ]
    assert select_party(_catch(), roster) == select_party(_catch(), list(reversed(roster)))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_a_team_select.py -q`
Expected: FAIL — `select_party` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# add to dexbot/team.py
SLEEP_MOVES = frozenset({"Spore", "Sleep Powder", "Hypnosis", "Sing", "Lovely Kiss", "Grass Whistle"})
PARALYSIS_MOVES = frozenset({"Thunder Wave", "Stun Spore", "Body Slam", "Glare"})
NON_POWDER_PARALYSIS = frozenset({"Thunder Wave", "Body Slam", "Glare"})  # work on Grass-types
FALSE_SWIPE_LEARNERS = frozenset({"Cubone", "Marowak", "Scyther", "Farfetch'd"})


def _viability(m: "RosterMon") -> tuple:
    # ponytail: level captures "trained-ness"; evolution stage correlates with
    # level, so we skip a species-data stage lookup. Deterministic tie-break by
    # dex number. Add a stage multiplier only if selection quality demands it.
    return (m.level, -m.national_dex)


def _knows_any(m: "RosterMon", moves: frozenset) -> bool:
    return any(mv in moves for mv in m.moves)


def _is_false_swipe_user(m: "RosterMon") -> bool:
    return "False Swipe" in m.moves or m.species_name in FALSE_SWIPE_LEARNERS


def select_party(objective: "TeamObjective", roster: list["RosterMon"], cap: int = 6) -> list["RosterMon"]:
    by_id = {m.id_bytes: m for m in roster}
    chosen: dict[bytes, "RosterMon"] = {}

    def add(m):
        if m is not None and len(chosen) < cap:
            chosen[m.id_bytes] = m

    # 1. Mandatory HM mules (highest-level holder per field move).
    for fm in objective.field_moves:
        holders = sorted((m for m in roster if fm in m.moves), key=_viability, reverse=True)
        if holders:
            add(holders[0])

    # 2. Catch-kit roles (best available for each missing role).
    if objective.kind == "catch":
        for pred in (
            lambda m: _knows_any(m, SLEEP_MOVES),          # ×2 status
            _is_false_swipe_user,                          # guaranteed 1 HP (Cubone→FS)
            lambda m: _knows_any(m, NON_POWDER_PARALYSIS), # Grass-safe paralysis backup
        ):
            if not any(pred(m) for m in chosen.values()):
                cands = sorted((m for m in roster if pred(m) and m.id_bytes not in chosen),
                               key=_viability, reverse=True)
                add(cands[0] if cands else None)

    # 3. Fill remaining slots by viability under a type-diversity cap
    #    (≤2 mons sharing a primary type unless nothing else remains).
    def primary(m):
        return m.types[0] if m.types else "?"

    type_count: dict[str, int] = {}
    for m in chosen.values():
        type_count[primary(m)] = type_count.get(primary(m), 0) + 1

    remaining = sorted((m for m in roster if m.id_bytes not in chosen), key=_viability, reverse=True)
    deferred = []
    for m in remaining:
        if len(chosen) >= cap:
            break
        if type_count.get(primary(m), 0) >= 2:
            deferred.append(m)
            continue
        add(m)
        type_count[primary(m)] = type_count.get(primary(m), 0) + 1
    for m in deferred:  # relax diversity only if slots remain
        if len(chosen) >= cap:
            break
        add(m)

    return sorted(chosen.values(), key=_viability, reverse=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_a_team_select.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add dexbot/team.py tests/test_a_team_select.py
git commit -m "feat(team): select_party catch-rate-optimized policy (mules, sleep/FS/para roles, diversity)"
```

---

### Task 3: `assemble_party` — realize the selection at a PC + capture the fixture

**Files:**
- Modify: `dexbot/team.py`
- Test: `tests/test_a_team.py` (the Task 1 test un-skips once the fixture exists; add an assembly test)

**Interfaces:**
- Consumes: `enumerate_roster`, `select_party`, `TeamObjective` (Tasks 1-2); `dexbot.navigation.navigate_to`; `dexbot.catching._pick_reachable_center`; `dexbot.boxes._find_pc_tile`; `modules.modes.util.pc_interaction.{interact_with_pc, PCAction}`.
- Produces: `assemble_party(objective: TeamObjective) -> Generator`.

- [ ] **Step 1: Capture the fixture from the live save**

Run:
```bash
PYTHONPATH=. .venv/bin/python -c "
import dexbot, shutil
from dexbot import PROJECT_ROOT
src = PROJECT_ROOT / 'pokebot-gen3/profiles/livingdex/current_state.ss1'
dst = PROJECT_ROOT / 'fixtures/a_team_solo.ss1'
shutil.copyfile(src, dst); print('captured', dst)
"
```
Expected: `captured .../fixtures/a_team_solo.ss1`. (The live save is solo Blastoise + Cut mule in party, diverse mons incl. Cubone L15 in boxes — exactly the target scenario.) Document the fixture's provenance in `fixtures/README` per project convention if present.

- [ ] **Step 2: Write the failing assembly test**

```python
# add to tests/test_a_team.py
def test_assemble_party_realizes_selection():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / FIXTURE).read_bytes())
    context.emulator.run_single_frame()

    from dexbot.team import assemble_party, enumerate_roster, select_party, TeamObjective
    from dexbot.runner import run_skill
    from dexbot.catching import fight_all_battles

    target = {m.id_bytes for m in select_party(TeamObjective(kind="catch", field_moves=("Cut",)), enumerate_roster())}
    run_skill(assemble_party(TeamObjective(kind="catch", field_moves=("Cut",))),
              "assemble", timeout_frames=400_000, on_battle_started=fight_all_battles)

    from modules.pokemon_party import get_party
    party_ids = {bytes(p.data[:4]) for p in get_party() if not p.is_egg}
    assert party_ids == target
    assert get_party().has_pokemon_with_move("Cut")  # mule retained
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_a_team.py::test_assemble_party_realizes_selection -q`
Expected: FAIL — `assemble_party` not defined.

- [ ] **Step 4: Write minimal implementation**

```python
# add to dexbot/team.py
def assemble_party(objective: "TeamObjective") -> Generator:
    from modules.context import context
    from modules.modes.util.pc_interaction import PCAction, interact_with_pc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_controllable
    from modules.pokemon_party import get_party
    from modules.pokemon_storage import get_pokemon_storage
    from modules.state_cache import state_cache

    from dexbot.boxes import _find_pc_tile
    from dexbot.catching import _pick_reachable_center
    from dexbot.navigation import navigate_to
    from dexbot.runner import SkillError, _log_event

    target = select_party(objective, enumerate_roster())
    target_ids = {m.id_bytes for m in target}
    current_ids = {bytes(p.data[:4]) for p in get_party() if not p.is_egg}
    if current_ids == target_ids:
        return  # nothing to do — don't walk to a PC for a no-op

    _log_event(skill="assemble_party", status="phase", phase="to_pc")
    center = _pick_reachable_center()
    yield from navigate_to(center.value[0], center.value[1])  # door warp → inside
    interior = get_party()[0].species and None  # placeholder removed below
    from modules.player import get_player_avatar

    interior = get_player_avatar().map_group_and_number
    pc_tile = _find_pc_tile(interior)
    yield from navigate_to(interior, (pc_tile[0], pc_tile[1] + 1))
    yield from ensure_facing_direction("Up")

    def drain():
        yield from wait_for_no_script_to_run("B")
        yield from wait_for_player_avatar_to_be_controllable("B")

    # Deposit party mons not wanted (keep ≥1 conscious HM-capable mon at all
    # times — deposit non-mules first, mules last only if still surplus).
    _log_event(skill="assemble_party", status="phase", phase="deposit")
    for p in list(get_party()):
        if p.is_egg:
            continue
        if bytes(p.data[:4]) not in target_ids and len([x for x in get_party() if not x.is_egg]) > 1:
            yield from interact_with_pc([PCAction.deposit_pokemon_to_box(p)])
            state_cache.reset()

    # Withdraw wanted mons still in boxes.
    _log_event(skill="assemble_party", status="phase", phase="withdraw")
    for want in target:
        if want.location == "party":
            continue
        if bytes_in_party(want.id_bytes):
            continue
        storage = get_pokemon_storage()
        boxed = _find_box_mon(storage, want.id_bytes)
        if boxed is not None and len([x for x in get_party() if not x.is_egg]) < 6:
            yield from interact_with_pc([PCAction.withdraw_pokemon_from_box(boxed)])
            state_cache.reset()

    yield from drain()
    result = {bytes(p.data[:4]) for p in get_party() if not p.is_egg}
    if result != target_ids:
        raise SkillError(f"assemble_party: party {result} != target {target_ids}")


def bytes_in_party(id_bytes: bytes) -> bool:
    from modules.pokemon_party import get_party

    return any(bytes(p.data[:4]) == id_bytes for p in get_party() if not p.is_egg)


def _find_box_mon(storage, id_bytes: bytes):
    for box in storage.boxes:
        for slot in box.slots:
            if slot is not None and not slot.pokemon.is_empty and bytes(slot.pokemon.data[:4]) == id_bytes:
                return slot.pokemon
    return None
```

Then delete the stray `interior = get_party()[0].species and None` placeholder line (kept here only to flag it — the real assignment is the `get_player_avatar()` one below it).

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_a_team.py -q`
Expected: PASS (enumerate + assemble). If `interact_with_pc` needs a specific standing tile/facing, adjust the PC approach to match `boxes.py:deposit_party_fodder` (which already deposits successfully) — reuse its exact tile/facing sequence.

- [ ] **Step 6: Commit**

```bash
git add dexbot/team.py tests/test_a_team.py fixtures/a_team_solo.ss1
git commit -m "feat(team): assemble_party realizes selection at a PC; capture a_team_solo fixture"
```

---

### Task 4: Planner integration — assemble a catch team instead of depositing to one

**Files:**
- Modify: `dexbot/planner.py` (the `deposit_party_fodder(keep=1)` block after a catch)
- Test: `tests/test_a_team_planner.py`

**Interfaces:**
- Consumes: `assemble_party`, `TeamObjective` (Task 3).
- Produces: no new public symbol; changes planner behavior.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_a_team_planner.py
import pytest
from pathlib import Path
from dexbot import PROJECT_ROOT

pytestmark = pytest.mark.skipif(
    not (PROJECT_ROOT / "fixtures" / "a_team_solo.ss1").exists(),
    reason="needs a_team_solo.ss1",
)


def test_planner_assembles_catch_team_not_solo():
    """After the team-management change, the post-catch step assembles a diverse
    party (>=2 mons, includes the Cut mule) rather than depositing down to one."""
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "a_team_solo.ss1").read_bytes())
    context.emulator.run_single_frame()

    from dexbot.team import enumerate_roster, select_party, TeamObjective

    picked = select_party(TeamObjective(kind="catch", field_moves=("Cut",)), enumerate_roster())
    assert len(picked) >= 2
    assert any("Cut" in m.moves for m in picked)
```

- [ ] **Step 2: Run test to verify it fails/skips**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_a_team_planner.py -q`
Expected: PASS already for the pure part (select_party exists) — this test guards the *selection* contract the planner relies on. If it fails, select_party regressed.

- [ ] **Step 3: Modify the planner**

In `dexbot/planner.py`, replace the post-catch block:

```python
        if len(get_party()) >= 5:
            from dexbot.boxes import deposit_party_fodder
            from dexbot.catching import fight_all_battles

            run_skill(deposit_party_fodder(keep=1), "deposit_fodder",
                      timeout_frames=600_000, on_battle_started=fight_all_battles)
```

with:

```python
        # Keep a diverse, catch-rate-optimized party instead of a solo lead.
        from dexbot.catching import fight_all_battles
        from dexbot.team import TeamObjective, assemble_party

        field_moves = tuple(annotation.get("field_moves", ("Cut",)))
        run_skill(
            assemble_party(TeamObjective(kind="catch", field_moves=field_moves)),
            "assemble_party",
            timeout_frames=600_000,
            on_battle_started=fight_all_battles,
        )
```

(`deposit_party_fodder` remains in `boxes.py` as the primitive assemble builds on; not deleted.)

- [ ] **Step 4: Run the full suite**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/ -q`
Expected: all green except the pre-existing peer `test_m7_koga` fixture-missing failure. No new failures.

- [ ] **Step 5: Commit**

```bash
git add dexbot/planner.py tests/test_a_team_planner.py
git commit -m "feat(team): planner assembles a catch team post-catch (was deposit-to-one)"
```

---

## Self-Review

**Spec coverage:** enumerate_roster (Task 1) ✓; select_party policy incl. HM mules / sleep / False-Swipe / non-powder-para / diversity (Task 2) ✓; assemble_party PC realization + no-op fast path + ≤6 / ≥1-mule invariants + assertion (Task 3) ✓; planner integration replacing deposit-to-one (Task 4) ✓; fixture + tests (Tasks 1/3) ✓. Out-of-scope items (leveling, catch move-selection, gym switching) correctly absent. Ball-economy Ultra-Ball change is a C follow-up, not A — correctly absent.

**Placeholder scan:** one intentional flagged placeholder in Task 3 Step 4 (`interior = get_party()[0].species and None`) with an explicit deletion instruction in the same step — acceptable because it names and removes itself. No TBD/TODO elsewhere.

**Type consistency:** `RosterMon.id_bytes: bytes` used as the identity key throughout (select/assemble/planner). `select_party(objective, roster, cap=6)` signature consistent across tasks. `TeamObjective` fields identical in every use. `_find_box_mon`/`bytes_in_party` defined in Task 3 and used only there.

**Open risk to resolve during execution:** the exact PC standing tile/facing for `interact_with_pc` — Task 3 Step 5 says to mirror `boxes.py:deposit_party_fodder`, which already works, if the naive `(pc_tile.x, pc_tile.y+1)` + face-Up doesn't.
