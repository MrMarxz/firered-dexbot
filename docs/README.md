# docs/ — offline reference cache

Bulbapedia pages cached as raw wikitext on 2026-07-06 (source:
`https://bulbapedia.bulbagarden.net/w/index.php?title=<page>&action=raw`), so
development never needs a web search for game facts. These are *development
references only* — runtime game facts live in `data/` (see `data/README.md`).

| File(s) | Page | Why |
|---------|------|-----|
| `bulbapedia/walkthrough_index.wiki`, `walkthrough_part_1..20.wiki` | Walkthrough:Pokémon FireRed and LeafGreen | Story progression, required flags/items per area (M4, M6, M7). |
| `bulbapedia/Catch_rate.wiki` | Catch rate | Gen III capture formula for M5 ball selection math. |
| `bulbapedia/Safari_Zone.wiki`, `Kanto_Safari_Zone.wiki` | Safari Zone / Kanto Safari Zone | Gen III safari mechanics (bait/rock probabilities, step budget) for M8. |
| `bulbapedia/Badge.wiki` | Badge | Field-move badge gating (validates `data/dependencies.json`). |
| `bulbapedia/FireRed_LeafGreen_Versions.wiki` | Pokémon FireRed and LeafGreen Versions | Version exclusives / trade-only species — defines the ~124 single-cart obtainable set. |
| `bulbapedia/Kanto_Pokedex.wiki` | List of Pokémon by Kanto Pokédex number | Dex numbering cross-reference. |
| `bulbapedia/Poke_Flute.wiki` | Poké Flute | Snorlax roadblock details (M6 dependencies). |
| `bulbapedia/Vs._Seeker.wiki` | Vs. Seeker | Trainer rematch money farming (M8 economy). |
