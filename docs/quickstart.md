# Quick start

## Install

Use Python 3.10 or newer. Install Git LFS before cloning so the sample archives and robot meshes are available as real files.

```sh
git lfs install
git clone https://github.com/KingKongRobotics/kingkong-design.git
cd kingkong-design
git lfs pull
python -m pip install -e ".[sim,dev]"
```

The `sim` extra supplies MuJoCo and mesh libraries used by simulation-aware checks. The `dev` extra supplies the test and schema-validation tools. The command-line programs are `shellflow` and `mjscene`; from a checkout, `python scripts/shellflow.py --help` and `python -m mjscene --help` show their options.

## Verify an example

The original appearance is a display-only whole-robot package. The maps are self-contained scene packages with the bundled Jumper default robot. Check a package's contents and compatibility with the trusted profile:

```sh
python scripts/shellflow.py verify-package library/skins/jumper-original.skin --profile robots/jumper/profile.json
python scripts/shellflow.py verify-package library/maps/park-pump-track.map --profile robots/jumper/profile.json
```

To ask MuJoCo to compile and forward the model as well, add `--mujoco`:

```sh
python scripts/shellflow.py verify-package library/skins/jumper-original.skin --profile robots/jumper/profile.json --mujoco
```

Package validation checks declared structure, file integrity, and profile compatibility. Native compilation is a separate model-loading check. Neither check substitutes for a human visual review or a physical fit test.

## Export a map

Start from a scene description and write the result to a new output path:

```sh
python scripts/shellflow.py export-map examples/maps/obstacle-course.scene.json --output outputs/obstacle-course.map
python scripts/shellflow.py verify-package outputs/obstacle-course.map --profile robots/jumper/profile.json --mujoco
```

`export-map` compiles the scene and includes the default robot and profile when available. For other command forms, consult `python scripts/shellflow.py --help` and [the package protocol](content-packages.md).

## Review and acceptance

Review the actual package renders, robot visibility, spawn, and scene composition manually. A successful manifest or hash check establishes package integrity, not visual correctness. MuJoCo compilation establishes that the model loads and can be forwarded; it does not establish controller performance. For any changed physical shell, digital assembly and model checks remain separate from printing and fitting it on a real robot.
