# Robot simulation

Install `python -m pip install -e ".[sim,dev]"`. The public baseline is [Jumper](../robots/jumper/profile.json), with matching URDF, MJCF and meshes. The original red display skin is [jumper-original.skin](../library/skins/jumper-original.skin).

## Loading

Run `python scripts/shellflow.py verify-package library/skins/jumper-original.skin --profile robots/jumper/profile.json --mujoco`. The same command accepts a map. Native verification compiles and forwards the complete robot and scene; this is not a trained-policy walking test.

URDF is an interchange model; MJCF supplies the native MuJoCo representation. A consumer must implement the content protocol and declared capabilities. Maps attach their environment without replacing the robot's global physics settings. Web material fidelity is a separate acceptance step described in [the visual standard](web-appearance-standard.md).

## Appearance changes

Use a trusted, hash-bound profile and an actual complete assembly. Preserve collision, inertia, joints, and all undeclared visual parts. Run `python scripts/shellflow.py assemble --help` and `python scripts/shellflow.py export-skin --help` for input options. The included scripts/build_original_skin.py rebuilds the stock appearance; custom shell geometry requires a matching mechanical interface and separate engineering review.

The public edition omits legacy robot profiles and historical deliveries. Supplying an old skin does not create a valid current baseline; obtain its authorized source profile before migration. See [baseline updates](jumper-source-update.md) and [package protocol](content-packages.md).

No sample package certifies physical fit, changed-shell dynamics or controller compatibility.
