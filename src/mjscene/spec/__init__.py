"""Contract layer: scene spec fields, validation, and expansion.

Dependency direction: `library` <- **`spec`** <- `build`. This layer transforms specs
through validation and assembly expansion; it does not generate MJCF.

    from mjscene.spec import validate, json_schema, NODES
    from mjscene.spec import assemblies        # expand assemblies into ordinary objects
"""

from __future__ import annotations

from . import assemblies
from .fields import NODES, VEC_LEN, F
from .issues import Issue, ValidationResult, suggest
from .rules import all_body_names, semantic_checks
from .schema import json_schema
from .validator import Validator, validate

__all__ = [
    "validate",
    "Validator",
    "json_schema",
    "Issue",
    "ValidationResult",
    "suggest",
    "NODES",
    "F",
    "VEC_LEN",
    "assemblies",
    "all_body_names",
    "semantic_checks",
]
