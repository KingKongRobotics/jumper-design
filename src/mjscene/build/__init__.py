"""Build layer: compile specs into MJCF and web assets.

Dependency direction: `library` <- `spec` <- **`build`**.

    from mjscene.build import compile_scene, compile_spec

    compile_spec(spec)                      # Generate CompileResult in memory
    compile_scene(spec, out_dir, spec_dir)  # Write scene.xml, sidecar, and assets

Modules::

    mjcf.py       MJCF attribute and geometry helpers (fmt / attrs / look_at)
    compiler.py   Compiler translating spec sections into MJCF elements
    sidecar.py    scene.viewer.json rendering hints
    terrain.py    Procedural height fields and standard-library PNG encoding
"""

from __future__ import annotations

from . import assets, environment, geometry, mjcf, png, procedural, sidecar, terrain
from .compiler import CompileResult, Compiler, compile_scene, compile_spec
from .environment import SHADOW_SIZE
from .sidecar import build_viewer
from .terrain import generate_field, write_gray_png, write_heightfield

__all__ = [
    "compile_scene",
    "compile_spec",
    "Compiler",
    "CompileResult",
    "SHADOW_SIZE",
    "build_viewer",
    "generate_field",
    "write_heightfield",
    "write_gray_png",
    "mjcf",
    "procedural",
    "png",
    "environment",
    "geometry",
    "assets",
    "sidecar",
    "terrain",
]
