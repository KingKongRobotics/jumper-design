"""Generate JSON Schema from the field table for editors and LLM tools."""

from __future__ import annotations

from typing import Any

from .. import library
from .fields import NODES, VEC_LEN, F

__all__ = ["json_schema"]


def _field_schema(f: F) -> dict:
    d: dict[str, Any] = {}
    if f.doc:
        d["description"] = f.doc
    k = f.kind
    if k == "number":
        d["type"] = "number"
    elif k == "integer":
        d["type"] = "integer"
    elif k == "string":
        d["type"] = "string"
    elif k == "bool":
        d["type"] = "boolean"
    elif k == "enum":
        d["enum"] = f.enum
    elif k in VEC_LEN:
        d.update({"type": "array", "items": {"type": "number"},
                  "minItems": VEC_LEN[k], "maxItems": VEC_LEN[k]})
    elif k == "numlist":
        d.update({"type": "array", "items": {"type": "number"}})
    elif k == "strlist":
        d.update({"type": "array", "items": {"type": "string"}})
    elif k == "node":
        d["$ref"] = f"#/$defs/{f.node}"
    elif k == "nodelist":
        d.update({"type": "array", "items": {"$ref": f"#/$defs/{f.node}"}})
    elif k == "ref":
        known = {"material": sorted(library.MATERIALS), "friction": sorted(library.FRICTION),
                 "contact": sorted(library.CONTACT_PROFILES)}.get(f.ref)
        if f.ref == "friction":
            d["anyOf"] = [{"type": "string", "examples": known},
                          {"type": "array", "items": {"type": "number"},
                           "minItems": 1, "maxItems": 3}]
        else:
            d["type"] = "string"
            if known:
                d["examples"] = known
    elif k == "any":
        pass
    if f.min is not None:
        d["minimum"] = f.min
    if f.max is not None:
        d["maximum"] = f.max
    if f.default is not None and k not in ("node", "nodelist"):
        d["default"] = f.default
    if f.enum and k in ("integer", "number"):
        d["enum"] = f.enum
    return d


def json_schema() -> dict:
    defs = {}
    for node, table in NODES.items():
        if node == "SCENE":
            continue
        props = {k: _field_schema(f) for k, f in table.items()}
        req = [k for k, f in table.items() if f.required]
        d = {"type": "object", "additionalProperties": False, "properties": props}
        if req:
            d["required"] = req
        defs[node] = d
    scene = NODES["SCENE"]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://local/mjscene/scene.schema.json",
        "title": "mjscene scene spec v1",
        "description": "High-level MuJoCo scene description. Build with: python -m mjscene build <file>",
        "type": "object",
        "additionalProperties": False,
        "required": ["name"],
        "properties": {"$schema": {"type": "string"},
                       **{k: _field_schema(f) for k, f in scene.items()}},
        "$defs": defs,
    }
