# EVENT 1 — exchange 3, SEAT B (Fix Designer)

Model check: claude-opus-5 (harness spawn parameter `claude-opus-5`; exact id
`claude-opus-5[1m]`, a context-variant marker that per COUNCIL_PROTOCOL.md §3
does not affect model identity).

Fix commit: **`4fb6c1619f0c3ab2fde2a509a633afb061a227a6`** on local `main`. Not pushed.

---

## 1. Diagnosis ownership

I re-derived the chain from the artifact, not from Seat A's summary.
`logs/bot.log` (run 2026-08-01T23:22Z) carries it verbatim:

```
File ".../run.py", line 90, in main            -> run_skill(scripted_opening(), ...)
File ".../dexbot/runner.py", line 387          -> _with_step_watchdog(...)
File ".../modules/modes/_listeners.py", line 189, in report_visible
File ".../modules/encounter.py", line 175, in log_encounter -> print_stats(...)
File ".../modules/console.py", line 214, in print_stats     -> console.print(Panel.fit(...))
File ".../rich/_win32_console.py", line 403, in write_text  -> self.write(text)
File ".../encodings/cp1252.py", line 19, in encode
UnicodeEncodeError: 'charmap' codec can't encode character '♀' in position 7
```

Independently confirmed:

- **Stdout config.** `.venv/Scripts/python.exe -c "print(sys.stdout.encoding, sys.stdout.errors, sys.stdout.isatty())"`
  with stdout redirected to a file → `cp1252 surrogateescape False`. Matches
  Seat C's probe. `surrogateescape` is a red herring: it rescues lone
  surrogates, not unmapped codepoints, which is why the run still died.
- **The gate is on by default from the templates, not the profile.**
  `dexbot/emulator.py:37` builds `Config(POKEBOT_ROOT/"modules"/"config"/"templates")`,
  so the live value comes from `pokebot-gen3/modules/config/templates/logging.yml:17`
  → `log_encounters_to_console: true`. The profile's own `logging.yml` is not read.
  Seat A's citation is right, and it also means "just edit the profile config"
  would not even have worked, quite apart from §9.3 forbidding it.
- **`position 7` → female Rattata**: I accept Seat C's tightening over Seat A's
  looser argument. Verified by the replay itself: the first panel rendered in the
  fixed run is `Rattata♀ encountered at Route 1` (below), on ROUTE1
  `map_group:3 map_number:19`, and `Pidgey♀` renders at position 6.

### Two additions the diagnosis did not have (both change the fix design)

**(a) The class is wider than the gender glyphs, and one member is *not*
gender-gated at all.** `pokebot-gen3/modules/console.py:44-45` appends
`U+2191`/`U+2193` (`↑`/`↓`) to every IV whose nature modifier is non-neutral —
inside the same `print_stats`, on the same panel, for *every* encounter with a
non-neutral nature, regardless of species or gender. Neither arrow exists in
cp1252 (CPython `encodings/cp1252.py` decoding table). So even a Nidoran — the
one species Seat A noted is name-guarded at `console.py:108` — would still have
killed the run. Any fix that sanitises the gender glyph specifically is
incomplete on its face. Emit sites in the class: `console.py:44-45`,
`console.py:109-110,114`, `encounter.py:190-196`.

**(b) The failure is self-perpetuating, which kills the "catch it at the call
site" family of fixes.** `rich/console.py:2019-2027`: in the legacy-Windows
branch, `legacy_windows_render(...)` is called and `del self._buffer[:]` is only
reached *after* it returns. When it raises, the poisoned segments stay in
`Console._buffer` and are re-rendered by the **next** `console.print`. That is
directly visible in `logs/bot.log`: the atexit handler's ASCII-only
`console.print("[yellow]Shutting down...[/]")` (`modules/libmgba.py:239`) fails
with the *same* `'♀' in position 7`. So a `try/except UnicodeEncodeError`
around the print — or around `run_skill`, or in `run.py` — leaves a permanently
broken console; every subsequent encounter would raise again from a buffer the
handler cannot reach. This is a stream-level defect and only a stream-level fix
is sound.

No disagreement with Seat A or Seat C on anything else. On Seat C's box-drawing
point I have new data: see §5.

---

## 2. The fix

Three committed files, all outside `pokebot-gen3/`. Nothing in the vendored
checkout was touched.

### `dexbot/stdio_safety.py` (new, 202 lines incl. the diagnosis in the docstring)
- `stream_is_safe(stream)` (`:95`) — true when the stream's codec can represent
  every Unicode scalar value (utf-8/16/32 family), or when it has no `encoding`
  at all (binary sink / test double: nothing to map, nothing to raise).
- `make_safe(stream)` (`:141`) — escalating, never raises, returns
  `(stream_to_use, status)`:
  `already-safe` → `reconfigured` (`TextIOWrapper.reconfigure`) →
  `rewrapped` (fresh `TextIOWrapper` over `stream.buffer`) →
  `proxied` (`LossyTextStream`, `:108`, escapes what the stream's own codec
  cannot take, *before* handing it over, so the write cannot raise).
- Target is `utf-8` + `errors="backslashreplace"` (`:77`, `:81`).
  `backslashreplace`, not `replace`/`ignore`: an escape still *names* the
  codepoint, so even a degraded write loses no information — §9.3 forbids
  weakening logging, and `♀` is recoverable where `?` is not.
- `harden_stdio()` (`:181`) — applies it to `sys.stdout`/`sys.stderr` in place,
  idempotent, returns a per-stream status, and swallows every exception: a run
  must never fail *because of* this guard.
- Full-coverage streams are left **completely** untouched (`errors` included),
  so pytest's own capture objects are not disturbed by the guard.

### `dexbot/__init__.py:14,23`
```python
from dexbot.stdio_safety import harden_stdio
STDIO_STATUS = harden_stdio()
```
Placed above the `sys.path`/libmgba bootstrap. **This is the unbypassable choke
point:** `pokebot-gen3` is not importable at all until `dexbot/__init__.py:29-30`
inserts it into `sys.path`, so *no* code path can reach `modules.console`,
`modules.encounter` or rich's writer without first executing this line. It
therefore covers `run.py`, the planner loop, `tests/conftest.py`,
`python -m dexbot.dev_resume`, and any future entry point, and it re-runs on
every process start — which is what makes it robust to the supervisor's
restart-on-crash behaviour.

### `supervisor/supervisor.py:481-501` — `bot_env()` + `start_bot(..., env=bot_env())`
Gives the bot child `PYTHONIOENCODING=utf-8:backslashreplace`, closing the
window *before* `import dexbot` runs (interpreter start-up, argparse, an import
traceback carrying a non-ASCII path). This is what rich's own error path
recommends (`rich/console.py:2055`: `"*** You may need to add
PYTHONIOENCODING=utf-8 to your environment ***"`). Deliberately scoped to the
bot child and **not** applied globally: `run_tools()` (`supervisor.py:497`) reads
its children with `capture_output=True, text=True`, i.e. the *parent's* locale
codec, so a UTF-8 override there would mojibake `supervisor.log` (e.g.
`tools/progress_snapshot.py:92`'s em dash) instead of fixing anything. Verified
that nothing decodes `bot.log` as text: the only references are
`supervisor.py:483` (`open(..., "ab")`) and `supervisor.py:150`, which uses it as
an evidence *path string*.

### `run.py:41-43` — one added log line
`[run] stdio: {...} encoding=...` so `bot.log` itself states whether the process
can carry encounter panels. Adds logging; removes none.

### Not changed, on purpose
`log_encounters_to_console` stays `true`. No emit site, no encounter data, no
planner/route/story/navigation code, no telemetry, no protocol or baseline file.

---

## 3. Alternatives considered and rejected

| Alternative | What it closes | Why rejected |
|---|---|---|
| **A. Reconfigure the child's stdout encoding (chosen, primary)** | Everything that reaches any console/log write in this process, present and future, at one line of code. | — |
| **B. Set the child env in `supervisor/supervisor.py` (chosen, secondary)** | The same class, from interpreter start-up, but *only* for supervisor-launched bots. | Kept as defence in depth, rejected as the *primary* fix: it does nothing for a manual `python run.py`, for `dexbot.dev_resume`, for the test suite, or for any other entry point, and it is invisible to anyone reading the crash site. A fix that only holds under one launcher is not a fix for "the planner loop, not just `scripted_opening`". |
| **C. Sanitise strings at the emit sites** | The specific strings sanitised. | (i) All the emit sites are inside gitignored `pokebot-gen3/` (see §4). (ii) It is a whack-a-mole list: `console.py:44-45`, `109-110`, `114`, `encounter.py:190-196` today, plus whatever the next upstream refresh adds — and rich renders *its own* box art through the same stream. (iii) It **destroys content**: the gender glyph is the encounter's information, and §9.3 forbids degrading logging. (iv) It would not even close the class, because rich's own `─`/`│` borders are chosen by rich, not by the emit site. |
| **D. Patch the vendored `pokebot-gen3` console** | The two `modules/` sites, until the next vendor refresh. | Uncommittable (§4), plus every objection in C. |
| **E. Catch the exception at `run.py` / `dexbot/runner.py`** | Nothing. | Refuted by evidence, not by taste: rich never clears the poisoned segment buffer on the raising path (`rich/console.py:2019-2027`), so the *next* `console.print` re-raises from state the handler cannot reach — demonstrated in `logs/bot.log` by the ASCII-only "Shutting down..." print failing with the same `'♀' in position 7`. A caught exception would convert a hard crash into an unbounded per-encounter exception storm with a permanently dead console, i.e. it would hide the defect while degrading logging. Strictly worse than the crash. |
| **F. Construct rich's `Console` with `file=` a UTF-8 wrapper** | Only `modules.console.console`. | Requires editing the vendored module (§4), and misses `print()` and any other console instance. |
| **G. Globally disable encounter console logging** | The symptom. | Explicitly a §9.3 automatic FAIL. Also would not have worked as a config edit — the live value comes from the templates, not the profile (§1). |

### `run.py`'s missing top-level exception handling (Seat A's separately-named gap)
**Out of scope for this fix; it belongs to a later event — argued, not asserted.**

1. It is not on this causal chain. With the stream fixed, the exception does not
   occur; adding a handler changes nothing about EVENT 1's failure and would be
   an unrelated edit under §9.3.
2. It is not obviously a *defect* at all. The supervisor is the restart
   mechanism (`start_bot`/`pause_bot`, crash counting at `CRASH_LIMIT`, trigger
   §4.4), and it detects crashes precisely *because* the child exits non-zero.
   A top-level `except` that logged and continued would blind trigger §4.4; one
   that logged and re-raised is cosmetic. Getting this right means deciding
   which exception classes are resumable and how a resumed loop interacts with
   the auto-checkpoint threshold — a design question with its own blast radius.
3. It needs its own evidence bar. Any handler that keeps the process alive after
   an arbitrary exception must be shown not to poison `current_state.ss1`
   (`run.py:59-66` exists exactly because a wedged battle saved as the resume
   point once cost a whole run). That is a separate replay, not a rider on this one.

Recommendation to Seat C: record it as a carried concern for a later event with
the framing "crash-exit is currently the supervisor's *contract*, not a bug —
decide deliberately whether to change it", rather than bundling it here.

---

## 4. The gitignore constraint (`pokebot-gen3/` is not tracked)

Confirmed independently: `.gitignore:8` lists `pokebot-gen3/`,
`git ls-files pokebot-gen3` is empty, there is no `.gitmodules`.

**No vendor edit was needed and none was made.** The whole fix lives in tracked
files (`dexbot/`, `run.py`, `supervisor/`, `tests/`), so it appears in the §9.3
diff, carries commit `4fb6c16` for a FINDINGS entry (§6), and survives a
re-clone or vendor refresh. This is not incidental — it is the main reason the
stream was chosen as the repair point over the emit sites: the emit sites are
*all* in the untracked vendor tree, so any fix written there would be, in §8.4's
terms, work that did not happen.

Note for the record: `logs/` is *also* gitignored (`.gitignore:5`), so this
evidence file and the replay artifacts under `logs/event1/` are not committable
either. They are referenced by path here and their contents are reproduced in
Seat B's exchange-3 message so the deliberation record does not depend on them.

---

## 5. §9.1 — cold-boot headless replay (Seat C's binding bar)

### Protection of the live run's resume point — what I did

1. Backed up, before anything ran, to `.venv/tmp/event1_backup/`:
   the whole `pokebot-gen3/profiles/livingdex/` directory, `logs/skills.jsonl`,
   `logs/progress.jsonl`, and `fixtures/_phases/`; recorded SHA-256 for each.
2. Ran the replay against a **throwaway profile** `event1replay`, a copy of
   `livingdex`, via `run.py --profile event1replay`. Profile-scoped writes
   (`current_state.ss1`, `current_save.sav`, `stats.db`, auto-checkpoints) went
   there and nowhere near `livingdex`.
3. After the replay: restored `logs/skills.jsonl` byte-for-byte (the replay
   appends skill records to the file the supervisor's `Watcher` polls — leaving
   them would have manufactured false triggers), restored `fixtures/_phases/`,
   and deleted the throwaway profile.
4. Moved the replay's telemetry file out of `logs/telemetry_*.jsonl`, because
   `tools/progress_snapshot.py:60` snapshots the **newest** matching file into
   `logs/progress.jsonl` — leaving it would have injected replay state into the
   live run's progress ledger. It is preserved as evidence at
   `logs/event1/replay_telemetry.jsonl` (a path the glob does not reach).

**Post-replay verification — every hash identical to the pre-replay values:**

```
B5A41C37...E02260  pokebot-gen3/profiles/livingdex/current_save.sav
89947AFE...D82B70  pokebot-gen3/profiles/livingdex/metadata.yml
1A1AF5AF...F71E28  pokebot-gen3/profiles/livingdex/stats.db
73EC8DA0...B1819A  logs/skills.jsonl          (5835 bytes, unchanged)
7BBF39A0...A7DE3E9  logs/progress.jsonl
livingdex/current_state.ss1 exists: False   (as before — it never existed)
fixtures/_phases: 0 differing hashes vs backup
logs/telemetry_*.jsonl count: 3             (as before)
```

### Reproduction conditions — identical to the crashed run

Launcher `.venv/tmp/event1_replay_launch.py` mirrors `supervisor.start_bot()`'s
**pre-fix** invocation exactly: `stdout` = a binary file handle opened `"ab"`,
`stderr=STDOUT`, `stdin=DEVNULL`, `--no-video`, cwd = repo root, and
`PYTHONIOENCODING` explicitly **removed** from the child env so CPython picks the
ANSI codepage on its own — i.e. the child's stdout is a non-tty cp1252 file
handle, the exact configuration Seat C required. The only differences from the
crashed run are `--profile event1replay` and the fix.

Artifacts: `logs/event1/replay_stdout.log` (35,385 bytes),
`logs/event1/replay_telemetry.jsonl` (80 samples).

### The memory-state samples

First line of `logs/event1/replay_stdout.log` after the mGBA banner:

```
[run] stdio: {'stdout': 'reconfigured', 'stderr': 'reconfigured'} encoding=utf-8
```

Decoded from emulator memory by `dexbot/telemetry.py:capture_state()` — not
console text:

| requirement | first qualifying sample | at Pokédex acquisition | last sample |
|---|---|---|---|
| `frame > 16633` | **17233** | 23833 | **52033** |
| `dex_seen >= 3` | **3** | 3 | **7** |
| `dex_owned >= 1` | **1** | 1 | **3** |
| game state | OVERWORLD, `in_battle:false` | OVERWORLD | BATTLE |
| map | `3,19` (ROUTE1) | `4,3` | `3,41` |
| `SYS_POKEDEX_GET` | false | **true** | true |
| process | alive | alive | alive (I stopped it) |

Raw first qualifying line:

```json
{"time":1785628561.688,"frame":17233,"game_state":"OVERWORLD","game_started":true,
 "player_name":"AA","money":3080,"map_group":3,"map_number":19,"coords":[16,9],
 "facing":"Up","party":[{"species":"Squirtle","level":6,"hp":21,"max_hp":21,
 "status":"Healthy"}],"dex_seen":3,"dex_owned":1,"in_battle":false, ...}
```

So: past the crash frame with margin (17233, and ultimately 52033 = 3.1×),
**`SYS_POKEDEX_GET` set at frame 23833**, which is `run.py:86`'s exit condition
for `scripted_opening` — the bot advanced past the stalled objective, not merely
past the frame. It then entered the planner loop and **caught Pikachu**
(`[planner] caught Pikachu (5% on (1, 0))`), taking `dex_owned` 1 → 3 and
`dex_seen` 3 → 7. That also closes Seat A's blast-radius claim empirically: the
planner loop's encounter path is exercised, not just `scripted_opening`.

### The class is demonstrably closed, and the content preserved

Nine encounter panels rendered without a single error. Titles, decoded from the
artifact as UTF-8:

```
┌────────────────────── Rattata♀ encountered at Route 1 ──────────────────────┐
┌────────────────────── Pidgey♂ encountered at Route 1 ───────────────────────┐
┌────────────────────── Pidgey♀ encountered at Route 1 ───────────────────────┐
┌───────────────── Caterpie♂ encountered at Viridian Forest ──────────────────┐
┌────────────────── Pikachu♀ encountered at Viridian Forest ──────────────────┐
┌────────────────────── Mankey♀ encountered at Route 22 ──────────────────────┐
```

Counts in the artifact: `U+2640` ×12, `U+2642` ×6, `U+2191`/`U+2193` ×12,
`U+2500` present, `"UnicodeEncodeError"` absent. Raw-byte check: 12 occurrences
of `E2 99 80` (UTF-8 `♀`) — the glyphs are *in the log*, not stripped.

**A finding worth Seat C's attention:** the panels now use Unicode box drawing
where the pre-fix `bot.log` showed ASCII (`+------ Traceback`). That is rich
adapting, not a side effect: `rich/box.py:Box.substitute` downgrades to ASCII
when `ConsoleOptions.ascii_only`, which is `not console.encoding.startswith("utf")`,
and `Console.encoding` reads `self.file.encoding`. So Seat C's observation that
legacy mode downgrades the borders was correct *because* the stream was cp1252;
with the stream fixed, rich re-enables `─`. This is the fix working *with* rich's
design rather than around it: rich downgrades what it owns (its box art) based on
what the stream declares, and cannot downgrade what it does not own (game text
handed to it). Making the stream's declared capability true is therefore the only
repair point that is consistent for both. It also means the box-drawing class
Seat C flagged is now *reachable* — and safe only because of this fix, which is
one more reason not to rely on a per-glyph sanitiser.

---

## 6. §9.2 — regression

Run verbatim, `cmd /c tools\run_tests.cmd`, at the committed code state:

```
FAILED tests/test_m6_planner.py::test_planner_queue_covers_pre_brock_species
FAILED tests/test_m6_planner.py::test_pre_brock_dex_complete - AssertionError...
2 failed, 136 passed in 36.21s
```

(run twice — before the replay and again after the commit and the state restore:
`36.20s` and `36.21s`, identical counts and identical failure identities.)

Versus Seat C's pre-fix control `2 failed, 120 passed in 37.14s`: **the same two
failures, the same two names** (the known BASELINE.md planner drift — Psyduck
emitted as pre-Brock catchable, `'surf'` method), **zero new failures**, and
`120 → 136 passed` = the 16 tests added here, all passing. I did not attempt the
two baseline failures; per §9.2 that is allowed but not required, and they are a
schema change (STATE.md carried concern 2), not an encoding matter.

### The regression test (`tests/test_console_encoding.py`, emulator-free)

- `test_unhardened_cp1252_stream_raises_on_every_hazard` — parametrised over
  `♀♂↑↓─♪`: each one raises `UnicodeEncodeError` on an untouched cp1252 stream
  (`errors=surrogateescape`, i.e. the crashed run's exact stream shape). This is
  the pre-fix bug, asserted as a fact rather than described.
- `test_make_safe_reconfigures_a_cp1252_stream_and_keeps_the_text` — after
  hardening, all six survive **and the decoded bytes equal the input**: the fix
  must preserve content, not degrade it.
- `test_make_safe_leaves_a_utf8_stream_completely_alone`,
  `test_proxy_fallback_never_raises_when_the_encoding_cannot_be_changed`
  (asserts the escape still names the codepoint: `♀` present),
  `test_harden_stdio_is_idempotent`, `test_harden_stdio_tolerates_a_missing_stream`.
- `test_encounter_panel_with_gender_glyph_survives_a_cp1252_file_stdout` — the
  load-bearing one. A **child process** with `stdout` = a real file handle and
  `PYTHONIOENCODING=cp1252` (forcing the failing condition deterministically on
  any host locale) imports `dexbot`, then renders through the **real vendored
  `modules.console.console`** object: `console.print(Panel.fit(..., title="Rattata♀
  encountered at Route 1"))`. Asserts `rc == 0` and that `♀ ♂ ↑ ↓` are all present
  in the output. Pre-fix this child dies rc=1; that is not a claim —
- `test_control_the_same_child_dies_when_the_guard_is_undone` proves it: the same
  child with `sys.stdout.reconfigure(encoding="cp1252", errors="strict")` after the
  import asserts `rc != 0` and `UnicodeEncodeError` + `u2640` in stderr. If the
  guard is ever removed, the first test fails; if the harness ever stops
  reproducing the crash, the control fails. Both directions are pinned.
- `tests/test_harness_supervisor.py`: `test_bot_env_forces_a_full_coverage_stdio_codec`
  and `test_start_bot_hands_the_child_that_env` (the real `start_bot` path, so
  `env=None` cannot silently return).

Incidental corroboration from this session: an inline `python -c` of mine, with
its own unhardened cp1252 stdout, died with
`UnicodeEncodeError: 'charmap' codec can't encode characters in position 0-22`
while merely *reading back* the panel lines above. Same class, same codec,
different process — the guard is the only thing standing between this codebase
and that error.

---

## 7. §9.3 — diff scope

```
 M dexbot/__init__.py                 (+11)
 M run.py                             (+7 -1)
 M supervisor/supervisor.py           (+18 -1)
 M tests/test_harness_supervisor.py   (+36)
?? dexbot/stdio_safety.py             (new)
?? tests/test_console_encoding.py     (new)
```
(all six are in commit `4fb6c16`)

Explicit statement:

- **No protocol or baseline file touched.** `COUNCIL_PROTOCOL.md`, `GOAL.md`,
  `CLAUDE.md`, `BASELINE.md`: untouched, unread-for-write.
- **No encounter data touched.** `data/` has no modifications of any kind.
- **No route / planner / story / navigation behaviour touched.** `dexbot/planner.py`,
  `dexbot/openings.py`, `dexbot/navigation.py`, `dexbot/catching.py`, `data/*`:
  all unmodified. The two `test_m6_planner` failures are byte-identical to the
  control's.
- **No telemetry or logging deleted, truncated or weakened.** Net additions:
  one `run.py` log line and a per-stream status dict. `logs/skills.jsonl` and
  `logs/progress.jsonl` are byte-identical to their pre-replay hashes;
  `log_encounters_to_console` remains `true`; the encounter panels now reach
  `bot.log` *with* their glyphs instead of killing the process.
- **Nothing inside `pokebot-gen3/`** was modified (it is untracked, so this is
  verifiable: `git status` shows no vendor path).
- `STATE.md` is modified in the working tree but **deliberately not in this
  commit** — that is the driver's EVENT 1 bookkeeping (`Open event: none → 1`),
  not Seat B's work, and bundling it would blur the diff.
- `.venv/tmp/` scratch (launcher, backups, test output) is inside the gitignored
  `.venv/`; `logs/event1/` artifacts are inside gitignored `logs/`.
- Nothing pushed: `git branch -vv` → `main 4fb6c16 [origin/main: ahead 1]`.
  No remote was contacted and no forbidden repository was fetched at any point in
  this exchange — the research here used only the repo's own artifacts and the
  locally installed `rich` / CPython sources (`.venv/Lib/site-packages/rich/`,
  `.venv/base/Lib/encodings/cp1252.py`), plus the vendored pret-independent
  `pokebot-gen3` checkout that is already on disk. No web fetch was made at all.
