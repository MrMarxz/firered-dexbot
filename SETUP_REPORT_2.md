# SETUP_REPORT_2 — Phase 2: ROM verification, patching, fixtures, quarantine execution

Setup instance run, 2026-07-31. Continuation of `SETUP_REPORT.md` (2026-07-24).
Honesty over optimism: **Phase A (ROM) passed; Phase B (patch) failed again — the
"replacement" patch is content-identical to the old unapplyable summary artifact.
Phase C (fixtures, pytest, M0 boot) was therefore skipped per the task's gate.
Phase D (quarantine) executed in full.**

---

## 1. Phase A — ROM verification: PASSED (both repos)

The human placed the new ROM in `..\dexbot-run\` only; the original repo still held
the Phase-1 bad dump (MD5 `ba45ff6f83fe4a734584ca778088954b`, matching SETUP_REPORT §4
exactly). The verified ROM was copied from dexbot-run over the stale bad dump, then
both re-verified:

| Location | Filename | Size | MD5 | Verdict |
|----------|----------|------|-----|---------|
| `firered-dexbot\roms\firered.gba` | ✅ | 16,777,216 | `e26ee0d44e809351c8ce2d73c7400cdd` | ✅ (after copy from dexbot-run) |
| `dexbot-run\roms\firered.gba` | ✅ | 16,777,216 | `e26ee0d44e809351c8ce2d73c7400cdd` | ✅ (as placed by human) |

### Deferred final setup step (setup.sh line 49 equivalent)

setup.sh's intent is `ln -sf $(pwd)/roms/firered.gba pokebot-gen3/roms/firered.gba`.
**Symlink creation failed in both repos** — `New-Item -ItemType SymbolicLink` →
"Administrator privilege required for this operation" (Developer Mode off, session
unelevated). **Fell back to copying the file**, as the task allows:

| Location | Size | MD5 |
|----------|------|-----|
| `firered-dexbot\pokebot-gen3\roms\firered.gba` | 16,777,216 | `e26ee0d…cdd` ✅ (copy, not symlink) |
| `dexbot-run\pokebot-gen3\roms\firered.gba` | 16,777,216 | `e26ee0d…cdd` ✅ (copy, not symlink) |

Consequence of copies instead of symlinks: **four** independent ROM files now exist;
if the ROM is ever replaced, all four must be updated (`roms\` and
`pokebot-gen3\roms\` in each repo).

## 2. Phase B — Patch: FAILED, replacement is the same summary artifact

`patches/0001-upstream-fixes.patch` was replaced on disk 2026-07-31 13:18 (11,535
bytes, LF endings). **Its content is identical to the Phase-1 artifact** — byte-for-byte
equal (after line-ending normalization) to the copy preserved in
`..\dexbot-run\patches\` (11,753 bytes, CRLF), and `git diff HEAD -- patches/…` shows
no content change (the `M` in git status is line-endings only). Whatever the previous
owner exported, it is the same human-readable change *summary* documented in
SETUP_REPORT §3: diffstat block → `--- Changes ---` divider → annotated hunk excerpts
ending in `+N -M` counters. It contains **no** `diff --git` / `--- a/` / `+++ b/`
headers at all (the only line matching those prefixes is the `--- Changes ---` divider
itself).

Three distinct application attempts against pristine pokebot-gen3 `5dd898f8`
(full transcript: `setup_proof/patch_apply_attempts_phase2.txt`):

1. `git apply --check --verbose` →
   `error: No valid patches in input (allow with "--allow-empty")` (exit 128)
2. GNU `patch -p1 --dry-run` →
   `can't find file to patch at input line 12` … `patch: **** malformed patch at line 44: modules/battle_handler.py` (exit 2)
3. `git apply --check -p0` →
   `error: No valid patches in input (allow with "--allow-empty")` (exit 128)

Per instructions the patch was **not** reconstructed or hand-merged; both pokebot-gen3
clones remain pristine at `5dd898f8`. No diffstat is recordable because nothing was
applied. Unpatched consequences are unchanged from SETUP_REPORT §3: every
`calculate_path(..., max_nodes=...)` call in dexbot (~20 sites) will `TypeError`
against pristine upstream, and the battle/spin-tile/Rocket-Hideout fixes are absent.

**What the human must supply:** a real machine-applyable diff — e.g. from a machine
that still has the patched checkout:
`git -C pokebot-gen3 diff > patches/0001-upstream-fixes.patch`. The file to look for
should start with `diff --git a/modules/... b/modules/...`, not with a diffstat table.

## 3. Phase C — SKIPPED (gated on Phase B, per task step 6)

Phase C was explicitly gated on "Phases A and B both passed". B failed, so **none** of
the following was run: provided-fixture emulator loads, fixture regeneration, the
pytest suites, the M0 boot proof. Everything in this section is disk-level fact
gathering only (no emulation was started).

### Provided fixtures — present on disk, NOT verified

Placed by the human 2026-07-31 13:19, in the **original repo only**:

| File | Size | MD5 | Status |
|------|------|-----|--------|
| `fixtures/a_team_solo.ss1` | 55,506 B | `bf74e7eb6241ae1d86bca8487116eea4` | present, non-trivial size; **load-verification not performed** |
| `fixtures/m7_post_badge1_dex.ss1` | 397,312 B | `119f4f185988d1c9ed20e185a742dcad` | present; **load-verification not performed** |
| `fixtures/m7_badge_brock.ss1` | 397,312 B | `04d581a8feeabb4b4490638fd5f43e16` | present; **load-verification not performed** |

The two `m7_*` files are the same size but different content (distinct MD5s) —
consistent with fixed-size mGBA savestates, not a duplication error. They were **not
copied into `..\dexbot-run\fixtures\`** — that copy is task step 9, inside the gated
Phase C. They remain untouched in `fixtures/` awaiting a valid patch.

### Fixture inventory

- Regenerated this session: **0** (blocked on patch).
- Provided, on disk, unverified: 3 (table above).
- Missing entirely: everything else in `fixtures/README.md`
  (`m0_title`, `m1_game_start`, `m4_post_lab`, `m4_pokedex`, `m5_five_species`,
  `m7_bridge`, `m7_mt_moon_cleared`, `m7_ss_ticket`, `m8_post_snorlax`,
  `m7_badge_koga`, `kit_campaign_final`).
- The two live-profile-derived recipes (`m8_post_snorlax`, `m7_badge_koga` →
  feeding `kit_campaign_final`) remain non-reproducible regardless of the patch;
  they would be skipped even in a full Phase C run.
- `fixtures/_stalls/`: does not exist; no stall output was produced (nothing ran);
  `..\quarantine_holdout\` still contains only its README.

### pytest / M0 boot

Not run this session (gated). The Phase-1 baseline in SETUP_REPORT §6–7 stands as the
latest measurement: 26 failed (all `SystemExit: ROM MD5 mismatch` — those failures'
*cause* is now fixed, but this has not been re-measured), 47 passed, 3 skipped on
`a_team_solo.ss1` (now on disk, also not re-measured). The three formerly-skipped
tests have **no** recorded pass/fail outcome yet. No new artifacts were added to
`setup_proof/` except the patch-attempt transcript; the pre-existing `proof/`
directory was not touched.

## 4. Phase D — Quarantine execution: DONE (dexbot-run only)

All actions below were performed **only** in `..\dexbot-run\`; the original repo's
copies of these files are untouched.

| Step | Action | Result |
|------|--------|--------|
| 12 | Delete `ROADMAP.md` | deleted |
| 13 | Delete `docs/superpowers/specs/` (3 files) and `docs/superpowers/plans/` (1 file) | deleted; `docs/superpowers/` is now an empty dir on disk (untracked by git, so absent from the commit) |
| 14 | Delete `CLAUDE.md` | deleted; **not** replaced (next phase supplies the protocol files) |
| 15 | `fixtures/README.md` narration removal | diff below; every command/recipe instruction preserved |
| 16 | `README.md` dangling links (lines 10–11) | the two link lines removed; nothing else changed |
| 17 | Code comments | untouched everywhere, incl. incident-naming ones |
| 18 | Commit | `fe36c8a` `quarantine: remove prior-run narrative documents` — 8 files changed, 2 insertions(+), 1184 deletions(-) |

`git log --oneline` in dexbot-run now shows exactly two commits and `git remote` is
empty:

```
fe36c8a quarantine: remove prior-run narrative documents
fc6352b chore: initial import of dexbot experiment copy
```

### fixtures/README.md — before/after diff (step 15)

Removed per SETUP_REPORT §8c lines 18–19: the run date (`2026-07-10`), dex count
(`dex 41`), money total (`→ ₽11,676`), the "campaign" narrative framing, the Cubone/
Parasect level-progression narration (`L15→33`, `L33 … en route`), and "Applied to
the live profile." Kept intact: the input-state references, every executable step,
and the resulting fixture state.

```diff
-| `m7_badge_koga.ss1` | Koga campaign from the live `current_state.ss1` (2026-07-10, dex 41): one Route 11 Vs Seeker income lap (→ ₽11,676), then `beat_koga` (assemble_party at Vermilion PC, 9 Hyper Potions, Fuchsia gym gauntlet + Koga). Badge 5 set, party alive. |
-| `kit_campaign_final.ss1` | Catch-kit campaign from `m7_badge_koga` state (2026-07-10): Amulet Coin given to Blastoise, then `train_false_swipe` (Route 11 wild grind, level-balancing strategy) — Cubone L15→33, learned False Swipe, evolved to Marowak; Parasect L33 learned Spore en route. Applied to the live profile. |
+| `m7_badge_koga.ss1` | From the live profile's `current_state.ss1`: one Route 11 Vs Seeker income lap, then `beat_koga` (assemble_party at Vermilion PC, 9 Hyper Potions, Fuchsia gym gauntlet + Koga). Badge 5 set, party alive. |
+| `kit_campaign_final.ss1` | From the `m7_badge_koga` state: Amulet Coin given to Blastoise, then `train_false_swipe` (Route 11 wild grind, level-balancing strategy) — Cubone learns False Swipe and evolves to Marowak; Parasect learns Spore. |
```

Note: `m8_post_snorlax.ss1`'s row (line 17) also mentions live-run state
("badges 4, dex 34") but was **not** flagged in §8c and was left untouched — §8c's
line list was treated as authoritative scope.

### README.md — removed lines (step 16)

```diff
 Full brief, architecture, and milestones are in [CLAUDE.md](CLAUDE.md).
-Progress log: [DEVLOG.md](DEVLOG.md) · Roadmap: [ROADMAP.md](ROADMAP.md) ·
-Honest gaps: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).
```

This also disposed of the `ROADMAP.md` link that step 12 would otherwise have left
dangling. **Newly dangling instead:** line 9's `[CLAUDE.md](CLAUDE.md)` link, because
step 14 deleted CLAUDE.md and step 16 forbade changing anything beyond lines 10–11.
Listed under Unresolved.

## 5. Original repo — state after this session

No commits were made in the original repo and nothing was pushed anywhere.
`git status` is unchanged from session start: `M patches/0001-upstream-fixes.patch`
(line-endings only, see §2), untracked `SETUP_REPORT.md` + `setup_proof/` (+ this
report). The ROM copies landed only in gitignored paths (`roms/`,
`pokebot-gen3/roms/`).

## 6. Unresolved — explicit list

1. **Patch still blocked.** The replacement `patches/0001-upstream-fixes.patch` is
   content-identical to the Phase-1 summary artifact — only its line endings differ.
   The previous owner needs to export an actual diff (see §2 for the command and
   what the file should look like). Until then dexbot cannot run against upstream
   (`max_nodes` TypeError), and everything below stays blocked.
2. **Phase C not executed** (gated on 1): the three provided fixtures are on disk but
   unverified in the emulator; 0 fixtures regenerated; pytest not re-run (the
   ROM-mismatch failures' *cause* is fixed but not re-measured; the 3 formerly-skipped
   tests still have no recorded outcome); no M0 boot proof / title-screen artifact yet
   despite the ROM now verifying.
3. **Provided fixtures not yet in dexbot-run** — copying them is Phase C step 9;
   do it after the patch clears (together with regenerated ones).
4. **ROM is copied, not symlinked**, in both `pokebot-gen3/roms/` (privilege denied on
   symlink creation) — four independent copies exist; keep them in sync if the ROM is
   ever replaced. Enabling Windows Developer Mode would allow real symlinks.
5. **dexbot-run README.md line 9** now has a dangling `[CLAUDE.md](CLAUDE.md)` link —
   created by the mandated CLAUDE.md deletion, out of scope to fix under step 16's
   "change nothing else". One-line fix for the human/next phase.
6. Carried over from SETUP_REPORT §9, still open: `a_team_solo.ss1` has no documented
   recipe (though the file itself is now provided); the two live-profile-derived
   recipes are non-reproducible; setup.sh is Linux-only; README "sibling" wording
   contradicts the in-root pokebot-gen3 layout.

## Proof artifacts added this session (`setup_proof/`, original repo — excluded from dexbot-run)

- `patch_apply_attempts_phase2.txt` — the three failed apply attempts, verbatim, plus
  the content-identity evidence versus the Phase-1 artifact.
