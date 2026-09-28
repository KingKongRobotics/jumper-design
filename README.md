# Design Workflow

Design Workflow creates, validates, and exchanges robot appearances (`.skin`) and environments (`.map`). The repository provides the Python reference tools, package standards, a versioned Jumper robot baseline, and the complete collection of 16 appearance packages and 13 environment packages.

## See what you can create

### Robot appearances · `.skin`

Replace the complete robot appearance with one display-only package. Print files stay separate.

| [Silver Armor Guardian](library/skins/mecha-tripo-v3.skin) | [Raphael Turtle](library/skins/raphael-turtle-v1.skin) | [Warm Sand Ranger](library/skins/warm-sand-ranger-integrated-v2.skin) |
|---|---|---|
| [![Silver Armor Guardian](docs/assets/examples/mecha-tripo-v3.png)](library/skins/mecha-tripo-v3.skin) | [![Raphael Turtle](docs/assets/examples/raphael-turtle-v1.png)](library/skins/raphael-turtle-v1.skin) | [![Warm Sand Ranger](docs/assets/examples/warm-sand-ranger-integrated-v2.png)](library/skins/warm-sand-ranger-integrated-v2.skin) |

### Environments and challenges · `.map`

Load an environment with terrain, props and a ready-to-place default robot. Thumbnails show the environment only.

| [Bedroom](library/maps/bedroom.map) | [Soccer Field](library/maps/soccer.map) | [Park Pump Track](library/maps/park-pump-track.map) |
|---|---|---|
| [![Bedroom](docs/assets/examples/bedroom.png)](library/maps/bedroom.map) | [![Soccer Field](docs/assets/examples/soccer.png)](library/maps/soccer.map) | [![Park Pump Track](docs/assets/examples/park-pump-track.png)](library/maps/park-pump-track.map) |

[Browse all skins](library/skins/README.md) · [Browse all maps](library/maps/README.md) · [Follow the workflow](docs/workflow.md)

These examples use the actual thumbnails embedded in the published packages. Images here are documentation copies; each `.skin` and `.map` remains self-contained.

## Quick start

Requires Python 3.10 or newer. Git LFS is required to check out the binary sample packages and robot meshes.

```sh
git lfs install
git clone https://github.com/KingKongRobotics/kingkong-design.git
cd kingkong-design
git lfs pull
python -m pip install -e ".[sim,dev]"
python scripts/shellflow.py --help
```

See [the quick start guide](docs/quickstart.md) for package checks and a first map export.

## What the tools do

- Read, validate, import, and repack versioned `.skin` and `.map` ZIP packages.
- Export display-only, complete-robot `.skin` packages and compile scene descriptions into `.map` packages.
- Check package structure, declared files, hashes, robot compatibility, and—when requested—load models with native MuJoCo.
- Record evidence and artifacts for a physical-shell workflow. Geometry generation, printer acceptance, and physical fitting remain separate work.

Automated package checks do not establish that a model looks correct. Review the rendered appearance and scene manually. Native MuJoCo compilation checks model loading; it does not certify the behavior or physical fit of a changed shell. See [engineering and acceptance](docs/engineering-and-acceptance.md).

## Repository map

- `src/`: Python package and MuJoCo scene compiler.
- `scripts/`: command-line entry points and content import/export utilities.
- `schemas/`: JSON Schema definitions for package manifests.
- `robots/jumper/`: versioned whole-robot baseline and profile.
- `library/skins/`, `library/maps/`: selected public example packages and indexes.
- `examples/`: scene source examples.
- `docs/`: package, workflow, architecture, and licensing documentation.

Start at the [documentation index](docs/index.md). For package layout and compatibility rules, read [the content package protocol](docs/content-packages.md).

## License

Maintainer-owned project materials are licensed under Apache-2.0. See [LICENSE](LICENSE), [NOTICE](NOTICE), and [licensing details](docs/licensing.md). Third-party materials remain under their respective terms, and generated outputs do not automatically inherit this repository's license.
