# Fixtures

mGBA savestates (`.ss1`) for headless tests, all produced with FireRed USA **1.0**
(upstream pokebot-gen3 test states are v1.1 and therefore unusable here).

| File | How it was produced |
|------|--------------------|
| `m0_title.ss1` | `python -m dexbot.m0_boot` — fresh boot, A-mash to title screen (CB2_TITLESCREENRUN), +600 settle frames. |
| `m1_game_start.ss1` | `python -m dexbot.new_game` — fresh boot → New Game → Oak intro (A-mash) → naming screens handled via 3×A + START + A (player/rival named "AA") → first controllable overworld frame in player's house 2F, map (4,1) @ (6,6), money 3000, empty party. |
| `m4_post_lab.ss1` | `python -m dexbot.openings` — after starter (Squirtle) + winning the lab rival fight, still inside Oak's lab. This is the "post-Oak's-lab" state used by the M3 acceptance test. |
| `m4_pokedex.ss1` | Same run, final state: Pokédex owned, parcel delivered, 10 Poké Balls bought, standing in Viridian Mart. |

Regenerate any fixture by re-running the listed command from the project root.
