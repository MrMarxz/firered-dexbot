# ROADMAP — where we are, where we're going, what fires next

Process rule (owner, 2026-07-10): after finishing ANY milestone or objective,
re-scan the **Opportunities** table and fire everything whose trigger is now
met — an unlock acted on late is progress thrown away (the Amulet Coin sat
inert in the bag for a day; the False-Swipe Cubone sat at L15 in a box).
Acquisition skills must follow through themselves where possible
(get_amulet_coin now gives the coin to the lead as part of the skill).

## Where we are (2026-07-10, evening)

Badges 1–5 (Koga ✓). **Dex: 51 owned** (fishing chunk complete: Magikarp,
Horsea, Poliwag, Poliwhirl, Goldeen, Krabby, Gyarados, Psyduck). Bicycle ✓,
Vs Seeker ✓, all three rods ✓, HM01 Cut ✓, HM03 Surf ✓ (taught to Blastoise),
Poké Flute ✓, Amulet Coin ✓ (held by Blastoise), **Exp. Share ✓** (collected
the hour dex hit 50), catch kit complete: Marowak L33 **False Swipe** +
Parasect L33 **Spore** + Gloom Sleep Powder backup. Catch queue idle again —
the frontier is the Safari Zone / Surf-water annotations.

## Story spine (mirrors data/dependencies.json `objectives`)

Done: pokedex → Brock → Misty → Bill/SS Ticket → Cut → Surge → Erika →
Rocket Hideout/Silph Scope → Poké Flute → **Koga**.

Next, in dependency order:
1. **Safari Zone** (open now): Gold Teeth → HM04 Strength; Warden's house;
   Safari-exclusive dex chunk (Scyther/Pinsir/Chansey/Kangaskhan/Tauros/
   Dratini via fishing, ...). Needs M8 `safari_run` (step budget, bait/rock).
2. **Silph Co** (open now): clears Saffron gym access → Sabrina (badge 6).
3. **Cinnabar** via Surf from Pallet/Route 21: Mansion Secret Key → Blaine
   (badge 7). Surfable water routes also open big dex chunks — annotate them.
4. **Sevii Islands** (after Blaine): island dex species, Moltres.
5. **Viridian gym** (Giovanni, badge 8) → Elite Four only if a species needs it.

## Opportunities (trigger → action)

| Trigger | Action | Status |
|---|---|---|
| Dex ≥ 40 | Amulet Coin (Route 16 gate aide) → GIVE to battle lead | ✅ done |
| Own a FALSE_SWIPE_LEARNER | Park it in the party so it levels passively; train to the learn level (Cubone L33) before it evolves | ✅ done |
| Dex ≥ 50 | **Exp Share** from Route 15 gate 2F aide → give to current trainee | ✅ done |
| Fuchsia reachable | **Good Rod** (Fuchsia fishing guru) → fishing encounters annotations | ✅ done (all 3 rods) |
| Snorlax cleared (Route 12) | **Super Rod** (Route 12 fisherman's house) | ✅ done |
| Badge 5 + Surf | Annotate surfable water routes (19/20/21, Routes 4/24 pools) for water dex | 🔜 open NOW |
| Safari Zone entered | HM03 was here (✓ have it); **Gold Teeth → HM04 Strength** | with Safari milestone |
| Own Pikachu + Power Plant annotated | Electabuzz/Zapdos area (needs Surf ✓) | after annotation |
| Evolution stones (Celadon dept. store) | Stone evolutions for living dex (Vulpix→Ninetales etc.) | M8 evolution pass |
| HM02 Fly (Route 16 house, needs Cut) | Teach Fly (Pidgeotto) — fast travel for the planner | when nav supports it |
| Vs Seeker rematch income | Blocked on an eligibility mystery (fires but "no interested trainers") — see KNOWN_LIMITATIONS; next probe is per-trainer defeated flags | 🔴 blocked |

Keep this file honest: when a trigger fires or a fact changes, update the row
in the same commit as the work.
