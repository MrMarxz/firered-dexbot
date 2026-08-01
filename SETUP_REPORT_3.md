# SETUP_REPORT_3 — Phase 3: patch derived from owner's snapshot, Phase C executed, holdout populated

Setup instance run, 2026-07-31. Continuation of `SETUP_REPORT.md` (Phase 1,
2026-07-24) and `SETUP_REPORT_2.md` (Phase 2, 2026-07-31). Executed the B-alt /
C-ext / D-ext addendum. **Every previously blocked item is now unblocked: the
real patch was derived from the owner's repo snapshot and applied in both
repos, all fixtures were harvested, both pytest suites run green except two
pre-existing planner failures (identical in both repos, documented below), and
the M0 boot proof exists.**

## 0. The snapshot

- The addendum said the zip is at `..\dewald-snapshot.zip` (sibling of this
  repo). It was actually at **`C:\Users\marku\Downloads\dewald-snapshot.zip`**
  (364,179,251 B); no copy existed at the sibling path.
- Extracted to `..\dewald-snapshot\` (outside both repos) as instructed. The
  zip's single top-level dir is `pokemon/` — the owner's full working repo
  (23,242 zip entries, incl. `.git`, `.venv`, live `states/`, `logs/`, a
  LeafGreen side-project's files, and a `Pokemon - Fire Red Version (U).zip`
  ROM archive which was not touched).
- 14 zip entries were symlinks that failed to extract (unelevated Windows);
  none of them are under `pokebot-gen3/`, `fixtures/`, or anything harvested,
  so nothing this phase needed was affected.

## 1. B-alt — patch derivation: SUCCESS

His `pokebot-gen3/` contains a full `.git`: branch `main`, `origin/main` =
**`5dd898f8`** (exactly our pin, also the merge-base), **13 local commits** on
top, plus **one unstaged edit** (`modules/map_data.py`). No untracked source
files. Therefore a single working-tree diff captures everything:

```
git -C <snapshot>/pokebot-gen3 diff 5dd898f8 > patches/0001-upstream-fixes.patch
```

Result: a genuine `diff --git` patch, 499 lines, 7 files, no binary hunks.

### Sanity check vs the old summary artifact's diffstat

| File | Summary artifact | Derived patch | Note |
|------|-----------------|---------------|------|
| `modules/battle_action_selection.py` | 22 | 76 | grew — later commits (stat-booster fixes) |
| `modules/battle_handler.py` | 22 | 22 | match |
| `modules/battle_move_replacing.py` | 6 | 6 | match |
| `modules/battle_strategies/default.py` | 5 | 5 | match |
| `modules/map_data.py` | — | 11 | **unlisted source change, KEPT** (includes his unstaged edit; VR var-door work per his commit messages) |
| `modules/map_path.py` | 76 | 207 | grew — later commits (VR boulder/path fixes) |
| `modules/modes/util/items.py` | 2 | 2 | match |
| **Total** | 127+ / 6− | **315+ / 14−** | summary is simply older than his checkout |

All six summary-listed files appear; the growth is consistent with his 13
commits (visible in his git log: battle stat-booster fixes, VR path fixes).
No ROM/profile/config noise appeared in the diff, so nothing was excluded.

### Application (original Phase B step 5)

- `git apply --check --verbose` passes against pristine `5dd898f8` in **both**
  repos (all 7 files check clean).
- Applied in both `firered-dexbot\pokebot-gen3\` and `dexbot-run\pokebot-gen3\`;
  post-apply diffstat in each: `7 files changed, 315 insertions(+), 14 deletions(-)`.
- `calculate_path` now takes `max_nodes` (`modules/map_path.py:812`); verified
  by real import + `inspect.signature` through each repo's own `.venv`
  (`MAX_NODES_RESOLVES_ORIGINAL` / `MAX_NODES_RESOLVES_DEXBOTRUN`). The ~20
  dexbot `max_nodes=` call sites no longer TypeError.

## 2. C-ext — fixture harvest: 26 harvested, 0 regenerated

Snapshot `fixtures/` top level holds 77 `.ss1` files. Harvest rule applied:
name appears in `fixtures/README.md`'s inventory **or** is loaded by a test.

- **Harvested (26)**: `m0_title`, `m1_game_start`, `m4_post_lab`, `m4_pokedex`,
  `m5_five_species`, `m6_pre_brock_dex`, `m7_bridge`, `m7_mt_moon_cleared`,
  `m7_ss_ticket`, `m7_badge_misty`, `m7_badge_surge`, `m7_badge_erika`,
  `m7_badge_koga`, `m7_badge_sabrina`, `m7_badge_blaine`, `m7_badge_giovanni`,
  `m7_cerulean_sweep`, `m7_hm_cut`, `m7_post_surge_sweep`,
  `m7_rock_tunnel_sweep`, `m7_tea`, `m7_west_sweep`, `m8_post_snorlax`,
  `m8_secret_key`, `m8_silph`, `kit_campaign_final` — including all three
  previously non-reproducible live-profile-derived ones.
- **Already provided (3)**: `a_team_solo`, `m7_post_badge1_dex`,
  `m7_badge_brock` — the snapshot's copies are **byte-identical** (same MD5s)
  to what the human placed in Phase 2. Not overwritten.
- **Excluded**: `current_state.ss1` (only a docstring reference to the live
  profile, not a fixture); the other ~48 top-level `.ss1` (LeafGreen `lg_*`,
  trade-experiment, probe/diagnostic states) — no README/test reference.
- **Still missing after harvest: none.** Per addendum step 6, **no fixture was
  regenerated** — the harvest covered everything README- or test-referenced.
  Full MD5 table of all 29: `setup_proof/fixture_load_verification.txt` has
  the load results; hashes were recorded in-session.

## 3. Phase C — executed in full

### Fixture load verification — 29/29 OK

Every `.ss1` in `fixtures/` was loaded into a headless emulator, one frame
run, and state decoded (`setup_proof/fixture_load_verification.txt`).
All 29 load; `m0_title` decodes as `TITLE_SCREEN`, the other 28 as
`OVERWORLD` with sane map/coords — `m1_game_start` sits at map (4,1) @ (6,6),
exactly its README recipe.

### Copy to dexbot-run (Phase C step 9)

All 29 fixtures copied to `..\dexbot-run\fixtures\`. `.ss1` is gitignored
there — no commit needed, tree stays clean.

### pytest — both repos, identical results: **74 passed, 2 failed, 0 skipped**

| | Phase 1 baseline | This run (original) | This run (dexbot-run) |
|---|---|---|---|
| passed | 47 | **74** | **74** |
| failed | 26 (all ROM-MD5 SystemExit) | **2** | **2** |
| skipped | 3 (`a_team_solo.ss1` missing) | **0** | **0** |

(Original repo: 46.1s; dexbot-run: 43.9s. Tails archived as
`setup_proof/pytest_phase3_original_tail.txt` / `…dexbot-run_tail.txt`.)

- **Formerly-skipped tests — all now PASS** (explicit re-run,
  `setup_proof/pytest_formerly_skipped_a_team.txt`):
  `test_a_team.py::test_enumerate_roster_reads_party_and_boxes`,
  `test_a_team.py::test_assemble_party_realizes_selection`,
  `test_a_team_planner.py::test_planner_assembles_catch_team_not_solo`.
- **Previously "non-reproducible recipe" fixtures — outcomes as requested:**
  - `m7_badge_koga.ss1` → `test_m7_koga.py::test_koga_defeated` **PASSED**.
  - `m8_post_snorlax.ss1` → loaded fine (29/29 table); no test loads it —
    it is only the documented regeneration *input* for `m7_badge_koga`.
  - `kit_campaign_final.ss1` → loaded fine; no test references it
    (README-inventory harvest only).
- **The 2 failures — pre-existing planner/KB drift, identical in both repos**
  (`tests/test_m6_planner.py::test_planner_queue_covers_pre_brock_species`,
  `::test_pre_brock_dex_complete`): `missing_catchable()` emits
  `('Psyduck', (3, 41), 100, {'requires': [], 'safe_tile': [38, 11]}, 'surf')`
  — a surf encounter with an empty `requires` list, so the planner counts it
  as pre-Brock catchable; the test's expected set (correctly) excludes it.
  Not a setup failure: the test file is identical to the snapshot's (modulo
  CRLF), but the snapshot's `dexbot/planner.py` and `data/` are **newer** than
  our release cut — the owner evidently fixed this after `ee2a10c` was cut.
  Importing his newer code/data is forbidden by the addendum ("no code" beyond
  the patch), so the failures stand and are recorded here.

### M0 boot proof — done

Fresh headless boot (no savestate): title screen (`CB2_TITLESCREENRUN`)
reached at **frame 818**; `setup_proof/m0_title.png` (genuine
FireRed title screen, visually verified) + `setup_proof/m0_memory.json`
(ROM MD5, gMain address `0x30030f0` + first 16 bytes). Written to
`setup_proof/` so the owner-era `proof/` dir stays untouched; the harvested
`fixtures/m0_title.ss1` was preserved (m0_boot's fixture write was restored
from the harvested bytes afterwards).

## 4. D-ext — quarantine holdout populated

- `fixtures/_stalls/` → `..\quarantine_holdout\_stalls\`: **894 files
  (~174 MB), filenames preserved** — 447 stall savestates, each with its
  `.png` screenshot sidecar; no unpaired files. Top producers:
  vs_seeker_leg (57 pairs), assemble_party (51), evolve_stones (32),
  retry_heal (28), plus a ~90-skill tail.
- Stall-like states found **elsewhere** in the snapshot's fixtures top level →
  `..\quarantine_holdout\stuck_elsewhere\`: `_wip_stuck.ss1`,
  `lg_stuck_route2.ss1`, `lg_stuck_tower.ss1` (the `lg_*` two are
  LeafGreen-side diagnostics).
- **Not** copied (not stalls): snapshot `fixtures/_phases/` (172 deliberate
  mid-skill phase checkpoints) and `states/` (63 live-run checkpoints) —
  left in the snapshot.
- Holdout `README.md` updated with the full inventory. Nothing from any of
  this entered `dexbot-run\`.

## 5. dexbot-run — two new commits (chose commits over amending)

Step 9's README fix was made as a **third commit** (not an amend — history
stays honest), and the stale committed patch artifact was replaced as a
fourth:

```
a5d642c fix(patches): replace prose change-summary with the real upstream diff
03941d1 docs: remove dangling CLAUDE.md link left by quarantine
fe36c8a quarantine: remove prior-run narrative documents
fc6352b chore: initial import of dexbot experiment copy
```

- `03941d1`: removed the line 9 sentence `Full brief, architecture, and
  milestones are in [CLAUDE.md](CLAUDE.md).` and collapsed the doubled blank
  line the removal left; nothing else changed (2 deletions).
- `a5d642c`: dexbot-run's committed `patches/0001-upstream-fixes.patch` was
  still the unapplyable prose summary; replaced with the derived real patch so
  the run repo is self-consistent with its patched `pokebot-gen3/`
  (499 insertions, 218 deletions). Judgment call — the addendum allows the
  derived patch into either repo; flagging it here for transparency.
- Working tree clean, still no remotes, nothing pushed.

## 6. Exactly what was taken from the snapshot (addendum step 10)

1. **The derived patch** — generated from his `pokebot-gen3` git history
   (working-tree diff vs `5dd898f8`); saved to both repos'
   `patches/0001-upstream-fixes.patch` and applied to both `pokebot-gen3/`
   checkouts.
2. **26 fixture savestates** (list in §2) → `firered-dexbot\fixtures\`, then
   copied (with the 3 pre-existing) to `dexbot-run\fixtures\` (gitignored).
3. **897 stall files** (894 from `_stalls/` + 3 stuck-states from fixtures top
   level) → `..\quarantine_holdout\` only — **not** a repo.

Nothing else — no markdown, docs, code, data, ROMs, or logs — entered either
repo. `..\dewald-snapshot\` is left in place for the human to delete;
the source zip remains at `C:\Users\marku\Downloads\dewald-snapshot.zip`.

## 7. Remaining open items

1. **2 planner-test failures** (§3) — pre-existing drift between the release
   cut and the owner's later working tree (his newer `dexbot/planner.py` +
   `data/` presumably fix it; visible read-only in the snapshot). Needs a
   human decision: re-derive the fix independently, or explicitly authorize
   syncing those files from the snapshot.
2. **Original repo left uncommitted** as in prior phases (patch modified,
   reports + `setup_proof/` untracked) — no instruction authorized commits
   here.
3. Carried over: four independent ROM copies (sync if replaced); setup.sh is
   Linux-only; README "sibling" wording vs in-root `pokebot-gen3/`;
   `a_team_solo.ss1` still has no documented recipe (file provided, verified
   loading).

## Proof artifacts added this session (`setup_proof/`)

- `fixture_load_verification.txt` — 29/29 fixtures load + decoded state table
- `pytest_phase3_original_tail.txt`, `pytest_phase3_dexbot-run_tail.txt` —
  suite results (74P/2F/0S each)
- `pytest_formerly_skipped_a_team.txt` — the 3 formerly-skipped tests passing
- `m0_title.png`, `m0_memory.json` — M0 boot proof (fresh boot, frame 818)
