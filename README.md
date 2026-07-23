# dexbot — autonomous living-dex bot for Pokémon FireRed

An autonomous bot that completes a single-cart living dex in Pokémon FireRed (USA):
catch one of every species obtainable without trading (~122 species), progressing
through the story as far as needed. State is read from emulator memory only (never
pixels); deterministic skills execute frame-perfectly, and an optional LLM reasons
only at objective/failure boundaries.

Full brief, architecture, and milestones are in [CLAUDE.md](CLAUDE.md).
Progress log: [DEVLOG.md](DEVLOG.md) · Roadmap: [ROADMAP.md](ROADMAP.md) ·
Honest gaps: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## What you need to bring

- **A ROM you own.** Not included and never will be. Place FireRed USA 1.0 at
  `roms/firered.gba`; startup verifies MD5 `e26ee0d44e809351c8ce2d73c7400cdd` and aborts otherwise.
- **[40Cakes/pokebot-gen3](https://github.com/40Cakes/pokebot-gen3)** as a sibling — this repo
  is an extension layer that imports its `modules`. Clone it alongside (gitignored here).
- **Test fixtures.** The `.ss1` savestates used by the test suite are **not** distributed
  (they are memory snapshots of the copyrighted ROM). Regenerate them from your own ROM —
  see [fixtures/README.md](fixtures/README.md).

## Layout

- `dexbot/` — the skill library, planner, and emulator glue (L0–L2)
- `data/` — static knowledge base built from the pret/pokefirered decomp (encounters, evolutions, trainers, nav graph)
- `tests/` — headless pytest checks (need regenerated fixtures)
- `docs/` — design notes and assets
- `patches/` — minimal upstream-touching diffs for the pokebot-gen3 fork

## License

Not yet chosen. Because `dexbot/` imports pokebot-gen3 at runtime, any license here
must be compatible with pokebot-gen3's terms — pick one before relying on reuse.
