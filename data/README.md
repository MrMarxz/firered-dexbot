# Knowledge base (data/)

All game facts the bot uses at runtime. **Nothing here is LLM-generated.**

| File | Contents | Source |
|------|----------|--------|
| `encounters.json` | Wild encounter tables for all 124 maps with encounters: land/surf/rock-smash/old-good-super-rod slots, per-slot % rates, level ranges. Keyed `"group,number"`, includes map name. | **Generated from the verified FireRed USA 1.0 ROM** by `dexbot/build_kb.py` (reads `gWildMonHeaders` via pret/pokefirered symbol tables; slot rates are the fixed gen-3 slot distribution from the decompilation). Regenerate: `python -m dexbot.build_kb`. |
| `trainers.json` | All 742 trainer parties: name, class, per-mon species/level/IV-strength, held items and custom moves where set. Keyed by trainer id (pret opponent index). | **Generated from the ROM** (`gTrainers`, pret `struct Trainer`). Same script. |
| `tmhm.json` | TM01–TM50 + HM01–HM08 → move taught + item index. | pokebot-gen3's `modules/data/items.json`/`moves.json` (extracted from pret decompilations). |
| `dependencies.json` | Story-flag / badge / HM dependency graph for progression planning. | Hand-authored from [Bulbapedia FRLG walkthrough](https://bulbapedia.bulbagarden.net/wiki/Appendix:FireRed_and_LeafGreen_walkthrough) and [Badge](https://bulbapedia.bulbagarden.net/wiki/Badge) field-move gating. Spot-verified in-game as milestones progress. |

Species data (catch rates, evolution methods, base stats, learnsets, types) is **not
duplicated here** — the bot reads `pokebot-gen3/modules/data/species.json`, which is
extracted from the pret decompilation projects by upstream's `modules/data/extract.py`.

Verified by `tests/test_m2_kb.py` spot checks (Pikachu in Viridian Forest at 5%,
Abra on Route 24 at 15%, Brock's party, HM moves, Squirtle evolution line).
