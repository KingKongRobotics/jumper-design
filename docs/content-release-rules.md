# Default rules for content delivery

These are confirmed project defaults. Apply them directly to future generation, migration, updates, and releases; do not ask the user to repeat each requirement. Change them only when the user gives a conflicting new requirement. Do not revert to an older approach for convenience.

## Files delivered to users

- Keep the formal directories flat: `library/skins/<stable-id>.skin` and `library/maps/<stable-id>.map`, with no per-work subfolders. Display titles remain separate from archive filenames.
- One file is the complete unit for import, sharing, and download. It includes models, relative assets, a manifest, and `preview/preview.png`; it must not depend on a sidecar image or folder.
- `.skin/3` is display only and contains the complete robot and confirmed whole-robot colors. Deliver print STL, 3MF, G-code, and STEP separately. Parts whose colors were not requested retain the selected baseline and the user's latest color decision.
- `.map/2` contains a complete default robot, spawn, environment, and props. Its thumbnail shows the environment only, without a robot. Check the combined robot view separately.
- Use a formal display name; do not pile concept letters, process steps, or experiment counts into the title. Map IDs must not carry a `be-` prefix; record origin in the manifest.
- The showcase platform, open grounds, obstacle course, and arena were removed from this project's formal library. Do not restore them during a batch rebuild.

## Visual fidelity

- Read the physical layer, independent Web visual layer, materials/textures, decorations, and props together. Exporting collision bodies is not a complete appearance export.
- Preserve lawns, paving, wooden floors, markings, plants, furniture, and prop details. Do not replace an existing design with a generic grid floor.
- For BE procedural scenes, execute the actual Web construction functions, including instance matrices, every geometry face group, vertex colors, and line segments. Attach prop visuals in the corresponding physical body's local coordinates. For the bedroom, retain the checked native XML, textures, and flex.
- New visuals have zero mass and no collision. Compare mass, inertia, joint parameters, and body poses before and after adding visuals; preserve original collision parameters.
- App-driven droplets, pouring, and contact flashes belong to the app; do not claim they are implemented by a static map.

## Thumbnails and package previews

- Render the environment from the final map without the robot. Frame the whole scene with margins, clear original terrain colors, and legible relationships between objects and ground. Avoid overexposure, clipping, and black corners.
- Write the image back into the package and update manifest hashes, package hash, indexes, and any consumer-managed download copies included in the delivery. Derive preview images from the final package; external images are temporary caches only.
- Open generated local package previews and verify that the displayed thumbnail and downloadable package refer to the same version. A website consumer must separately refresh its own pages when it integrates these packages.

## Required before release

1. Generate in a candidate directory; pass protocol, resource, platform, thumbnail, and hash checks.
2. Actually compose/load the complete robot and check spawn; verify that visual migration leaves physical parameters unchanged.
3. Compare each scene with its Web source and inspect real thumbnails and combined robot views. Automated checks do not replace visual inspection.
4. Check flat directories, in-package thumbnails, any delivered download-copy SHA, consistent names, and the removal list.
5. Switch the formal library while retaining Git/LFS history. Regenerate and open local package previews, then report completion.

Automatically reject missing in-package thumbnails, format/hash errors, failed platform/model checks, old directory indexes, release overwrite conflicts, map `be-` prefixes, and restoration of removed maps. Reject BE maps lacking a real Web visual export, visuals with collision or mass, and visual counts inconsistent with source records. Old formats remain read-compatible but do not automatically qualify for the formal library.

Entry points: `scripts/import_be_maps.py` → `scripts/export_map_collection.py` → `scripts/publish_content.py`; use `scripts/content_gallery.py` for local package previews. See the [content package protocol](content-packages.md), [Git storage rules](git-storage.md), and [scene-by-scene visual audit](map-visual-audit.md).

## New challenges and authored maps

- Store authored sources in `library/map-sources/authored/<id>/`; formal user files remain flat under `library/maps/`. Batch export prefers an authored source with the same ID, so the ground-level pouring challenge does not revert to its tabletop version. Retain the original BE source.
- Design a new narrow bridge for the current robot's static collision width and record clearance. Static width or path-clearance checks do not establish a successful gait. Check physical collision height and continuity on slopes and turning platforms.
- By default, place the pouring bottle, cup, and tray on the ground, removing both the tabletop and its barriers from visual and collision geometry. Appearance placement of a new prop must not change its original inertia.
- Put challenge instructions in an in-package README.md. Give target areas and movable objects stable MJCF names. Scoring, liquid effects, and controllers remain app responsibilities. Do not add mandatory execution semantics to `/2` without a protocol version bump.
- Record real provenance and an `authoredGround` marker for authored maps, and preserve designed ground in thumbnails. Do not misrepresent them as direct exports of original BE Web scenes.

## Confirmed Web color standard

Generate and accept all scenes according to the [be-web/1 color and visual standard](web-appearance-standard.md). Every new `.map` must include a hash-verified `visual-appearance.json` with fixed sRGB handling, ACES 0.95, original Web sky/key lighting, and complete materials. Do not brighten all scenes or automatically darken imported ones. Render the package thumbnail with the real Web importer; native MuJoCo rendering is for a separate simulation check. Disable distance fog for panorama thumbnails to prevent washed-out content; retain original Web fog in formal interaction. Before release, compare source and imported views from the same angle and confirm physical parameters are unchanged.

## External website consumer acceptance

The following checks belong to a separate website integration task. They do not authorize this workflow to edit website code, accounts, pages, or uploaded works. The current repository task ends at validated, published packages and local preview evidence.

- Updating local `library/maps` does not mean the website's “My Scenes” has changed. For fixes to uploaded content, compare the current account's actual downloaded package SHA with the formal library SHA; matching names, thumbnails, or local files alone are insufficient.
- For an existing work the user asked to fix, use that work's package replacement interface, retaining its work ID, interaction relationships, and historical files. Inspect before applying; preserve the old package on failure. Do not create another work with the same name or touch the recycle bin or other accounts.
- After replacement, download again and verify SHA, in-package `visual-appearance.json`, and preview. Test the real Web path from package read through WASM attach to material mapping, then switch between built-in and imported scenes at the same view in the actual simulator. A standalone acceptance page cannot establish that the website change took effect.
- New scenes from BE Web retain the agreed sRGB, light, material, and ground visual scope. Do not guess a global conversion for numeric RGB in older third-party MJCF. Re-export missing original Web visuals from a verifiable source.
