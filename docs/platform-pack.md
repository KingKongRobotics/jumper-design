# Mechanical platform packs

A mechanical platform pack describes CAD interfaces for physical shell engineering. It is separate from the display robot profile in robots/jumper/profile.json.

No manufacturing CAD platform archive is distributed in this public edition. Obtain authorized inputs for the exact hardware revision before starting physical shell work. Existing platform_pack.py tooling can inspect and install a user-supplied archive; run `python scripts/platform_pack.py --help` for commands. Installed packs belong in ignored .local/platforms, never in a generated .skin.

Display-only packaging and scene creation use the included Jumper baseline and original skin; they do not need a manufacturing CAD pack. A package loading successfully does not establish mechanical fit.
