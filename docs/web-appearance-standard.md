# Scene color and visual standard: be-web/1

The user confirmed the current built-in BE UNLIMITED Web scenes as the visual reference. Generation, export, and reimport must follow the same rules. Do not brighten scenes by eye or present a native MuJoCo render as proof of Web fidelity.

## Fixed rendering rules

- Input colors: Web material CSS/hex and textures are sRGB; shading operates in linear space and output is sRGB. Numeric Three.js RGB values are linear by default; do not pass normalized exported hex channels directly to a linear constructor.
- Tone mapping: ACES Filmic, exposure 0.95, background `#eef1ed`.
- Sky light: white, ground color `#90988b`, intensity 1.7. Warm-white key light: `#fff8ed`, intensity 2.4, position (1.5,-2,4). PCF shadows, 2048², bias -0.0003, normalBias 0.002.
- A standard package uses full Web default lighting at scale 1. Do not automatically lower it to 0.6 because a scene is imported. The Web standard visual does not stack approximate MJCF lights.
- Normal interactive fog: `#eef1ed`, near 6, far 16. Panorama thumbnails alone disable distance fog to prevent distant camera views from washing out content; all other colors, materials, and lighting remain identical.
- Preserve roughness, metalness, colored emissive, emissiveIntensity, transparency, visible faces, unlit, and flatShading. Do not merge groups only by color. Preserve original vertex normals and correctly read independent normal indices.

## In-package declaration and compatibility

`.map` remains `kk-scene-package/2`. Its `visual-appearance.json` uses `kk-web-appearance/1` and is SHA-bound by the existing `files` manifest; material dictionary keys correspond to MJCF material names, with attach prefixes stripped by the loader. See `schemas/web-appearance-v1.schema.json` and `src/shellflow/web_appearance.py`.

This is an optional Web visual extension and does not alter the native physics protocol. Every **new map released by this project must include** the standard; a missing or unknown visual version fails publication. Older MJCF-only maps remain readable but cannot claim visual fidelity. A Web importer supporting the extension reconstructs its materials. Native MuJoCo has different material and lighting models and provides only an approximate MJCF display, with no pixel-for-pixel cross-renderer guarantee.

The original bedroom Web scene uses numeric linear RGB: convert it to sRGB when exporting the sidecar; retain the original Web tint on textures. Do not apply the same mechanical conversion as in other hex-based scenes. The ground-level pouring challenge retains its ground design; its geometry differs from the original tabletop scene, so exclude it from same-image error rankings.

## Reproducible generation and acceptance

Run from this project's root. Node uses BE project dependencies and Python uses this project's simulation dependencies:

```text
python scripts/import_be_maps.py
python scripts/build_ground_pouring.py
python scripts/build_authored_challenges.py --sources-only
node scripts/export_web_visuals.mjs ../BE-UNLIMITED/be-unlimited outputs/web-appearance-audit
python scripts/prepare_web_appearance_audit.py
node scripts/prepare_web_appearance_audit.mjs
python outputs/web-appearance-audit/server.py
```

Open local port 8881 in a browser. Compare left and right images from the same camera and click “Generate all in-package thumbnails.” The formal Web importer reconstructs data from actually compiled MJCF; the left side uses the real Web scene, while the bedroom runs the original Web bedroom code. Thumbnails exclude the robot. Then run:

```text
python scripts/export_map_collection.py --output outputs/reviewed-maps --library outputs/reviewed-library --preview-dir outputs/web-appearance-audit/renders
python scripts/prepare_web_appearance_audit.py --robot-library outputs/reviewed-library
```

Click “Generate all whole-robot composite images,” inspect spawn and visuals, and verify that mass, inertia, joints, and poses did not change. Switch formal files, indexes, and pages only after every check passes. Without `--preview-dir`, standard map export fails instead of silently producing a native-rendered thumbnail.

## Acceptance results for this run

All 12 packages passed native whole-robot loading and spawn checks. All 12 maps retained the previous rigid-body mass, inertia, pose, and joint limits/axes/damping. Eight original Web scenes were compared from the same camera. Mean absolute RGB channel errors (0–255, one fixed-camera sample) were: home 0.0182, bedroom 0.4215, soccer field 1.6654, street-corner plaza 0.3796, warehouse challenge 0.0092, table-tennis recovery 0.0187, mine survey 0.1800, and litter scooping 0.0049.

These values include the background and are not universal visual-quality scores; visual inspection was also performed. Thin capsules replacing lines, sampled vertex-colored triangles, transparency sorting, and different geometry grouping leave small residuals, especially at the soccer field. Pixel identity is not claimed. Native simulation loading, Web appearance fidelity, and app/physical execution are separate acceptance checks.

## Optional Web integration

The BE UNLIMITED source exporter is an optional integration requiring a separately available website checkout. It is not required to load or validate the public packages. The public examples include their complete visual declarations and assets. This repository does not distribute the website; a third-party consumer must implement the documented rendering contract.
