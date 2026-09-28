---
name: robot-shell-workflow
description: Use Design Workflow to create, validate and exchange robot appearances (.skin) and environments (.map), with separate physical-shell manufacturing when requested.
---

# Design Workflow

The skill identifier remains `robot-shell-workflow` for compatibility. Select the appearance or environment route in `../../docs/workflow.md` first. Map work uses scene authoring/build/export and does not require a print-shell job or slicer. Use the mechanical engineering steps below only when producing a physical shell.

This is a thin entrypoint into the repository, not a standalone CAD engine.

Read `../../AGENTS.md` and `../../README.md` relative to this file. Run the repository's `scripts/shellflow.py` from its root. If the skill has been copied elsewhere without the repository, locate the user's checkout first; do not guess personal paths or claim that missing assets are installed.

For every new interoperable delivery, follow `../../docs/content-packages.md`: use `export-skin` for a display-only full-robot appearance (.skin/3); printing files must remain separate, or `export-map` for a compiled scene. Run `verify-package`, pin the trusted robot profile for skin compatibility, and use `--mujoco` for an actual native loading check. Deliver `.skin` and `.map`; preserve `/1` protocol semantics, relative resources, SHA bindings and separate manufacturing/fit status. Use `import-package` and `repack-package` for validated round trips. Never invent an incompatible manifest just to make a consumer accept the file.

Use `doctor`, `start`, `status`, `next`, `checkpoint`, and `assemble` as documented. The v0.2 CLI includes a real full-robot assembly producer, while `checkpoint` remains an evidence ledger. Generic image generation, Tripo, CAD adaptation and manufacturing validation backends are not fully migrated. Preserve these distinctions.

Load `docs/workflow.md` for the current stage and `docs/engineering-and-acceptance.md` before engineering/validation. Use the user's own authorized AI/provider tools and local platform package. Avoid reading historical cases in bulk.

Every new shell requires printing and simulation delivery: STL/AMS 3MF plus a complete full-robot `robot.urdf`, `robot.xml`, `scene.xml`, relative `meshes/` and the simulation report. Read `docs/simulation.md` before assembly. Preserve every source body/link/joint and verify the complete tree and URDF poses; a shell-only URDF is not a delivery.

New jobs default to `robots/jumper/profile.json`. Existing jobs retain their selected robot; explicitly upgrade with `assemble PROJECT --shell FILE --robot-platform jumper --output NEW_DIR`. The canonical source is `jumper/urdf/jumper.urdf`: 41 links and 22 movable joints named by indexed groups such as `LF_J0_joint`. Import adds a `floating_base` virtual root joint. The source has no active sensor, camera, or actuator elements. Preserve mechanical and inertial defaults, declare any requested lower-body and limb colors in visual_overrides, and replace the upper shell visual on `upper_shell_link`. Registration checks the seam only; the six-hole interface is not physically certified and `physical_fit_tested` stays false. Keep the historical `jumper-v1-6` profile and its old deliveries bound to that version.
The preview pose is static display data, not a motion target. Keep source joint limits unchanged and clamp display values into range (`RF_J4` 0 rad to 0.1 rad; `LM_J0` retains 0.0012 rad within [-0.75, 1] rad). Because all 22 joint names changed to indexed names, bind controllers using the new mapping; do not assume old controllers can be reused directly. See `../../docs/jumper-source-update.md` for source hashes, skin migration, checks and limits.

Baseline-preserved collision and inertia do not validate new-shell dynamics.

The library contains actual historical final assets, including entries explicitly marked `needs-review`. Use their IDs and SHA records, fetch Git LFS assets, and do not silently turn historical reports into a new acceptance pass.

Publish current display-only `.skin/3` releases via `scripts/publish_content.py` into `library/skins/`. Use `library/maps/` for `.map/2`, which bundles a complete default robot and spawn; verify composed robot presence and spawn clearance, including pouring maps. Keep print sources separate and build outputs out of Git. Follow `docs/git-storage.md` for LFS, naming, indexes, and version replacement.
