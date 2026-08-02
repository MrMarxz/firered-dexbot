# EVENT 1 — Exchange 1 (Seat A, Stall Diagnostician)

**Model check: claude-sonnet-5** (spawned explicitly per COUNCIL_PROTOCOL.md §3/§11).

## 1. Classification

**Code defect** (§2 category), not KB error, not planner deadlock, not transient,
not an already-known finding (FINDINGS.md index confirmed empty — no rediscovery
risk).

**Confidence: high.** The failure is a deterministic, 100%-reproducible
`UnicodeEncodeError` in a display/logging path, independently reproduced by me
(below) from the standard library alone — not a game-logic ambiguity.

## 2. Root cause — causal chain (every link read, file:line cited)

Confirmed causal chain, driver's observation verified as accurate:

1. `dexbot/runner.py:387` `_with_step_watchdog(context.controller_stack[-1])` inside
   `run_skill` (`dexbot/runner.py:276-496`) calls `next(controller)`.
2. That advances into `pokebot-gen3/modules/modes/_listeners.py:183-189`
   (`report_visible`), which — once a wild encounter's "Wild {SPECIES} appeared!"
   text finishes printing — calls `log_encounter(self._active_wild_encounter)`
   at line 189.
3. `pokebot-gen3/modules/encounter.py:174-175`: because
   `context.config.logging.log_encounters_to_console` defaults to `True`
   (`pokebot-gen3/modules/config/schemas_v1.py:195`,
   `pokebot-gen3/modules/config/templates/logging.yml:17`, and nothing in this
   run overrides it), `print_stats(...)` is called unconditionally.
4. `pokebot-gen3/modules/console.py:105-114`: `print_stats` builds
   `rich_name` for the Panel title. Line 108: `if pokemon.gender is not None and
   not pokemon.species.name.startswith("Nidoran")`. Line 109:
   `gender_code = "♂" if pokemon.gender == "male" else "♀"`. Line 114:
   `rich_name = f"[{type_colour}][bold]{pokemon.species_name_for_stats}{gender_code}[/bold][/{type_colour}]"`.
5. Line 214-220: `console.print(Panel.fit(..., title=f"{rich_name} ...`))`.
6. Rich's renderer detects a legacy Windows console (no ANSI/VT support on the
   inherited stdout handle) and takes the `rich/_win32_console.py:442` →
   `write_text` → `.venv\base\Lib\encodings\cp1252.py:19 encode()` path, which
   raises because U+2640 (♀) has no cp1252 codepoint.
7. `dexbot/runner.py:491-493`: `run_skill`'s `except BaseException as e:` logs
   `status="error"` to `logs/skills.jsonl` (confirmed:
   `logs/skills.jsonl:2,4,6`, all three identical) and **re-raises**.
8. `run.py:90` calls `run_skill(scripted_opening(), ...)` with **no surrounding
   try/except** — the exception is unhandled at `run.py`'s top level, Python
   prints the traceback to stderr (captured into `logs/bot.log`, opened
   `"ab"` and wired as the child's combined stdout+stderr —
   `supervisor/supervisor.py:483-485`, confirmed exactly as the driver stated),
   and the process exits with CPython's default unhandled-exception code
   (`rc=1`, matching `logs/supervisor.log:5,7,9`).

**Why deterministic, and what triggers it.** `logs/skills.jsonl:1,3,5` show all
three `scripted_opening` starts at identical `frame=4632`; the two captured
telemetry streams (`logs/telemetry_20260802_012218.jsonl`,
`..._012248.jsonl`) are frame-for-frame, coordinate-for-coordinate,
map-for-map identical from frame 4633 through the crash frame 16633 — this is
a scripted, input-deterministic opening with no RNG-sensitive branching before
this point, so every replay reaches the exact same wild-encounter roll.
`logs/progress.jsonl:1` (`frame:16633, dex_owned:1, dex_seen:3`) pins the
trigger: `dex_seen` goes from 2→3 at the crash frame — this is the run's
**first wild encounter with a determinable gender** (the starter Squirtle at
`dex_seen:1..2` and the rival's Charmander don't route through
`log_encounter`/`report_visible`). Map at the crash
(`map_group:3, map_number:19`, `logs/progress.jsonl:1`) is ROUTE1. Its wild
table per `data/encounters.json:11271-11310` (`"3,19"`, `map_name: "ROUTE1"`)
is exactly two species: **Pidgey** (6 letters) and **Rattata** (7 letters).
The reported error position — `position 7` — is the 0-indexed offset of the
gender glyph appended directly after `pokemon.species_name_for_stats` with no
separator (`console.py:114`); `"Rattata"` occupies indices 0-6, so the glyph
lands at index 7. `"Pidgey"` would land it at index 6. **This pins the
triggering encounter to a female Rattata**, not "some unspecified encounter" —
evidence: `data/encounters.json:11271-11310` (repo data/ source) +
`logs/progress.jsonl:1` (memory-state observation) + the arithmetic on
`console.py:114`.

**The class, not the character.** I independently verified in a live Python
interpreter on this machine:
```
'♂'.encode('cp1252') → UnicodeEncodeError (position 0)
'♀'.encode('cp1252') → UnicodeEncodeError (position 0)
'\xa0'.encode('cp1252') → OK
'é'.encode('cp1252')  → OK
'°'.encode('cp1252')  → OK
```
So the failing class is **any Unicode codepoint outside the Windows-1252
repertoire that reaches `console.print()` while stdout is bound to this
legacy-Windows/cp1252 write path** — not one character. Concretely, in this
codebase that means:
- `console.py:109-114` (`print_stats` / Panel title) — the actual crash site —
  fires for **every non-genderless, non-Nidoran species** (Nidoran is
  excluded only because its species *name itself* already contains ♂/♀ and is
  guarded out at line 108 — meaning an actual Nidoran♂/Nidoran♀ encounter
  would ALSO crash via its `species.name` string, an *unguarded* second
  sub-case of the same class).
- `encounter.py:190-196` (`log_encounter`'s `species_name` for
  `context.message`) builds the identical `♂`/`♀`-suffixed string for a
  different consumer; I did not find a `console.print(context.message)` call
  in the files read, but this is the same defect class sitting in a second
  location and should be checked for other sinks (video overlay text, etc.)
  before being called fixed.
- Any other non-cp1252 glyph anywhere else in the codebase's `console.print`
  call sites (shiny star, special markers, non-Latin move/ability names if
  any) is the same class; I have not exhaustively grepped every
  `console.print` call site — that grep is evidence Seat B's fix must supply
  (see §6 below), not something I should scope here.

## 3. Severity and blast radius

**This is not scoped to `scripted_opening`.** `log_encounter` is invoked from
the generic wild-encounter listener (`_listeners.py:183-196`), which is wired
into `context.bot_listeners` for every `run_skill` call
(`dexbot/runner.py:297`, `get_bot_listeners`), including every
`catch_species`/`safari_run`/`grind_levels` skill the planner runs
(`dexbot/planner.py:561-627`). Critically, `plan_and_catch_all`'s per-species
retry loop (`dexbot/planner.py:584-621`) only catches `except SkillError`
(line 603) — `run_skill` re-raises the **original** `UnicodeEncodeError`
unwrapped (`runner.py:491-493`), so it is not a `SkillError` and is not
caught there either. It would propagate out of `plan_and_catch_all()` and out
of `run.py`'s unguarded call at line 96, killing the whole bot process exactly
as it did here. **This blocks the entire run, not just the opening**: the very
first gendered wild encounter after the planner loop starts would reproduce
the identical crash-loop, and Pidgey/Rattata-class (any gendered, non-shiny,
non-Unown, non-Wurmple-special-cased) encounters are the overwhelming
majority of species in this Pokédex. Until this is fixed, no run can survive
past its first wild encounter, in `scripted_opening` or afterward.

**What it does not block:** anything upstream of the first wild encounter —
the scripted intro, starter selection, and rival battle all completed cleanly
all three times (`logs/telemetry_...:1-14`, badges/flags/party state
progressing identically and without incident through frame ~14833).

**Secondary, separable observation (not a defect I'm calling, just naming it
so it's not conflated with the primary):** `run_skill`'s design of
"log-then-reraise" (`runner.py:491-493`) combined with zero top-level
exception handling in `run.py` around either `run_skill(scripted_opening())`
(line 90) or `plan_and_catch_all()` (line 96) means **any** unhandled
exception during either phase — not just this one — kills the whole process
rather than deferring/retrying at the objective level the way
`SkillError` already does in the planner loop. That is a distinct
architectural gap (missing top-level supervision / exception-type
narrowness) from the Unicode encoding defect itself. I am flagging it as a
second, separable class for the record; I take no position on whether it
should be fixed in this event or PARKED, since naming a fix is not my role.

## 4. Forward-progress analysis

**No progress was made or lost across the three restarts — they are
byte-identical replays.** Evidence:
`logs/telemetry_20260802_012218.jsonl` and `..._012248.jsonl` (restarts 1 and
2) are frame-count-for-frame-count, coordinate-for-coordinate, map-for-map
identical from frame 4633 (first sampled frame) through the crash. Both
`skills.jsonl` start events (`logs/skills.jsonl:1,3,5`) begin at the same
`frame=4632`. `bot.log` prints `"[run] fresh save — playing the intro"`
identically on all three starts (`logs/bot.log:2,62,122`) — and this is
**accurate, not a bug**: `run.py:78` (`if not game_has_started(): ...
run_new_game_intro(...)`) is driven by the profile's actual SRAM
(`pokebot-gen3/profiles/livingdex/current_save.sav`), and `run.py:44-46`
loads/saves `current_state.ss1` for mid-run resume — **no
`current_state.ss1` exists anywhere in the profile directory or repo**
(confirmed: directory listing of `pokebot-gen3/profiles/livingdex/` shows
only `current_save.sav`, `metadata.yml`, `stats.db`; repo-wide search for
`*.ss1` under that profile found none). The reason is not a persistence bug:
`run.py:52` sets `checkpoint_interval_frames = 5*60*60 = 18000`
frames-of-game-time before the first auto-checkpoint fires
(`checkpoint_hook`, `run.py:55-67`), and the crash happens at frame 16633 —
**before** that threshold on every single attempt. So the "resume point"
supervisor.log describes (`"resume point = last calm auto-checkpoint"`,
`logs/supervisor.log:11`) does not yet exist for this run; each restart
correctly and harmlessly re-derives the same ~16,633 frames (≈4.6 min of
emulated game time, ~30s wall-clock at this headless speed per
`skills.jsonl` timestamps) from a genuinely fresh cartridge state. **This is
not a second, separable defect** — the resume point is sound *because*
nothing has been banked yet, and I found no evidence of state corruption or
drift. I checked this specifically because CLAUDE.md's memory index flags
`.ss1` resume soundness as a recurring risk class in this codebase; it does
not apply here.

**Cross-check against STATE.md's 8 carried-forward EVENT 0 concerns:** none is
causally involved. They concern `data/dependencies.json` map-annotation
coverage, per-map-vs-per-method HM gating, the Altering Cave Smeargle/Zubat
table collapse, Dunsparce/Tanoby under-gating, `is_national_dex_enabled`'s
FRLG bug, a stale `BASELINE.md` count, the unverified single-Eevee claim, and
Seat C's `.venv`/Python-3.12 gap. All are planner-routing/KB concerns
downstream of the Pokédex/badge/route graph; none touches console output,
encoding, or the wild-encounter listener. This event is causally independent
of all eight.

## 5. Questions for Seat B / evidence demands for Seat C

- **For Seat B:** the fix's real target is the *class* (§2 above,
  non-cp1252-representable glyphs reaching a `console.print` call under this
  process's stdout configuration), not the single `♀` on Rattata. A fix that
  only special-cases gender symbols, or only patches `console.py:109-114`
  while leaving `encounter.py:190-196`'s identical pattern (and the unguarded
  Nidoran case at `console.py:108`) untouched, has not closed the class.
  Please also grep every `console.print`/`context.message` construction site
  for other non-ASCII literals (I did not do an exhaustive grep — that's
  fix-scoping work, not diagnosis) before calling it closed.
- **Evidence Seat C must demand (§9.1 — memory-state assertion, not
  narrative):** there is **no existing savestate captured at this specific
  stall** — `_dump_stall` (`runner.py:92-110`) is only invoked from the
  pacing/timeout `SkillError` path, never from an unhandled-exception path,
  so nothing under `fixtures/_stalls/` corresponds to this crash, and the
  profile has no `current_state.ss1` either. Given the crash is
  deterministically reproducible from a cold boot of the `livingdex` profile
  (proven above), the replay evidence should be: run headless from a fresh
  boot of this profile with the fix applied, and assert via memory-state read
  (not console text) that `dex_seen` advances to 3 *and* `scripted_opening`
  (or the equivalent planner objective) continues past frame ~16633 without a
  process exit — e.g. an explicit `get_pokedex()`/frame-count assertion in a
  headless test, per the `tests/utility.py:236`
  (`log_encounters_to_console=False`) pattern already used elsewhere in this
  repo's test harness, which itself is worth Seat B/C noting: tests already
  disable this exact logging path, which is presumably why this defect
  wasn't caught by the pytest baseline.
- Regression (§9.2): note STATE.md's carried-forward concern #8 — Seat C
  could not self-serve pytest last event (missing Python 3.12 from the Codex
  shell's view). Per `logs/COUNCIL_LOG` context (git log `a055bf3` "Seat C
  self-serves §9.2 regression runs — run_tests.cmd + self-contained venv"),
  this may already be fixed; Seat C should confirm it can now run the suite
  itself before relying on driver-run evidence again.
