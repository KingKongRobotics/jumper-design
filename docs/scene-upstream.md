# Scene compiler provenance

The bounded `src/mjscene/` import comes from the maintainer's scene-design project at commit `356c0ad59ae2d2fe3665d520091c5ac768ef5446`. The upstream checkout was clean before import. Python compiler, spec validation, material library, CLI, MuJoCo checks, and the existing `kk-scene-package/1` exporter were copied. The web viewer, AI prompts, scene workspaces, and large generated assets were excluded. A small upstream minimal scene spec and generated JSON schema are included in the source tree.

The source hashes below are SHA-256 of the original tracked files at that commit. They make local adaptations auditable. The imported `scene-package.json`, `scene.xml`, `assets/`, and optional `props/` structure follows the upstream format; `.map` is a new default ZIP filename. `legacy_zip=True` preserves `.scene.zip` output. Local changes also tighten source asset paths, adapt the CLI, and add the shellflow package validator.

| Upstream path | Original SHA-256 |
| --- | --- |
| `mjscene/__init__.py` | `00dc68f857a0e2379e0b40785864260cd629654431b01b2d1a956226f1b82a81` |
| `mjscene/__main__.py` | `4b1afbca74a10abc3cff7b4e5a11b558bf619e45b89709faf9225a474a2a250f` |
| `mjscene/authoring/__init__.py` | `7864fc048754eef4b164e1030176174260e31a929ea3e537035495f39a9a5ee9` |
| `mjscene/authoring/prompt.py` | `7b886ba32317ad9e7ed03fea54e2bec5890c4224ea549e80f228f99b4f043e84` |
| `mjscene/authoring/templates.py` | `bd5390bd64105ae5fb3c48634953aeb4308da4cbea55b3610175643f878caf30` |
| `mjscene/build/__init__.py` | `23a71e74bb09bb4b0cf620b2f5d7bbd64fc6f3ad834a870d933d772445f8401c` |
| `mjscene/build/assets.py` | `1ab5c3e98f9dc1f9519a32b453100a223a66a4eb094b309abe4bc1bb26058718` |
| `mjscene/build/compiler.py` | `023d4967e3c20e2f8e18cfa0c1515532bff375530131a8a42c61b95231baf6ea` |
| `mjscene/build/environment.py` | `65dc204936afd68dc96a0e8d4cb0c1585104e4df4f000e32d0fc57667f973676` |
| `mjscene/build/geometry.py` | `54c34a04f1540a5999ee69ba7930263d7651f541e15caedc324e902080ef2a37` |
| `mjscene/build/mjcf.py` | `b566e96c57774636fc76c9e0e1e91bd13f58b4d800a5ef842b63b48c93e293d8` |
| `mjscene/build/png.py` | `bbbdb8bf2a891698330399504f3ea1768847d8f2209f25187bb7abbb006987dd` |
| `mjscene/build/procedural.py` | `bcd1311a1b8e50b92f729021f6c90c57064d6d3587ba72e70d19e41af4e82652` |
| `mjscene/build/sidecar.py` | `24a735f7b9cbbb58ea08c253601834fa9acd70f5cd9ac285ac35c19fb6c789bd` |
| `mjscene/build/terrain.py` | `46d1e2cace236c484a10e42ffef0da144fd76f5a368b36aa3c2090303aab31d9` |
| `mjscene/check/__init__.py` | `533fe42d45418b92623f451137058a61d02bc5940d0b17e4e11900b39edae0cb` |
| `mjscene/check/model.py` | `ca0120ca9a5a045a3ae2051464c791d5913348f03e34d01a4a087014ffa7ff11` |
| `mjscene/check/runtime.py` | `55fbf0a1ba57cb0154d645b4fec2eb94b1228012a2ae73bd36b17ba78a1e0deb` |
| `mjscene/check/smoke.py` | `cef3d069064b0bcb0bfa42da8589be2544b39ff45d7ff8af5ea2f49274387a78` |
| `mjscene/cli/__init__.py` | `7aaada6000cbc05d5e7effc62195c6cc3f493e1b1fdb7b4545f574e198cae8ad` |
| `mjscene/cli/app.py` | `ab9eaf5f1db46ada2f87255c6d3e2ce8bce5baea856e47c8ac5cb339b97694d1` |
| `mjscene/cli/commands.py` | `f9fc158e165ec8f155917a39817112214bfa82efc98918b7c4b16d4fa4b0d420` |
| `mjscene/cli/common.py` | `06a7d705b9e753a8d360fe57c5d8b2fb3fff492201b3309c4d8138de33077214` |
| `mjscene/export/__init__.py` | `865368ddbf8eb1e00b4c21ff720aa010dd186ac8e781c5da89e72f940e16fa8b` |
| `mjscene/export/mjcf_tools.py` | `2f458efe2a666a308847f54223ce1f314f86467ba6fe3b72275c2abdf3db8373` |
| `mjscene/export/mjlab.py` | `e80239a0dfadde9fe61d27b649dc006e2b3df7739907131938a7bac991711623` |
| `mjscene/export/scene_package.py` | `3a7ead13e8fccec6925961ede5bf78363cacb44eaeebd3d596d63bc6230efb75` |
| `mjscene/library/__init__.py` | `3631ef1b15e0cd00a3ff04adf4a04908a2ad977d9340a17ec8964ab7cd2b64a3` |
| `mjscene/library/catalog.py` | `b9686edb1659775b99ebdd4481ad8b78e8885d9bb9876f1a4358857439f34b91` |
| `mjscene/library/contact.py` | `201919232d1e9ce3ca8520616a395c8d24b777de4fe965bebda6c89a727c2825` |
| `mjscene/library/environment.py` | `8d35005a86c3c30688622578318ea8954e0e6e5b743670b2dd1c4790842eccba` |
| `mjscene/library/materials.py` | `3b2f0d69005d42615b43de0f5749fae9e75109ab867f945ad7acc13016b0ab09` |
| `mjscene/spec/__init__.py` | `b81ad72c64365858889f142d3a022b5a9be71678f914b5035fba7d013c2ee681` |
| `mjscene/spec/assemblies.py` | `605ce2c1324e3ac137bc99cf55d2b4505366c78bfd9208761898074637e5faf9` |
| `mjscene/spec/fields.py` | `07e02b8528f8f2c3adfefd0fb8032e63ac0449ab80fb3c379129ebb4c5f18ffd` |
| `mjscene/spec/issues.py` | `089fb71999b1d692d487eab1f6297777e3c77d284167a0a2d44b0530abcfd967` |
| `mjscene/spec/rules.py` | `d2efa1675d4bf916c32a82370c61d3be04269e92e03ee9da8f82fbd8de4fbe95` |
| `mjscene/spec/schema.py` | `888261337728c16291b1601c1908307fd846ce92e728cbd743a09a90e1307de9` |
| `mjscene/spec/validator.py` | `d6796fa6cb7b01e94e8d0d741349382831842c0ba79362a06194c9142b5ae61c` |
| `schemas/scene.schema.json` | `f87231aa2e5e09f0e9c32b1f91869b09cc9bc5420411130248d13acf146d9ffc` |
| `workspace/minimal/scene.json` | `4bfe8e5a1362d57244ab69c2c0c5397df64bf90ee7534b872b140fc459fc1aa0` |

The recorded upstream snapshot had no separate license file. This public edition distributes the maintainer-owned compiler adaptation under Apache-2.0; the revision and hashes above retain its provenance. See [license scope](../NOTICE.md).

`kk-scene-package/1` was aligned upstream to the independent `kk-rl-mjlab` scene exporter. Manifest names and fields remain unchanged. The shellflow adapter enforces hashes, portable paths, MJCF restrictions, reference resolution, and explicit consumer capabilities. `flex` and `hfield` are rejected for consumers that do not list support. This is package validation, not a claim that every consumer renders all physics/material features identically.

## Local API

`shellflow.map_package.export_map(spec, output, package_id=None, title=None)` accepts a scene JSON path and sibling assets, compiles the MJCF with the imported `mjscene` compiler, validates the produced package, and writes one `.map` ZIP. It returns a compact result with `ok`, `schema`, `id`, `output`, SHA-256, and file count. See `examples/maps/minimal.scene.json` for a small input. The destination must be new.

`shellflow.map_package.validate(files, capabilities=None)` accepts a path-to-bytes dictionary obtained from the ZIP and returns the manifest. To enforce the format's 64 MiB compressed, 192 MiB expanded, and 256-file limits, read external `.map` or legacy `.scene.zip` input with `package_io.read_archive(path, limits=map_package.MAP_LIMITS)`. Both extensions carry the same protocol. `capabilities=None` inspects without binding to a consumer; pass an explicit set when loading for a consumer. Unknown names in `requiredCapabilities` and observed `flex` or `hfield` require matching support.

The importer rejects undeclared files, mismatched SHA-256 or byte counts, unsafe and colliding paths/basenames, missing resources, option/include/plugin/extension elements in any MJCF, an invalid attach prefix, bad world or prop references, non-finite spawn values, and declared counts that disagree with the world XML. It does not silently remove unsupported scene features. The `spawn.yaw` field remains in degrees, as the original protocol specifies.
