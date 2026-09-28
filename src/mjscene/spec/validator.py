"""Structural validation of fields, types, ranges, and references.

Physical semantics are checked in `rules.py`.
"""

from __future__ import annotations

from typing import Any

from .. import library
from .fields import NODES, VEC_LEN, F
from .issues import Issue, ValidationResult, suggest
from .rules import semantic_checks

__all__ = ["Validator", "validate"]


class Validator:
    """Collects issues; also knows which names are defined in this spec."""

    def __init__(self, spec: dict):
        self.res = ValidationResult()
        self.spec = spec
        self.material_names = set(library.MATERIALS) | {
            m.get("name") for m in spec.get("materials", []) if isinstance(m, dict)}
        self.friction_names = set(library.FRICTION) | {
            f.get("name") for f in spec.get("friction_profiles", []) if isinstance(f, dict)}
        self.contact_names = set(library.CONTACT_PROFILES)
        self.mesh_names = {m.get("name") for m in spec.get("meshes", []) if isinstance(m, dict)}
        self.object_names = self._collect_object_names(spec)

    def _collect_object_names(self, spec: dict) -> set[str]:
        names: set[str] = set()

        def walk(objs):
            for o in objs or []:
                if not isinstance(o, dict):
                    continue
                if o.get("name"):
                    names.add(o["name"])
                walk(o.get("children"))

        walk(spec.get("objects"))
        for r in spec.get("robots", []) or []:
            if isinstance(r, dict) and r.get("name"):
                names.add(r["name"])
        return names

    def err(self, path, msg, hint=""):
        self.res.issues.append(Issue(path, msg, hint, "error"))

    def warn(self, path, msg, hint=""):
        self.res.issues.append(Issue(path, msg, hint, "warning"))

    # -- per-kind checks ---------------------------------------------------
    def check_field(self, path: str, f: F, value: Any):
        k = f.kind
        if value is None:
            return
        if k in ("number", "integer"):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return self.err(path, f"Expected a number, got {type(value).__name__}")
            if k == "integer" and isinstance(value, float) and value != int(value):
                return self.err(path, "Expected an integer")
            if f.enum and value not in f.enum:
                return self.err(path, f"Value must be one of {f.enum}; got {value}")
            if f.min is not None and value < f.min:
                self.err(path, f"{value} is below the minimum {f.min}")
            if f.max is not None and value > f.max:
                self.err(path, f"{value} is above the maximum {f.max}")
        elif k == "string":
            if not isinstance(value, str):
                self.err(path, f"Expected a string, got {type(value).__name__}")
        elif k == "bool":
            if not isinstance(value, bool):
                self.err(path, f"Expected true/false, got {value!r}")
        elif k == "enum":
            if f.enum and value not in f.enum:
                self.err(path, f"Unknown value {value!r}", suggest(str(value), [str(e) for e in f.enum]))
        elif k in VEC_LEN:
            n = VEC_LEN[k]
            if not isinstance(value, (list, tuple)) or len(value) != n:
                return self.err(path, f"Expected length {n} numeric array, got {value!r}")
            for i, v in enumerate(value):
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    self.err(f"{path}[{i}]", f"Expected a number, got {v!r}")
        elif k == "numlist":
            if not isinstance(value, (list, tuple)) or not all(
                    isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
                self.err(path, f"Expected a numeric array, got {value!r}")
        elif k == "strlist":
            if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) for v in value):
                self.err(path, f"Expected a string array, got {value!r}")
        elif k == "ref":
            self.check_ref(path, f, value)
        elif k == "node":
            if not isinstance(value, dict):
                return self.err(path, "Expected an object {}")
            self.check_node(path, f.node, value)
        elif k == "nodelist":
            if not isinstance(value, list):
                return self.err(path, "Expected an array []")
            for i, item in enumerate(value):
                if not isinstance(item, dict):
                    self.err(f"{path}[{i}]", "Expected an object {}")
                else:
                    self.check_node(f"{path}[{i}]", f.node, item)

    def check_ref(self, path: str, f: F, value: Any):
        table = {
            "material": (self.material_names, "material"),
            "friction": (self.friction_names, "Friction model"),
            "contact": (self.contact_names, "contact preset"),
            "mesh": (self.mesh_names, "mesh"),
            "object": (self.object_names, "object"),
        }[f.ref]
        names, label = table
        if f.ref == "friction" and isinstance(value, (list, tuple)):
            if len(value) not in (1, 2, 3):
                self.err(path, "Friction values must be [sliding], [sliding,torsional], or [sliding,torsional,rolling]")
            return
        if not isinstance(value, str):
            return self.err(path, f"Expected {label} name (string), got {value!r}")
        if value in names:
            return
        # An empty candidate set means the author never declared this kind at all —
        # "did you mean: <nothing>" is useless, say what to declare instead.
        if not names:
            where = {"mesh": "top-level meshes: [{\"name\": ..., \"file\": ...}]",
                     "object": "an object name in objects"}.get(f.ref, f"top-level {label} list")
            return self.err(path, f"No definitions for {label}", f"Declare it in {where} first")
        self.err(path, f"Undefined {label} {value!r}", suggest(value, names, f"Available {label}"))

    def check_node(self, path: str, node: str, data: dict):
        table = NODES[node]
        for key, value in data.items():
            if key.startswith(("$", "//", "_")) or key == "comment":
                continue           # allow $schema / comments
            if key not in table:
                self.err(f"{path}.{key}" if path else key,
                         f"Unknown field {key!r} (in {node})", suggest(key, table))
                continue
            self.check_field(f"{path}.{key}" if path else key, table[key], value)
        for key, f in table.items():
            if f.required and data.get(key) is None:
                self.err(f"{path}.{key}" if path else key, f"Missing required field {key!r}", f.doc)


def validate(spec: Any) -> ValidationResult:
    """Validate a scene spec and return all errors and warnings."""
    if not isinstance(spec, dict):
        r = ValidationResult()
        r.issues.append(Issue("<root>", "Scene spec must be a JSON object"))
        return r
    v = Validator(spec)
    v.check_node("", "SCENE", spec)
    name = spec.get("name")
    if isinstance(name, str) and not all(c.isalnum() or c in "_-" for c in name):
        v.err("name", f"{name!r} contains invalid characters", "Only letters, digits, underscores, and hyphens are allowed")
    semantic_checks(spec, v)
    return v.res
