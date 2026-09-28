"""Validation result structures and spelling suggestions."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field as _dc_field

__all__ = ["Issue", "ValidationResult", "suggest"]


@dataclass
class Issue:
    path: str
    message: str
    hint: str = ""
    level: str = "error"

    def __str__(self) -> str:
        head = f"[{self.level}] {self.path}: {self.message}"
        return f"{head}\n         → {self.hint}" if self.hint else head


@dataclass
class ValidationResult:
    issues: list[Issue] = _dc_field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def report(self) -> str:
        if not self.issues:
            return "Spec validation passed with no issues."
        return "\n".join(str(i) for i in self.issues)


def suggest(key: str, options, label: str = "Available fields") -> str:
    near = difflib.get_close_matches(key, list(options), n=3, cutoff=0.6)
    if near:
        return "Did you mean " + " / ".join(repr(n) for n in near) + "?"
    opts = sorted(str(o) for o in options)
    shown = ", ".join(opts[:25]) + (" ..." if len(opts) > 25 else "")
    return f"{label}: {shown}"
