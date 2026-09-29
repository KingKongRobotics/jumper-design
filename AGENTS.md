# Instructions for AI assistants working in this repository

## Project scope and request routing

The public project name is **Design Workflow**. Appearance `.skin` and environment `.map` creation are equal workflows. First identify the requested route. For maps, gather scene requirements, scale, terrain/props, challenge targets, robot profile, spawn and visual acceptance; use scene authoring/build/export rather than the print task ledger. For display-only appearance packaging, use the existing complete-robot assembly and `export-skin`. Apply CAD installation, print engineering, slicing and physical-fit rules only to physical-shell work. APP execution and website implementation are outside this repository. Keep established CLI, protocol and historical provenance identifiers compatible.

## Required design selection before modeling

For every new appearance, including display-only skins and physical shells, present distinct design candidates and wait for the user's explicit choice before selecting a modeling tool or generating 3D geometry. Do not treat silence, a default option, or an assistant preference as a selection. Reuse a design or existing model explicitly selected by the user in the current task; record that instruction without asking again. Pure repackaging or validation of an unchanged existing asset does not require new concept selection. Scene authoring remains a separate route.

Record the selected design, actual user confirmation, and immutable reference hashes as described in docs/workflow.md. Only then assess available tools and explain the suitable route using docs/providers.md. Tripo is optional; never require an account or assume permission to spend credits. If available tools cannot preserve the selected design, explain the limitation and obtain a new choice before simplifying or substituting it.

Review actual front, side, back and assembled color renders against the chosen silhouette, proportions, details and palette. Also inspect gray geometry and activity clearances. Iterate on mismatches before delivery; package validity is not visual acceptance. Never present concept art as a render of the generated model.

## Required appearance and scene exchange protocol (v0.6)

Read the [content package protocol](docs/content-packages.md) first. Deliver appearances as `.skin` and scenes as `.map`. Do not invent another directory layout, unit system, manifest field, or extension. For new production use `export-skin` / `export-map`; run `verify-package` before delivery, passing the selected trusted `--profile` for skins. Use `--mujoco` to check actual loading. Package parsing, platform compatibility, simulation loading, manufacturing checks, and physical fitting are separate conclusions.

- `.skin/3` is display only. It must contain a complete whole-robot URDF/MJCF and relative display meshes, and must not contain print STL, AMS 3MF, G-code, or STEP. Deliver print files separately, bound to the exact mechanical interface and profile SHA. Undeclared parts retain the baseline configuration. Never fabricate a whole robot from one shell or treat different mechanical revisions as interchangeable.
- For whole-robot color requests, use `assemble --visual-overrides FILE.json` or a batch recipe in `library/skin-recipes.json`; declare lower-shell and limb visual RGBA in `.skin/3` `visual_overrides`. Change only explicitly declared, noncollision visual parts, never the baseline profile or physical parameters. Legacy `/1` and `/2` are read-compatible only.
- New `.map` production uses `kk-scene-package/2`: retain `scene-package.json`, terrain, and props; include a verified, complete display-only `.skin/3` as the default robot under `robot/`, bound to a trusted profile SHA. Spawn must be declared or explicitly supplied by the exporter. Legacy `/1` and `.scene.zip` are read-compatible only. Attach the scene; do not concatenate XML in a way that overrides the robot's global physics parameters. `spawn.yaw` remains in degrees, never radians. Compile the default complete robot and check its spawn in each new map; manifest fields alone do not prove that a robot is visible.
- Package data must be self-contained. Reject path traversal, undeclared assets, hash mismatches, unknown required capabilities, and executable extensions. A failed check must stop release/replacement and preserve the previous session and files.
- Protocol changes must update schemas, the Python reference validator, round-trip and rejection tests, docs, and release notes. New mandatory semantics require a protocol version bump; do not keep `/1` if old readers would silently ignore a new requirement. Cross-platform support applies only to consumers that implement the protocol and required capabilities.
- Do not promote `source_provided_unverified` to printable or physically tested by editing a manifest `passed` field. The generic geometry/manufacturing backend has not all been migrated; the package format does not invent acceptance evidence.
- Use an appropriate working model for normal implementation, a lightweight model for independent reading/checks, and scripts for fixed calculations and batch validation. Reserve advanced models for architecture and materially complex issues. Never remove required acceptance checks to save tokens.

Read [the quick-start guide](docs/quickstart.md) and [documentation index](docs/index.md) before using the public CLI. v0.2 already has an asset library and whole-robot assembly exporter; generic modeling, hollowing, and manufacturing acceptance backends are still being migrated. Do not claim missing backends ran, install paths from someone else's historical computer, or copy browser identity.

## Starting and resuming physical-shell work

1. Extract from the user's request the platform ID/mechanical revision, appearance, closure requirement, left/right and front/back constraints, colors, equipment, and any design already explicitly selected by the user. Respect information already provided in this turn and session; do not ask again.
2. Run `python scripts/shellflow.py doctor` to inspect local tools. Rerun only when the environment changes. Tool presence does not establish that its version, Python libraries, or modeling workflow were validated.
3. Use `start` for new work; use `status` / `next` for existing work. Resolve and validate the mechanical platform at `.local/platforms/<id>/platform.json`. New tasks default to the `jumper` whole-robot simulation platform; `start --robot-platform` overrides it. Existing tasks keep their selection and must not depend on historical project directories or upgrade silently. `jumper-v1-6` and `hexa-v1` remain supported; old projects and assets retain their respective profiles.
4. Read the project's `AGENT_TASK.md` / `job.json`, loading only docs needed for the current stage. Work independently where possible, then group questions that truly affect the next step.
5. CLI checkpoints currently save file evidence and fingerprints only. `recorded` is not `verified`; a record, file's existence, or single `passed` line does not establish engineering completion.
6. If a stage executor has not been implemented, identify the specific gap. Checked, project-specific adapter code may be built in the task directory, but never invoke unknown historical external scripts or reuse face indices from another shape.
7. Every new upper shell requires both print and whole-robot simulation delivery. Once the print part is frozen, run `assemble PROJECT --shell FILE` with the real robot, inspect output and report, then register `simulation`. Report completion only after both deliveries have actually met their requirements and limitations are clear.

## Engineering rules

- Follow [engineering and acceptance](docs/engineering-and-acceptance.md). Preserve original inputs; modify an appearance copy and add the exact interface last.
- Record units, forward/up axes, and transformation matrices explicitly. A platform's face count, hole count, tolerances, and allowed front/back region are not universal robot constants.
- If the user permits front/back protrusion, do not recess those details merely to simplify constraints. Check monotonicity, fixed center, and no side crossing for lateral deformation.
- Inspect actual front, side, back, and underside gray meshes and color views. Concept art or a front-only preview cannot replace real mesh review.
- After freezing, check the actual STL. Read AMS 3MF back and compare it with the same frozen coordinates, triangles, and colors. Until full acceptance is migrated, control-layer states cannot stand in for these checks.
- With an unconfirmed printer, use only a clearly labeled reference slice and do not send a print. Keep `physical_fit_tested=false` until physical fitting occurs.

## Whole-robot simulation rules

- Use the task's selected versioned whole-robot baseline; new tasks default to `robots/jumper/profile.json`. Legacy `hexa-v1` and `jumper-v1-6` remain. An old project upgrades only with explicit `assemble PROJECT --shell FILE --robot-platform jumper --output NEW_DIR`, and persists the new binding only after a successful export and review.
- The canonical `jumper` source is `jumper/urdf/jumper.urdf`: 41 links and 22 movable joints with indexed names such as `LF_J0_joint`. The importer adds a virtual `floating_base` root joint; it is absent from the source URDF. The source has no active sensor, camera, or actuator elements. Retain source mechanics, inertia, and undeclared colors; apply explicit whole-robot colors through `visual_overrides`; replace the visual of `upper_shell_link`. Never deliver a shell-only URDF or fabricate a whole robot from one shell.
- The new names of all 22 joints differ from historical semantic names. Bind controllers through the new mapping; do not claim that an old controller works unchanged. A preview pose is static display data, not a control target. Clamp out-of-range display values to source URDF limits without changing those limits. Current `LM_J0_joint` source limit is [-0.75, 1] rad; reject the stale +0.75 lower limit on import. Remap the preview from the historical source pose, retaining `LM_J0` at 0.0012 rad. `RF_J4` at 0 rad is clamped to its source lower limit of 0.1 rad.
- Keep STL in original CAD millimeters. The AMS bed-placement transform is for printing only, not assembly. Change nonshell colors only through explicit `visual_overrides`. Extract new shell colors only from a geometry-matched AMS; otherwise document a single-color fallback.
- Simplify simulation appearance meshes only, targeting 100,000 faces by default. Do not modify print STL/AMS. Report simplification error and the approximate scope of color splitting.
- Deliver complete `robot.urdf`, `meshes/`, native MJCF `robot.xml`, `scene.xml`, and `simulation-report.json` every time. Check whole-tree `whole_robot` records and the URDF 10-pose validation, and match print-shell and robot-profile SHAs in the report to this run's inputs.
- Historical `jumper-v1-6` has 37 robot links, 22 movable joints, and zero source actuators. Its old simulation packages, source, and validation evidence remain bound to that profile, never rewritten as `jumper`.
- Registration of the new baseline checks only the upper-shell seam. The six-hole mechanical interface has no physical interface certification: `physical_fit_tested=false`. Digital registration is not a physical fit test. Do not reuse transforms from `hexa-v1` or `jumper-v1-6`.
- Before first simulation use, install `.[sim]` and check dependencies per [simulation](docs/simulation.md). An in-memory VFS resolves assets under Chinese Windows paths; other software and systems require actual testing.

## AI and service boundaries

Reuse tools explicitly authorized by the current user. Image generation, authorized Tripo web/API access, or user-supplied GLB are possible inputs. Paid credits and accounts belong to the user; examples/configuration do not grant spending authorization. Use the AI's current browser tools and do not hard-code DOM indices from a past session. Preserve real task evidence for uploads, generation, and export. If a service is unavailable, use local file import or state the required input.

Before any service generation that consumes credits, including free credits, follow the mandatory service preflight in `docs/providers.md`: verify the current account tier, generation and export allowances, exact model/version options, required downloadable format, total cost, public visibility and relevant usage terms. Record current evidence locally before spending. Unknown export eligibility blocks generation. Do not automatically spend again after an export failure or change versions to retry unless existing user authorization covers the retry and cost; never infer subscription/purchase permission. The CLI cannot verify remote account entitlements.

## Version control and delivery

Author repository documentation, code, and public metadata in English. Preserve historical source paths and evidence identifiers exactly where they are used for lookup; encode non-English originals as JSON Unicode escapes instead of translating or fabricating them. Preserve original manufacturing binary bytes. Public `.skin` and `.map` decoded strings must be English. Run `python scripts/check_english.py --require-packages` for a full release check; CI text checks may accept LFS pointers, but release verification must fetch and inspect the actual archives.

Commit code, rules, schemas, tests, and asset indexes to Git. Use Git LFS for explicitly selected STL/AMS under `library/assets/`, complete-robot and simulation meshes, and verified minimal platform bundles under `platforms/bundles/`. The original-robot-v1 engineering reference bundle is included at the repository maintainer request; legacy character print deliveries remain excluded. Read docs/platform-pack.md and verify the bundle with scripts/check_mechanical_platform.py before use. Preserve historical license metadata and unverified mechanical states; publication does not certify fit or grant a new source-asset license. Missing archives require separately authorized mechanical inputs; never reconstruct mounting geometry from display meshes. Installed platforms, ordinary runtime directories, secrets, and local configuration remain ignored. Do not commit an entire old kit. Bind stage results to input, parameter, code, and artifact SHAs; revalidate affected stages after changes. Delivery notes must distinguish implemented features, checks actually run, limited sampling, and physical checks not performed.

Keep routine work to necessary context and concise status. Parallelize only for independent audits or clear debugging benefit. Do not relax acceptance to save tokens.

## Formal content releases and confirmed defaults

Read and apply [content release defaults](docs/content-release-rules.md) first. These confirmed requirements should not be asked of the user again; do not rely only on historical summaries and miss this entry point. They cover flat single-file delivery, in-package thumbnails, robot-free map thumbnails, the full Web visual layer, original terrain materials, the removal list, and physical invariance. This repository produces and checks packages; website accounts, pages, and uploads are separate consumer work and require their own explicit task scope.

`content_library.publish` runs both protocol validation and `release_policy.validate_release_policy`. Passing automated checks still requires visual review under the rules; metadata success does not prove visual fidelity.

The current BE Web `be-web/1` is the shared standard for scene color; read [color and visual standard](docs/web-appearance-standard.md) first. Export in-package visual declarations, compare the same camera angle, and render thumbnails through the Web importer. Never substitute native renders for Web acceptance or silently treat sRGB as linear RGB.

## Public distribution licensing

The maintainer selected Apache-2.0 for maintainer-owned content in this public candidate. Preserve LICENSE, NOTICE and third-party attribution. Do not restore a CC BY split or a pending license-choice statement. License selection does not resolve upstream ownership: imported code and assets require a recorded distribution basis before publication. Generated user packages do not inherit the tool's license automatically. Keep all package changes hash-consistent and retain notices for embedded assets. Before publishing, run the package, English, publication and fresh-clone checks documented in docs/release-checklist.md.

## README translations

Maintain README.md as the English homepage and README.zh-CN.md as its Simplified Chinese translation, with reciprocal language links. Keep prompts, examples, commands and capability boundaries aligned. These two documentation surfaces are explicit exceptions to the English-only rule: only the language-switch label may use Chinese in README.md. Source code and public package metadata remain English.
