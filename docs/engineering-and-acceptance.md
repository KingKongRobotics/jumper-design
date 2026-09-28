# Engineering constraints and acceptance

This specification retains acceptance principles from the old kit for future public executors. **The current control CLI does not perform the checks below.** A report is responsible only for files, scope, and methods actually checked.

## Geometry processing order

1. Lock the original CAD platform, millimeter units, forward/up axes, and transformation matrix. Record the selected design, front-closure requirement, internal space, and equipment in the project.
2. Preserve the original GLB and create an appearance copy. Inspect actual front, side, back, and underside gray meshes, especially protruding features and surface continuity.
3. Shape the permitted region, hollow it, form the inner cavity and nonplanar transition. **Add the original CAD functional interface last**; never run global smoothing, scaling, or voxel reconstruction over it.
4. Join mounting posts to the shell with solid roots while preserving hole mouths, channels, assembly rays, and required tool clearance.
5. Freeze the mesh, export the actual STL, read it back, and accept it. Generate AMS from that same frozen geometry and bind every final file to a SHA.

Within this use case, lateral protrusion can obstruct leg travel; front/back protrusion follows the approved design allowance. One uniform scaling rule cannot replace the separate directional constraints. Closing the front does not mean sealing the underside mounting opening.

## Turn observed failures into rules

| Observed failure | Required check |
|---|---|
| A concept and original GLB had a protruding nose, but fitting recessed it | Compare gray meshes at the same angle before/after fitting. Model front/back allowances separately; do not use the lateral limit to compress the nose. |
| A ridge, bump, or seam formed between the eyes | Check continuous surfaces and transition position. Do not merely overlay a patch or inspect texture alone. |
| A second face appeared on the back | Check multiview consistency and generated back view; redo appearance input if needed. |
| Side shrinkage pushed coordinates across center and made a kink in back | Keep deformation center fixed and each side monotonic; forbid crossing; inspect sides and back after deformation. |
| Facial features were covered after functional assembly | Rearrange transitions and cavity on the appearance copy; review the actual surface again after assembly. |
| In-memory double-precision mesh passed but STL failed | Check actual exported single-precision vertices, degenerate faces, slivers, self-intersections, and T-junctions. |
| Face IDs from a prior case were applied to a new model | Locate by geometric conditions and record provenance/color; never reuse old vertex/face indices. |

These are judgment rules, not universal values for deformation distance, voxel size, or front/back width from one case.

## Delivery checks

| Item | Required evidence | Limit of conclusion |
|---|---|---|
| Provenance and size | Input/platform/final export SHAs, units, axes, transforms, bounding box | Even the same platform needs an exact mechanical revision binding. |
| Mesh | Actual STL component count, closure, normals, degeneracy/duplicates/self-intersection results | Appearance screenshots cannot replace topology checks. |
| Mechanical interface | Independent original CAD/interface reference, functional-domain comparison, sample method and error | Incremental discrete error is not printer precision or proof of the entire continuous surface. |
| Wall thickness | Method, sample domain, included/excluded counts, minimum/distribution, thin locations | A sampled minimum is not a strict whole-model minimum. |
| Holes, lips, and roots | Openings, rays, clearance, and solid root connection | Mark corresponding interference checks unverified when screws, lower shell, or internals are absent. |
| Appearance and leg space | Actual multiview images; allowed envelope or known motion-based checks | Without a complete motion model, do not claim collision-free full motion. |
| AMS | Read actual 3MF back; compare geometry, scale, faces, colors/material slots | Preserve real colors such as a white cavity; merely opening the package is insufficient. |
| Slicing | Printer/nozzle/material/layer height, full slicing state, path/tower/bed/support checks | Distinguish reference and actual-printer presets; state the sampled layer scope. |
| Delivery | Files readable again, manifest SHAs match, reports reference final versions | Do not reuse old reports after geometry, export, or color changes. |

Reports should store `inputs`, `outputs`, `method`, `code_version`, `dependencies`, `parameters`, `checks`, and `limitations`. Each check records threshold source, actual value, state, and sampling scope. Use `not_tested`, never `passed`, for work not run.

Record code checks, digital geometry, slicing, actual printing, static assembly, and full-motion trials separately. No new physical fit evidence exists for the current platform. **Digital acceptance must be followed by a physical fit test.**
