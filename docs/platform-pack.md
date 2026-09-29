# Mechanical platform packs

A mechanical platform pack describes CAD interfaces for physical shell engineering. It is separate from the display robot profile in `robots/jumper/profile.json`.

## Included engineering reference pack

`platforms/bundles/original-robot-v1.platform.zip` is included through Git LFS at the repository maintainer request. It is an engineering reference, not a certified manufacturing release. Historical archive metadata retains `redistribution_status=unconfirmed`; inclusion does not grant a new source-asset license, and the repository Apache-2.0 license must not be assumed to cover these assets.

The archive is 22,953,549 bytes (about 21.9 MiB), containing 38 assets totaling 63,625,531 bytes. It includes original STEP/BREP, CAD feature metadata, a nonplanar interface ring, four primary posts and two auxiliary posts, plus attachment references. Interface STL files are engineering components, not completed character print deliveries. No example AMS 3MF or G-code has been added.

## Install and verify

From the repository root:

```sh
python scripts/platform_pack.py install --archive platforms/bundles/original-robot-v1.platform.zip --destination .local/platforms
python scripts/check_mechanical_platform.py
```

The installer verifies every declared file and rejects an existing installation rather than replacing it. Installed packs stay in ignored `.local/platforms/`, never inside `.skin`. To inspect an existing installation, run the second command only. To test an independent installation, use another destination and pass its platform directory to the checker with `--platform-dir`.

`platforms/catalog/original-robot-v1.json` pins the manifest and archive hashes. The checker compares the actual original STEP with the current robot profile, checks installed assets, and loads the seven interface STL modules. These checks establish data availability and identity, not CAD functional correctness or physical fit.

## Coordinate and compatibility boundaries

- Units are millimeters. The archived interface manifest defines front as -Y and up as +Z. Original CAD +Z accesses the holes from below. Preserve the original coordinates and use the selected robot profile's assembly transform; do not reuse a historical robot transform.
- The original STEP hash matches the current Jumper profile's source reference. This is provenance agreement, not proof that the entire current hardware revision has the same mounting interface.
- Historical metadata retains original machine paths and validation statements. Resolve assets through `platform.json`, not those paths. Geometry bytes and original reports are preserved; old reported checks have not been rerun by installation.
- The 164 protected functional faces and six-post layout belong only to this exact source. Do not apply face indices to another STEP or revision.
- The two auxiliary mounting functions remain unconfirmed. `six_hole_interface_validated=false` and `physical_fit_tested=false` remain unchanged in the current robot profile.
- A complete internal-component keepout model, lower-shell mating validation and full-motion envelope are still missing. Do not invent these from the display meshes or claim interference checks passed.

Before redistributing these source assets, establish the applicable rights and review legacy metadata portability. Before a printable-shell acceptance claim, validate the selected hardware's interfaces, obtain internal keepouts, perform CAD/mesh engineering and slicing checks, and then conduct physical fitting. Restoring this pack enables engineering to start; it does not implement an automatic arbitrary-shell manufacturing backend.

Display-only packaging and scene creation use the included Jumper baseline and original skin; they do not need this manufacturing CAD pack.
