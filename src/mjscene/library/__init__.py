"""Data vocabulary available to scene authors.

This layer contains data and lookup functions without dependencies on other
mjscene modules. Add new materials, friction models, or lighting rigs here;
`mjscene list`, JSON Schema enums, and the LLM prompt derive from these tables.

    from mjscene.library import MATERIALS, FRICTION, friction_triple
"""

from __future__ import annotations

from .catalog import (ASSEMBLIES, DEFAULT_PHYSICS, MESH_GENERATORS, SHAPES,
                      TERRAIN_KINDS, TEXTURE_GENERATORS)
from .contact import CONTACT_PROFILES, FRICTION, friction_triple
from .environment import LIGHTING, SKY
from .materials import MATERIALS

__all__ = [
    "MATERIALS",
    "FRICTION",
    "CONTACT_PROFILES",
    "friction_triple",
    "SKY",
    "LIGHTING",
    "SHAPES",
    "ASSEMBLIES",
    "TERRAIN_KINDS",
    "DEFAULT_PHYSICS",
    "TEXTURE_GENERATORS",
    "MESH_GENERATORS",
]
