"""mjscene compiles high-level JSON scene descriptions into browser-ready MuJoCo simulations.

Layers (dependencies point downward only)::

    cli/         Commands: new / build / validate / list / schema / prompt / doctor
      │
      ├── authoring/   Scene templates and LLM system prompts
      ├── export/      Downstream simulation/RL exports, such as kk-rl-mjlab
      ├── check/       MJCF validation and smoke tests with optional MuJoCo
      └── build/       spec -> MJCF + scene.viewer.json + assets
            │
            └── spec/      Fields, validation, semantic rules, JSON Schema, assemblies
                  │
                  └── library/   Data vocabulary for materials, friction, contact, sky, lights

Common entry points::

    from mjscene import compile_scene, validate_spec

    spec = {"name": "demo",
            "objects": [{"shape": "sphere", "size": [0.1], "pos": [0, 0, 1]}]}
    result = validate_spec(spec)
    if result.ok:
        compile_scene(spec, "web/public/scenes/demo")
"""

from __future__ import annotations

from . import authoring, build, check, export, library, spec
from .build import CompileResult, compile_scene, compile_spec
from .check import check_model, smoke_test
from .spec import Issue, ValidationResult, json_schema
from .spec import validate as validate_spec

__all__ = [
    # Four common actions
    "compile_scene",
    "compile_spec",
    "validate_spec",
    "json_schema",
    # Validation (requires mujoco)
    "check_model",
    "smoke_test",
    # Data structures
    "CompileResult",
    "ValidationResult",
    "Issue",
    # Layer subpackages
    "library",
    "spec",
    "build",
    "check",
    "authoring",
    "export",
    "__version__",
]

__version__ = "0.1.0"
