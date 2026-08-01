# SETUP_REPORT — firered-dexbot setup, verification & quarantine

Setup instance run, 2026-07-24. Honesty over optimism: **two hard blockers were found
(unapplyable upstream patch, ROM MD5 mismatch)**. Everything that could be done without
them was done; everything invalidated by them was stopped and is listed under
*Unresolved* at the bottom.

---

## 1. Environment

| Item | Value |
|------|-------|
| OS | Windows 11 Pro 10.0.26200 (win32) — note: setup.sh assumes Linux |
| Repo root | `C:\Users\marku\OneDrive\Desktop\GIT\firered-dexbot` (clone of MrMarxz/firered-dexbot, HEAD `ee2a10c`, branch main, clean) |
| Python | 3.12.10 — **installed during setup** (only 3.14.3 was present; project pins 3.12). Per-user silent install from python.org official installer (`python-3.12.10-amd64.exe`), no PATH/system changes |
| venv | `.venv/` in repo root, Python 3.12.10 |
| Key packages | numpy 2.1.3, cffi 1.17.1, Pillow 10.4.0, aiohttp 3.10.11, pytest 9.1.1 + full pinned set from setup.sh, plus upstream's Windows extras `pywin32`, `psutil~=5.9.5`. Full list: `setup_proof/pip_freeze.txt` (64 packages) |
| libmgba | libmgba-py 0.2.0 (release tag `0.2.0-2`) **win64** build extracted to `pokebot-gen3/mgba/` — the Windows equivalent of setup.sh's ubuntu-lunar zip; DLLs are bundled, so the Linux-only `vendor/lib/libmgba.so.0.10` step was skipped (the `dexbot/__init__.py` preload is conditional and simply no-ops) |
| pokebot-gen3 | Cloned **inside the repo root** at pinned commit `5dd898f8` ("Overlay: Fix issues with encounter list and pre-load sprites (#821)") — exactly what setup.sh pins; working tree clean (unpatched, see §3) |

### pokebot-gen3 location — README wording vs. reality

The README calls pokebot-gen3 a "sibling — clone it alongside", which reads as
*next to* the repo. The code disagrees: `dexbot/__init__.py:23` hardcodes
`POKEBOT_ROOT = PROJECT_ROOT / "pokebot-gen3"`, `.gitignore:8` ignores `pokebot-gen3/`,
and setup.sh clones into the repo root. **The correct location is inside the repo root,
where the human placed it — no move was needed.** The README's "sibling" phrasing is
the disagreement, reported here as required; "(gitignored here)" is the accurate half.

Import verification passed:
`import dexbot` → `POKEBOT_ROOT` on `sys.path` → `import modules`, `import mgba`,
`from modules.memory import GameState` all succeed under the venv.

## 2. setup.sh outcome

Summary of what it does: pin-clone pokebot-gen3 into the repo root; apply `patches/`
(silently skipping on failure via `|| true` — this contradicts the task's stop-and-report
rule, so patches were handled explicitly, see §3); create `.venv` with `python3.12`; pip-install
the pinned dependency set; download libmgba-py 0.2.0 (Ubuntu build) into `pokebot-gen3/`;
vendor `libmgba.so.0.10` out of an Ubuntu .deb; MD5-check the ROM and symlink it into
`pokebot-gen3/roms/`.

Run as-is (Git Bash): **failed at line 21, `python3.12: command not found`** — the script
is Linux-only (`python3.12` binary name, `.venv/bin/`, apt-get/dpkg, `.so` vendoring).
All steps were then performed manually with Windows equivalents (documented in §1).
No repo files were edited. The final setup.sh step (symlink ROM into `pokebot-gen3/roms/`)
was deliberately **not** performed because the ROM failed verification (§4).

## 3. Patch application — FAILED, unapplyable artifact

**`patches/0001-upstream-fixes.patch` is not a machine-applyable diff.** It is a
human-readable change *summary*: a diffstat header, a `--- Changes ---` divider, then
annotated hunk excerpts ending in `+N -M` counters. It has no `diff --git`/`---`/`+++`
file headers and elides context lines (verified: hunk `@@ -171,11 +171,31 @@` shows only
~7 of 11 old-side lines).

Three application attempts, all failed:
1. `git apply --check --verbose` → `error: No valid patches in input`
2. GNU `patch -p1 --dry-run` → `can't find file to patch at input line 12` (parses the diffstat as garbage)
3. `git apply --check -p0` → same as (1)

History forensics: the file **was** a valid git diff up to commit `b11ff90` (2026-07-07);
commit `137ad88` replaced it with the summary format, and all later upstream fixes
(spin-tile pathfinding `db6938e`, Rocket Hideout blocker `e809396`, A* `max_nodes` budget
`cdcf880`) exist **only** in summary form. The valid historical version predates the
`max_nodes` API. No branches, tags, or stashes hold a newer valid copy (fresh clone,
single-entry reflog).

Per instructions I did **not** hand-reconstruct the patch. Consequences of running
unpatched:
- `dexbot` calls `calculate_path(..., max_nodes=...)` in ~20 places
  (`navigation.py`, `gyms.py`, `story.py`, `items_ground.py`) — unpatched upstream will
  raise `TypeError` on every such call.
- Battle edge-case fixes (stale party slot after PC deposits, whiteout instead of crash,
  in-battle item-use loop fix), spin-tile/stair-warp path modeling, and the Rocket
  Hideout B1F phantom-column blocker are all absent.
- **Fixture regeneration and most gameplay tests are invalid until a real patch is
  provided** (currently masked by the ROM blocker, which fails first).

## 4. ROM verification — FAILED (hard stop for all emulation)

| Check | Expected | Actual | Verdict |
|-------|----------|--------|---------|
| Path/filename | `roms/firered.gba` | `roms/firered.gba` | ✅ |
| Size | 16 MiB | 16,777,216 bytes | ✅ |
| MD5 | `e26ee0d44e809351c8ce2d73c7400cdd` | `ba45ff6f83fe4a734584ca778088954b` | ❌ **MISMATCH** |
| SHA-1 (for the record) | — | `c40338de117f8d01fa9d63e8db12844ddff006ef` | — |

GBA header of the placed file: title `POKEMON FIRE`, game code `BPRE` (FireRed USA),
maker `01`, version byte `0` (claims rev 1.0). Correct size and header but wrong content
hash ⇒ **a modified or bad dump wearing a v1.0 header** — not an innocently-swapped v1.1
(whose header version byte would be 1). Per project rules nothing was downloaded or
generated to replace it; **the human must supply a verified FireRed USA 1.0 dump**.
Everything ROM-derived (fixtures, gameplay tests, boot proof) is invalid until then.

## 5. Fixture regeneration — BLOCKED (0 of 12+ produced)

`fixtures/` contained only `README.md` — no `.ss1` files and **no `fixtures/_stalls/`
directory** (the public-release commit `ee2a10c` untracked all ROM-derived savestates).
Every documented regeneration command boots the emulator through
`setup_headless_emulator()` → `verify_rom()`, which exits on the MD5 mismatch. Zero
fixtures were regenerated; none of the documented inventory (m0_title, m1_game_start,
m4_post_lab, m4_pokedex, m5_five_species, m7_* chain, m8_post_snorlax,
kit_campaign_final) exists.

Two fixture-documentation gaps found while attempting this:
- Tests skip on `a_team_solo.ss1`, which is **not documented** in `fixtures/README.md`.
- Several fixtures chain from states not in the table (`m7_post_badge1_dex.ss1`,
  `m7_badge_brock.ss1` are referenced as inputs but have no recipe rows), and two rows
  derive from "the live profile's `current_state.ss1`", which is not reproducible from
  a fresh ROM by following the README alone.

## 6. pytest results

Full logs: `setup_proof/pytest_original_repo.txt`, `setup_proof/pytest_dexbot_run.txt`.

**Both repos: 26 failed, 47 passed, 3 skipped — per-test outcomes diffed and identical
(76 entries).**

- 26 FAILED — all uniform `SystemExit: ROM MD5 mismatch` raised by the `verify_rom()`
  gate before any emulation (m0 boot, m1 telemetry, m3 navigation ×3, m4, m5, m6 ×2,
  m7 blaine/bridge/erika/giovanni/gyms×2/hm_cut/koga/misty/sabrina/ss_ticket/surge/
  sweep×4, m8 secret_key). No other defect signature surfaced; with the wrong ROM these
  tests say nothing about code health.
- 47 PASSED — ROM-independent logic: knowledge-base checks (test_m2), planner queue
  logic, LLM-planner validator/fallback (test_m9, both boundaries), team/battle/catch
  action selection, encounter-map lookup.
- 3 SKIPPED — missing undocumented fixture `a_team_solo.ss1` (test_a_team ×2,
  test_a_team_planner).

## 7. Boot verification (M0)

`python -m dexbot.m0_boot` aborts at the MD5 gate with exit code 1:

> ROM MD5 mismatch: got ba45ff6f83fe4a734584ca778088954b, expected
> e26ee0d44e809351c8ce2d73c7400cdd (FireRed USA 1.0). Refusing to run with an
> unverified ROM.

That refusal — the gate functioning exactly as specified — is the only honest M0
artifact producible in this environment. Captured in `setup_proof/m0_boot_attempt.txt`.
No title-screen screenshot/memory snapshot exists because emulation never started.
`setup_proof/` is a fresh directory; the pre-existing `proof/` was not touched or reused.

## 8. Quarantine (Phase 3)

- **Copy**: working tree → `..\dexbot-run\` excluding `.git/`, `pokebot-gen3/` (lives
  in-root), plus setup artifacts `.venv/` and `setup_proof/` and `__pycache__`/
  `.pytest_cache`. The unverified ROM copied along as part of the working tree — flagged
  here so the human replaces it in **both** repos.
- **Deleted in dexbot-run**: `KNOWN_LIMITATIONS.md`, `DEVLOG.md`, `proof/` (17 files).
- **Fresh git**: `git init -b main`, single commit `fc6352b`; verified `git rev-list
  --count HEAD` = 1, no remotes, clean status. `.gitignore` keeps `pokebot-gen3/`,
  `.venv/`, `roms/` out of tracking.
- **Runnable**: pinned pokebot-gen3 (`5dd898f8` + win64 mgba bindings) copied in
  offline; fresh Python 3.12 venv with the same pinned packages; pytest re-run inside
  `dexbot-run` — identical to original (§6).
- **Fixtures**: none to copy (none exist, §5). **`quarantine_holdout/`** created OUTSIDE
  dexbot-run (`..\quarantine_holdout\`) with a README; it is **empty** because no
  `fixtures/_stalls/` savestates existed on disk.
- **No remote pushes anywhere; all work local.** Nothing was committed to the original repo.

### 8c. Reference-scan hit list (report-only — nothing deleted; human decides)

Minimum term `"KNOWN_LIMITATIONS"` (7 hits):
| File | Line | Note |
|------|------|------|
| `CLAUDE.md` | 65 | process rule "Keep a KNOWN_LIMITATIONS.md" |
| `README.md` | 11 | dangling markdown link (file deleted) — prose, breaks no tooling |
| `ROADMAP.md` | 70 | **narrates a diagnosed failure** (Vs Seeker "no interested trainers" mystery) + dangling "see KNOWN_LIMITATIONS" |
| `dexbot/evolution.py` | 6, 28 | code comments "see KNOWN_LIMITATIONS" |
| `dexbot/story.py` | 22, 249 | code comments "in KNOWN_LIMITATIONS" / "too slow from here (see KNOWN_LIMITATIONS)" |

Minimum term `"DEVLOG"` (4 hits):
| File | Line | Note |
|------|------|------|
| `README.md` | 10 | dangling markdown link |
| `CLAUDE.md` | 50, 63, 111 | process rules referencing DEVLOG.md (the "write a DEVLOG entry" workflow) |

Minimum terms `"stall 2"`, `"seen live"`: **0 hits** in the remaining tree (those
phrases lived only in the deleted files).

Minimum term `"2026-07"` (15 content hits + 4 dated filenames):
| File | Line(s) | Note |
|------|---------|------|
| `CLAUDE.md` | 13 | owner directive date |
| `ROADMAP.md` | 3, 10, 12, 45, 51 | dated progress narration ("Where we are (2026-07-10, late night)", badges done) |
| `fixtures/README.md` | 18, 19 | fixture recipes narrating the live run (dex 41, ₽11,676, Koga campaign) |
| `docs/README.md` | 3 | Bulbapedia cache date (benign) |
| `dexbot/planner.py` | 343 | code comment "both diagnosed 2026-07-10" |
| `docs/superpowers/specs/2026-07-09-battle-team-gym-progression-design.md` | 3, 12 | **narrates the Koga whiteout loss** (+ dated filename) |
| `docs/superpowers/specs/2026-07-09-team-roster-pc-assembly-design.md` | 3, 22 | whiteout narration (+ dated filename) |
| `docs/superpowers/specs/2026-07-09-safe-weakening-catch-strategy-design.md` | — | dated filename (content hits under broader terms) |
| `docs/superpowers/plans/2026-07-09-team-roster-pc-assembly.md` | — | dated filename |

Broader failure-narration pass (candidates beyond the minimum terms; code comments —
NOT removed, human to judge). Highest-signal items:
| File | Line | What it reveals |
|------|------|-----------------|
| `dexbot/story.py` | 1883 | points at a specific stall savestate: "probe_maze tape (fixtures/_stalls/evolve_stones_163922.ss1 → door)" |
| `dexbot/runner.py` | 329 | "the Koga stall" |
| `dexbot/battle.py` | 3 | "the Koga whiteout" |
| `dexbot/boulders.py` | 280 | "(churned the live E4 run)" |
| `dexbot/navigation.py` | 101, 411 | "USR1-diagnosed twice" / "re-ran identical failures for hours of CPU" |
| `dexbot/navigation.py` | 439 | "get_rods stalled in Lavender" |
| `dexbot/catching.py` | 383, 602 | "Cave 30k-frame stall", "fenced zoo pen … stalls for 30k frames" |
| `ROADMAP.md` | 10–70 | whole file is a dated progress/failure narrative — closest thing to a surviving DEVLOG |
| `docs/superpowers/specs/*.md`, `plans/*.md` | — | previous owner's design docs incl. failure post-mortems |

Dangling references that would break tooling: **none found.** `dexbot/m0_boot.py`
recreates `proof/` via `mkdir(exist_ok=True)`; `dexbot/runner.py` recreates
`fixtures/_stalls/` the same way. No script reads DEVLOG.md or KNOWN_LIMITATIONS.md.
Accordingly, no code fixes were made.

## 9. Unresolved — explicit list

1. **ROM is not FireRed USA 1.0** (MD5 `ba45ff6f…`, modified/bad dump with a v1.0
   header). Human must place a verified dump at `roms/firered.gba` in **both** repos.
   Until then: no fixtures, no gameplay tests, no boot proof, no experiment.
2. **`patches/0001-upstream-fixes.patch` cannot be applied** (summary, not a diff).
   Human must export a real diff (e.g. from a machine that still has the patched
   pokebot-gen3 checkout: `git -C pokebot-gen3 diff > patches/0001-upstream-fixes.patch`).
   Without it, dexbot's `max_nodes` calls TypeError against pristine upstream even with
   a good ROM. Both pokebot-gen3 clones (original repo and dexbot-run) are pristine at
   `5dd898f8`.
3. **Fixtures: 0 regenerated** (blocked by 1, and partially by 2). After both blockers
   clear: rerun the `fixtures/README.md` recipes, copy results into `dexbot-run/fixtures/`,
   and divert any `fixtures/_stalls/` output to `..\quarantine_holdout\`.
4. **`a_team_solo.ss1` has no documented recipe** in fixtures/README.md (3 tests skip);
   `m7_post_badge1_dex.ss1` / `m7_badge_brock.ss1` are referenced as chain inputs without
   recipe rows; two recipes depend on a non-reproducible "live profile" state.
5. **setup.sh is Linux-only** — on this Windows machine it cannot run past line 21;
   the Windows-equivalent environment was built manually (§1–2). Not "fixed" in-repo
   since editing repo files was out of scope.
6. **Quarantine judgement calls for the human** (§8c): ROADMAP.md and
   `docs/superpowers/` carry substantial previous-run narration; code comments
   name specific past incidents (Koga stall/whiteout, `_stalls/evolve_stones_163922.ss1`,
   live E4 churn). All left in place per instructions.
7. **README "sibling" wording** contradicts the actual in-root pokebot-gen3 layout (§1).

## Proof artifacts (`setup_proof/`, this repo — excluded from dexbot-run)

- `pytest_original_repo.txt` — full verbose suite output, original repo
- `pytest_dexbot_run.txt` — full verbose suite output, clean copy
- `m0_boot_attempt.txt` — M0 boot gate refusal (exit 1)
- `pip_freeze.txt` — 64-package environment inventory
