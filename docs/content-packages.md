# `.skin` and `.map` content package standard

This file, `schemas/*-package.schema.json`, `src/shellflow/*_package.py`, and contract tests together define the exchange agreement. Producers must pass the reference validator; consumers must perform equivalent checks. JSON Schema checks manifest shape only, not asset hashes, XML resources, robot structure, or capabilities.

## File identity and versions

| External file | Root ZIP manifest | Protocol | Purpose |
|---|---|---|---|
| `name.skin` | `skin-package.json` | `kk-skin-package/1` | Historical whole-robot appearance package containing print source |
| `name.skin` | `skin-package.json` | `kk-skin-package/2` | Historical package additionally declaring lower-shell visual color |
| `name.skin` | `skin-package.json` | `kk-skin-package/3` | Display-only whole-robot appearance, optionally declaring lower-body and limb visual colors |
| `name.map` | `scene-package.json` | `kk-scene-package/1` | Independently attachable terrain and props |
| `name.map` | `scene-package.json` | `kk-scene-package/2` | Terrain, props, and a directly loadable in-package default robot |

Both are standard ZIP files with the manifest at the root and no enclosing directory. Consumers check both extension and manifest protocol; renaming cannot establish compatibility. Legacy `.scene.zip` can be imported and repacked as `.map`, retaining internal bytes and semantics.

`id` and `version` identify a `.skin` work version; exact dependencies also lock the archive SHA256. A `.map` is identified exactly by manifest `id` plus archive SHA256. `/2` makes the default robot mandatory through an explicit version change; `/1` keeps its original meaning. Filenames may change and do not determine identity.

Formal library filenames use stable ASCII IDs (`library/skins/<id>.skin` and `library/maps/<id>.map`). Human-readable English titles are separate manifest/index values. Renaming an outer archive does not alter internal bytes or identity; verify its archive SHA after moving it.

The reference packer fixes file order, timestamps, and permissions when rebuilding identical content. Repacking another producer's archive may change ZIP compression bytes and the archive SHA, but every internal file must remain byte-identical. Never recalculate hashes to conceal a modification. Changed assets require a new work version.

Changes requiring a protocol version bump include unit/coordinate semantics, required fields, collision or inertia policy, embedded challenge execution, and mandatory behavior old readers cannot understand. Reject unknown protocols rather than silently falling back to apparently successful old behavior.

## Public commands

Run `python scripts/shellflow.py` from the repository or `shellflow` after installation. Packaging and structural checks use the standard library; `--mujoco` requires simulation dependencies.

```sh
python -m pip install -e ".[sim,dev]"

# Scene description -> compile MJCF/assets -> package with a verified robot -> one .map/2
python scripts/shellflow.py export-map examples/maps/obstacle-course.scene.json --output outputs/obstacle-course.map

# New tasks default to jumper. Assemble the whole robot, then package it for display.
python scripts/shellflow.py assemble bee-demo --shell delivery/print/shell.stl
# Lower-body and limb visual colors may be declared at assembly; print source is separate.
python scripts/shellflow.py export-skin --simulation workspaces/bee-demo/delivery/simulation --profile robots/jumper/profile.json --id bee-a --title "Honeybee A" --version 1.0.0 --author "Actual Author" --license "Actual License" --output outputs/bee-a.skin

# Before delivery: check assets, structure, platform, and actual URDF/MJCF loading.
python scripts/shellflow.py verify-package outputs/bee-a.skin --profile robots/jumper/profile.json --mujoco
python scripts/shellflow.py verify-package outputs/obstacle-course.map --profile robots/jumper/profile.json --capability rigid --capability jumper --mujoco

# Import to new directories after validation; do not overwrite an existing delivery.
python scripts/shellflow.py import-package outputs/bee-a.skin --profile robots/jumper/profile.json --destination outputs/imported-bee
python scripts/shellflow.py import-package outputs/obstacle-course.map --destination outputs/imported-map

# Repackage after cross-platform transfer while preserving every internal file byte.
python scripts/shellflow.py repack-package outputs/obstacle-course.map --output outputs/returned.map
```

Unmigrated v1 `.skin` archives keep their original profile. This migration's products bind `robots/jumper/profile.json` per the [source update](jumper-source-update.md). Existing `jumper-v1-6` robot packages and historical reports remain bound to the old profile, regardless of skin migration.

Enter real authorship and license values for `--author` and `--license`; example values grant no rights. Display and baseline assets retain their original licenses. Export and import destinations must be new paths; failures return nonzero status and JSON errors without overwriting old results.

Scene authors can use installed `mjscene new/build/export` or `python -m mjscene` for legacy `/1` environment packages. This repository's `export-map` alone verifies a default `.skin/3` and packages `/2` with a whole robot. The default is library Silver Armor Guardian on `robots/jumper/profile.json`; `--default-skin` and `--profile` can override it. Legacy `.scene.zip` remains readable.

## Required `.skin` contents and restrictions

```text
skin-package.json
provenance/profile.json
provenance/baseline.xml
assembled/<platform-id>/
  robot.urdf
  robot.xml
  scene.xml
  meshes/...
  simulation-report.json
  preview-pose.json              retained if present at source
  preview.png / README.md        retained if present at source
preview/preview.png              supplied via --preview
```

This is the new `/3` layout. Historical `/1` and `/2` additionally require `print/shell.stl` and may contain `print/ams.3mf`. Newly produced `/3` **must contain no `print/` files**. STLs under `assembled/.../meshes/` that the complete robot actually references are display meshes, not print sources, and must remain. Baseline profile meshes no longer referenced by the assembly may remain if their package bytes match profile hashes. Other unreferenced meshes are rejected; renaming a print part into `meshes/` is invalid. `/3` `source.shell_sha256` still records the original print-shell SHA from the assembly report for provenance, but does not make the print file available in the package. `export-skin` can take just simulation and profile; if `--shell` is also given, its byte hash must match the assembly report. Legacy `--ams` remains callable but `/3` neither reads nor packages 3MF.

A complete robot is mandatory. The validator compares actual bodies/links/joints with the in-package baseline, checks that only profile-designated visual slots changed, and re-exports and compares URDF from the actual MJCF. With trusted `--profile`, it also checks original profile bytes and baseline/original mesh hashes; a self-declared replacement baseline cannot impersonate compatibility.

Without `--profile`, a self-contained structural check is possible, but `trusted_platform_profile=false` means mechanical platform identity is uncertified. Applying a skin on a runtime platform requires the current trusted platform and a match; preview alone is not evidence that it can replace a real part.

The current default baseline is `jumper`; historical `jumper-v1-6` and `hexa-v1` remain supported and their old packages retain their profiles. Each profile binds its own mechanical source SHA and transform; revisions are not interchangeable. `jumper/urdf/jumper.urdf` has 41 links and 22 movable joints, all indexed such as `LF_J0_joint`. The importer adds a virtual `floating_base` root and retains source mechanics, inertia, and color defaults. New registration checks only the `upper_shell_link` seam, not the six-hole mechanical interface or physical fit.

Assembly/simulation units are meters; print STL keeps original CAD millimeters. AMS bed placement is not an assembly transform. The `jumper` source has no active sensor, camera, or actuator elements. Undeclared visual parts, joints, collision, inertia, and physics defaults retain the baseline. Controllers must bind the actual indexed joint map; old semantic names and controllers cannot be assumed reusable. The display pose is remapped from historical raw `preview-pose.json` and is separate from app reset/control pose; it is static display data, not a target. `LM_J0_joint` source limits are [-0.75, 1] rad; display 0.0012 rad needs no clamp, and the importer rejects the obsolete +0.75 lower bound. `RF_J4` display 0 rad is clamped to the source lower bound 0.1 rad. See [jumper source update](jumper-source-update.md) for source hashes and migration checks.

All `/1`, `/2`, and `/3` use `collision_policy=baseline_preserved`, `inertia_policy=baseline_preserved`, `physical_fit_tested=false`, and `physical_dynamics_validated=false`. Physical shell changes need future explicit protocol support.

`/2` is only for explicit lower-shell visual recoloring. Producers call `assemble(..., lower_shell_color="#RRGGBB")` or `assemble --lower-shell-color '#RRGGBB'`, changing only `base_link`'s `base_link_visual` `rgba` in assembled MJCF; regenerated whole-robot URDF must match. `simulation-report.json` and root manifest must declare identical `visual_overrides`:

```json
[{"link":"base_link","geom":"base_link_visual","rgba":[0.07058823529411765,0.20392156862745098,0.33725490196078434,1.0]}]
```

This is the only allowed `/2` target and field. `/3` requires `visual_overrides`, either an empty array or per-item `{link, geom, rgba}` for nonshell lower-body/limb parts. Each target must be a unique noncollision baseline visual geom; duplicates, the replaced upper-shell visual, and collision geoms are forbidden. On historical `split_base` platforms where lower and upper visuals share a link, only the profile's original visual geom may be recolored. RGBA components must be finite from 0 to 1 and alpha exactly 1. Manifest and `simulation-report.json` declarations must match exactly, as must each MJCF color; URDF must be fully exported from that MJCF. The validator restores declared colors and compares the whole MJCF tree, rejecting undeclared visual changes or any change to joints, collision, inertia, or other physics. Profile bytes and SHA remain unchanged. `/1` and `/2` remain readable; old consumers must reject unknown `/3`. `schemas/skin-package-v3.schema.json` defines manifest shape; reference validation against a trusted profile establishes mechanical authenticity.

`/3` has no `manufacturing` field and offers no print capability. Source report hashes for the print source, platform, and production code remain. If an old assembly report lacks `visual_overrides`, export derives an in-package copy with an empty array without changing its source directory. Historical `passed` in that report is not manufacturing certification. The source report inventory may explicitly omit `preview.py`; all other required data must match, and the package does not carry the script.

This version cannot generate manufacturable geometry from text alone. Freeze print files and run `assemble` under the engineering process before `export-skin`.

## Required `.map` semantics

`kk-scene-package/2` keeps upstream `scene-package.json`, `scene.xml`, `assets/`, and optional independent `props/`, and requires `robot/`. That subtree contains a verified complete `.skin/3` expanded at original relative paths: `robot/skin-package.json`, `robot/assembled/<platform>/robot.xml`, `robot.urdf`, meshes, report, and `robot/provenance/`. Top-level `robot` binds skin ID, platform ID, and profile SHA; both layers' assets enter the top-level hash inventory, and the validator reruns full skin checks. Authoring input `scene.json` need not ship. Legacy `/1` environment packages remain readable but fail the new requirement for a map with its own robot.

- Terrain/object positions use meters in a right-handed Z-up world with zero heading along +X. `spawn.yaw` **remains in degrees**, not another protocol's radians. MJCF quaternion order is wxyz; consumers must convert explicitly.
- `/2` requires `spawn`; if omitted, the generator writes default position `[0,0,0]` and zero-degree heading. Authors must check spawn safety for each map. `spawn.position.z` is ground height; the reference loader adds the skin preview pose's `base_height_m`. With `spawn.site`, use that site's world coordinates in the attached, compiled model.
- With `props[].file`, a prop is an independent model using `initPositionRelativeToRobot`. Without `file`, it is a world body whose `position` is absolute world position. Do not mix these meanings.
- Consumers load the packaged robot by default, or may verify and substitute a same-platform `.skin`; map world and spawn remain separate. Compose with MJCF `<attach>` or equivalent `MjSpec.attach`, not XML concatenation that overrides host compiler/default/option. `physics` is advisory, not an automatic host control-step override. `compose_default` compiles the actual default robot with the scene and checks spawn pose and `forward`.
- Scene MJCF forbids option, include, plugin, extension, and DTD/entity declarations; external model references are checked recursively. Every file reference, including texture faces, must resolve inside the package; MuJoCo basename fallback to a similar file is invalid.
- The validator derives required capabilities such as flex/hfield from actual XML and checks explicit requirements. Unsupported consumers must reject execution; they may offer a clearly labeled static preview but cannot silently drop objects.
- This version produces rigid flat-ground/obstacle scenes. Challenge scoring, seed, reset, input replay, and app behavior are not inserted into existing `/1`; a future experiment configuration can refer to an exact map SHA.

Repeatable `--capability` declares actual consumer capabilities. `/2` also needs robot platform ID, plus `hfield`/`flex` when present. Omitting capabilities checks files only, without claiming compatibility with a consumer. Mechanical trust still needs `--profile`; a name cannot replace hash comparison.

## Shared mandatory checks

Paths are NFC Unicode, case-unique POSIX relative paths. Reject backslashes, drive letters, absolute paths, `..`, empty segments, symlinks, Windows device names, trailing dots/spaces, duplicates, and file/directory conflicts. Manifest hashes must match actual bytes; required resources cannot be omitted and undeclared files cannot be carried. Maps permit unlisted README.md/LICENSE, but other runtime resources must be inventoried.

ZIP accepts stored/deflate only, with no encryption or executable extensions. General read budgets are 512 MiB compressed, 1 GiB expanded, 256 MiB per file, and 4096 entries. Maps retain smaller upstream limits: 64 MiB compressed, 192 MiB expanded, and 256 entries; `/2` includes the expanded skin within those limits. Reject excess size explicitly rather than weakening checks or trimming resources. Servers/consumers may impose lower limits with clear errors.

JSON rejects duplicate keys and nonfinite numbers; XML must be UTF-8. Publish to a new directory only after validating the entire package, and atomically switch a runtime platform only after all checks pass. Keep the previous robot/scene on failure. File processing does not execute packaged programs.

## Consumer integration and round trips

Python reference entry:

```python
from pathlib import Path
from shellflow.packages import verify_package, import_package, repack_package

report = verify_package(Path("course.map"), platform_profile=Path("robots/jumper/profile.json"), capabilities={"rigid", "jumper"}, mujoco=True)
import_package(Path("course.map"), Path("new-import-directory"), platform_profile=Path("robots/jumper/profile.json"), capabilities={"rigid", "jumper"})
repack_package(Path("course.map"), Path("returned.map"))
```

Native composition example, actually attaching, compiling, and forwarding a skin and map together:

```sh
python examples/load_skin_map.py --skin outputs/bee-a.skin --map outputs/obstacle-course.map --profile robots/jumper/profile.json --output outputs/combined-load.json
```

This example substitutes an external `.skin` for the map default and checks that robot joint parameters, sensor/actuator names, and global options remain unchanged before and after composition. It records `spawn_applied=false` and performs no reset, policy rollout, or app control. The packaged default robot is checked with `compose_default`, which applies spawn and skin preview pose and rejects spawns clearly intersecting nonground objects. Neither simplified example attaches independent `props[].file` models; a full consumer must implement that part of the protocol.

Web consumers must unpack under the same rules and place verified models/assets at original relative paths in MuJoCo WASM VFS. Run MJCF; URDF is for robot-ecosystem exchange. Before loading a map, check basename conflicts against robot assets and unload previous map resources. Declare Web material, heightfield, and flex display capabilities independently; Python loading does not prove Web support.

The repository supplies generators, a Python reference consumer, schemas, and tests. This work does not modify BE UNLIMITED or kk-rl-mjlab UI/upload entry points. Only after those products integrate these interfaces and pass the same acceptance matrix may they claim `.skin` / `.map` support. Adding extensions to a community attachment allowlist alone does not make third-party content safe to run.

At minimum a new consumer must pass generation → validation → import → repack → reload, internal byte identity, rejection of platform mismatch, missing assets/bad hashes/path traversal, rejection of unknown required capabilities, preservation of host parameters after map attach, and failure without damaging existing content. CI has simulation-free contract tests on Windows/Linux/macOS and a separate simulation-dependency job; CI configuration does not prove remote jobs have run successfully.

Identical geometry and dependency versions do not guarantee bitwise-equal floating trajectories across engines/hardware. Evaluation needs fixed inputs, seeds, versions, and reasonable error metrics. `--mujoco` here proves actual compilation and `forward`, not policy training quality or physical fit.

## Portable thumbnails

Display skins `/3` and maps `/2` store thumbnails at ZIP path `preview/preview.png`, with size and SHA256 in existing `files["preview/preview.png"]`; the validator checks PNG format. No new top-level manifest field or robot/physics/scene loading semantics are added. Old packages may omit previews; new formal library `/2` publication requires one and rejects absence.

Map thumbnails show environment and props only, never the robot, even though the `.map` includes one; acceptance of combined loading is separate. Skin thumbnails show the complete appearance. The formal library stores no sidecar `preview.png`; a single package provides its thumbnail.

## Web visual extension

`.map/2` may include hash-bound `visual-appearance.json` (`kk-web-appearance/1`). New releases in this library require `be-web/1`; see the [visual standard](web-appearance-standard.md). The extension preserves Web appearance without changing physics attachment; native MuJoCo uses approximate MJCF visuals. Loaders supporting the extension reject unknown extension versions. Old packages remain compatible but are not guaranteed to meet the new visual standard.
