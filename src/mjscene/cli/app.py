"""Argument parsing and CLI entry point."""

from __future__ import annotations

import argparse

from .. import authoring
from .commands import (cmd_build, cmd_doctor, cmd_export, cmd_list, cmd_new, cmd_prompt,
                       cmd_schema, cmd_validate)


__all__ = ["build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m mjscene",
                                description="MuJoCo scene authoring framework for web simulation")
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="Create a scene spec from a template")
    n.add_argument("name")
    n.add_argument("--template", "-t", default="minimal",
                   choices=sorted(authoring.TEMPLATES))
    n.add_argument("--title")
    n.add_argument("--dir")
    n.add_argument("--force", action="store_true")
    n.set_defaults(func=cmd_new)

    b = sub.add_parser("build", help="Compile a spec into MJCF and web assets")
    b.add_argument("files", nargs="*")
    b.add_argument("--all", action="store_true", help="Build every scene in scenes/")
    b.add_argument("--out", help="Output root (default: workspace/<scene>/build/)")
    b.add_argument("--no-check", dest="check", action="store_false",
                   help="Skip MuJoCo compile validation")
    b.add_argument("--smoke", type=float, default=3.0,
                   help="Smoke-test duration in seconds; 0 skips it (default: 3)")
    b.add_argument("--watch", action="store_true",
                   help="Watch the spec and rebuild after changes")
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("validate", help="Validate a spec without writing files")
    v.add_argument("files", nargs="*")
    v.add_argument("--all", action="store_true")
    v.add_argument("--no-compile", dest="compile", action="store_false")
    v.set_defaults(func=cmd_validate)

    e = sub.add_parser("export", help="Export for downstream simulation and RL frameworks")
    e.add_argument("files", nargs="*")
    e.add_argument("--all", action="store_true")
    e.add_argument("--target", "-t", default="mjlab",
                   choices=sorted(__import__("mjscene.export", fromlist=["TARGETS"]).TARGETS))
    e.add_argument("--out", help="Output directory (default: workspace/<scene>/export/<target>/)")
    e.add_argument("--legacy-zip", action="store_true",
                   help="Use the legacy .scene.zip filename without changing the package protocol")
    e.set_defaults(func=cmd_export)

    l = sub.add_parser("list", help="List materials, friction, lights, assemblies, and other options")
    l.add_argument("topic", nargs="?")
    l.set_defaults(func=cmd_list)

    s = sub.add_parser("schema", help="Print the JSON Schema")
    s.add_argument("--write", action="store_true", help="Write schemas/scene.schema.json")
    s.set_defaults(func=cmd_schema)

    pr = sub.add_parser("prompt", help="Generate the LLM system prompt from the current vocabulary")
    pr.add_argument("--write", action="store_true", help="Write ai/PROMPT.md")
    pr.set_defaults(func=cmd_prompt)

    d = sub.add_parser("doctor", help="Check the environment")
    d.set_defaults(func=cmd_doctor)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
