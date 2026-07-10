# Fixtures

mGBA savestates (`.ss1`) for headless tests, all produced with FireRed USA **1.0**
(upstream pokebot-gen3 test states are v1.1 and therefore unusable here).

| File | How it was produced |
|------|--------------------|
| `m0_title.ss1` | `python -m dexbot.m0_boot` — fresh boot, A-mash to title screen (CB2_TITLESCREENRUN), +600 settle frames. |
| `m1_game_start.ss1` | `python -m dexbot.new_game` — fresh boot → New Game → Oak intro (A-mash) → naming screens handled via 3×A + START + A (player/rival named "AA") → first controllable overworld frame in player's house 2F, map (4,1) @ (6,6), money 3000, empty party. |
| `m4_post_lab.ss1` | `python -m dexbot.openings` — after starter (Squirtle) + winning the lab rival fight, still inside Oak's lab. This is the "post-Oak's-lab" state used by the M3 acceptance test. |
| `m4_pokedex.ss1` | Same run, final state: Pokédex owned, parcel delivered, 10 Poké Balls bought, standing in Viridian Mart. |
| `m5_five_species.ss1` | `python -m dexbot.catching` from `m4_pokedex.ss1` — Rattata, Pidgey, Caterpie, Weedle, Pikachu caught; dex owns 6 species. |

| `m7_bridge.ss1` | `python -m dexbot.story cross_nugget_bridge m7_post_badge1_dex.ss1 m7_bridge.ss1` — Nugget Bridge cleared (rival + 5 trainers + Rocket). |
| `m7_mt_moon_cleared.ss1` | `python -m dexbot.story clear_mt_moon m7_badge_brock.ss1 m7_mt_moon_cleared.ss1` — Helix Fossil, east exit open. |
| `m7_ss_ticket.ss1` | `python -m dexbot.story visit_bill m7_bridge.ss1 m7_ss_ticket.ss1` — Bill helped, SS Ticket obtained. |
| `m8_post_snorlax.ss1` | Copy of the live profile's `current_state.ss1` right after `catch_snorlax` (badges 4, dex 34, Route 12 south end). Used to rebuild nav-graph epoch 4 with the Snorlax tile cleared. |
| `m7_badge_koga.ss1` | Koga campaign from the live `current_state.ss1` (2026-07-10, dex 41): one Route 11 Vs Seeker income lap (→ ₽11,676), then `beat_koga` (assemble_party at Vermilion PC, 9 Hyper Potions, Fuchsia gym gauntlet + Koga). Badge 5 set, party alive. |
| `kit_campaign_final.ss1` | Catch-kit campaign from `m7_badge_koga` state (2026-07-10): Amulet Coin given to Blastoise, then `train_false_swipe` (Route 11 wild grind, level-balancing strategy) — Cubone L15→33, learned False Swipe, evolved to Marowak; Parasect L33 learned Spore en route. Applied to the live profile. |

Regenerate any fixture by re-running the listed command from the project root.
