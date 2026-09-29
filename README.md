# Design Workflow

**English** | [简体中文](README.zh-CN.md)

**Design your robot's look and world with a single prompt.**

Describe what you want to your AI coding assistant. Design Workflow provides the generation rules, package formats, and validation tools for robot appearances (`.skin`) and environments (`.map`).

## One prompt, two workflows

After [setting up the project](#quick-start), open this repository in an AI coding assistant that can read files and run commands. Ask it to read [AGENTS.md](AGENTS.md), then describe the appearance or environment you want.

| Change the appearance | Create an environment |
|---|---|
| **Your prompt:** "Give Jumper a warm sand ranger appearance with coordinated body and limb colors, and export it as a .skin." | **Your prompt:** "Create a park pump track with rolling terrain, trees, benches, and a ready-to-place Jumper, and export it as a .map." |
| Describe → Review design → Generate → Validate | Describe → Build scene → Preview → Validate |
| **Result:** A display-only, complete-robot `.skin` ready to import into a compatible viewer or simulator. | **Result:** A self-contained `.map` with environment assets, a default robot, and a declared spawn point. |
| [![Warm Sand Ranger example](docs/assets/examples/warm-sand-ranger-integrated-v2.png)](library/skins/warm-sand-ranger-integrated-v2.skin) | [![Park Pump Track example](docs/assets/examples/park-pump-track.png)](library/maps/park-pump-track.map) |
| [Download an example .skin](library/skins/warm-sand-ranger-integrated-v2.skin) | [Download an example .map](library/maps/park-pump-track.map) |

A single prompt starts the workflow. Your assistant checks the available tools and inputs, asks you to choose a design when needed, and validates the resulting package. New geometry may require an external modeling tool or a supplied model; arbitrary designs are not guaranteed to finish automatically in one step. The images above are existing example packages, not a promise of an identical result from each prompt.

The repository includes the Python reference tools, package standards, a versioned Jumper robot baseline, and the complete collection of **16 appearances and 13 environments**. Explore the selected examples below or follow the [detailed workflow](docs/workflow.md).

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
