"""Subcommand implementations; app.py only connects arguments to them."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .. import authoring, build, check, export as export_mod, library, spec as spec_mod
from ..spec import assemblies
from .common import (ASSETS_DIRNAME, BAD, INFO, OK, ROOT, SPEC_FILENAME, WARN,
                     WORKSPACE_DIR, build_dir_of, colour, find_specs, load_spec,
                     print_issues, scene_dir_of, write_catalog)

__all__ = ["cmd_new", "cmd_build", "cmd_validate", "cmd_list", "cmd_schema",
           "cmd_prompt", "cmd_doctor", "cmd_export"]


def cmd_new(args) -> int:
    """Create workspace/<name>/ — one self-contained folder per scene."""
    tpl = authoring.get_template(args.template)
    tpl["name"] = args.name
    if args.title:
        tpl["title"] = args.title
    workspace = Path(args.dir) if args.dir else WORKSPACE_DIR
    scene_dir = workspace / args.name
    dest = scene_dir / SPEC_FILENAME
    if dest.exists() and not args.force:
        print(f"{BAD} {dest} already exists (use --force to overwrite)")
        return 1
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / ASSETS_DIRNAME).mkdir(exist_ok=True)
    # Keep the schema next to the chosen workspace, even for an installed CLI.
    schema_path = workspace / "schemas" / "scene.schema.json"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    if not schema_path.exists():
        schema_path.write_text(json.dumps(spec_mod.json_schema(), indent=2,
                                          ensure_ascii=False) + "\n", encoding="utf-8")
    tpl["$schema"] = "../schemas/scene.schema.json"
    dest.write_text(json.dumps(tpl, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{OK} Created scene directory {scene_dir}")
    print(f"  {INFO} {SPEC_FILENAME}   <- edit this file")
    print(f"  {INFO} {ASSETS_DIRNAME}/       <- place meshes and textures here")
    print(f"  {INFO} Build output will go to {args.name}/build/")
    print(f"  Next: python -m mjscene build {args.name}")
    return 0


def cmd_validate(args) -> int:
    rc = 0
    for path in find_specs(args.files, args.all):
        print(f"\n{colour(str(path), '1')}")
        data = load_spec(path)
        res = spec_mod.validate(data)
        if res.issues:
            print_issues(res.issues)
        if not res.ok:
            print(f"  {BAD} Spec validation failed: {len(res.errors)} errors")
            rc = 1
            continue
        print(f"  {OK} Spec validation passed"
              + (f" ({len(res.warnings)} warnings)" if res.warnings else ""))
        if args.compile:
            try:
                result = build.compile_spec(data, path.parent)
            except Exception as exc:
                print(f"  {BAD} Build failed: {type(exc).__name__}: {exc}")
                rc = 1
                continue
            print(f"  {OK} MJCF generated ({len(result.xml.splitlines())} lines)")
    return rc


def cmd_build(args) -> int:
    if getattr(args, "watch", False):
        return _watch(args)
    return _build_once(args)


def _watch(args) -> int:
    """Poll the spec files and rebuild on change — handy while iterating with an AI."""
    import time
    args.watch = False
    seen: dict[Path, float] = {}
    print(f"{INFO} Watching for changes (Ctrl-C to exit)...")
    try:
        while True:
            specs = find_specs(args.files, args.all)
            changed = [p for p in specs
                       if p.exists() and seen.get(p) != p.stat().st_mtime]
            if changed:
                for p in changed:
                    seen[p] = p.stat().st_mtime
                args.files = [str(p) for p in changed]
                args.all = False
                _build_once(args)
                print(f"\n{INFO} Waiting for another change...")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print(f"\n{INFO} Stopped watching")
        return 0


def _build_once(args) -> int:
    specs = find_specs(args.files, args.all)
    if not specs:
        print(f"{BAD} No scenes in the workspace. Create one: python -m mjscene new <name>")
        print(f"  {INFO} Each scene is {WORKSPACE_DIR}/<name>/{SPEC_FILENAME}")
        return 1
    rc = 0
    for path in specs:
        if not path.exists():
            print(f"\n{BAD} Not found: {path}")
            rc = 1
            continue
        print(f"\n{colour(str(path), '1')}")
        data = load_spec(path)
        res = spec_mod.validate(data)
        if res.issues:
            print_issues(res.issues)
        if not res.ok:
            print(f"  {BAD} Spec has {len(res.errors)} errors; skipping build")
            rc = 1
            continue

        # Everything a build produces stays inside the scene's own folder.
        scene_out = Path(args.out) / data["name"] if args.out else build_dir_of(path)
        try:
            result = build.compile_scene(data, scene_out, scene_dir_of(path))
        except Exception as exc:
            print(f"  {BAD} Build failed: {type(exc).__name__}: {exc}")
            rc = 1
            continue
        print(f"  {OK} Wrote {scene_out}/scene.xml"
              + (f" + {len(result.assets)} assets" if result.assets else ""))
        for note in result.notes:
            print(f"  {INFO} {note}")

        if args.check:
            chk = check.check_model(scene_out / "scene.xml")
            if not chk.ok:
                rc = 1
                print(f"  {BAD} MuJoCo rejected the model:")
                for line in chk.error.splitlines():
                    print(f"      {line}")
                if chk.error_element:
                    print(f"      Related element: {colour(chk.error_element, '36')} (line {chk.error_line})")
                if chk.hint:
                    print(f"      → {chk.hint}")
                continue
            s = chk.stats
            print(f"  {OK} MuJoCo compile passed: {s['nbody']} body / {s['ngeom']} geom / "
                  f"{s['nlight']} light / {s['nmat']} material / {s['nq']} qpos, "
                  f"extent {s['extent']}m")
            if args.smoke > 0:
                smoke = check.smoke_test(scene_out / "scene.xml", duration=args.smoke)
                mark = OK if smoke.ok and not smoke.problems else (BAD if not smoke.ok else WARN)
                print(f"  {mark} " + smoke.report().replace("\n", "\n  "))
                if not smoke.ok:
                    rc = 1
    index = write_catalog()
    print(f"\n{OK} Scene index updated: {index}")
    print(f"{INFO} Start the web simulator: cd web && npm install && npm run dev")
    return rc


def cmd_export(args) -> int:
    """Export build output for a downstream framework such as kk-rl-mjlab."""
    rc = 0
    for path in find_specs(args.files, args.all):
        scene_dir = scene_dir_of(path)
        print(f"\n{colour(str(scene_dir), '1')}  ->  {args.target}")
        if not (scene_dir / "build" / "scene.xml").exists():
            print(f"  {BAD} Scene is not built; run: python -m mjscene build {scene_dir.name}")
            rc = 1
            continue
        try:
            res = export_mod.export_scene(args.target, scene_dir,
                                          Path(args.out) if args.out else None,
                                          legacy_zip=args.legacy_zip)
        except Exception as exc:
            print(f"  {BAD} Export failed: {type(exc).__name__}: {exc}")
            rc = 1
            continue
        print(f"  {OK} Wrote {res.out_dir}")
        for line in res.report().splitlines():
            print(f"    {line}")
    return rc


def cmd_list(args) -> int:
    topic = args.topic or "all"

    def show_materials():
        print(colour("\nMaterial presets (materials)", "1"))
        for name, m in library.MATERIALS.items():
            tex = m.get("texture", {}).get("builtin", "-")
            print(f"  {name:16s} rgba={m.get('rgba')} reflectance={m.get('reflectance', 0)} "
                  f"texture={tex}")

    def show_frictions():
        print(colour("\nFriction models (friction) — [sliding, torsional, rolling] + suggested condim", "1"))
        for name, f in library.FRICTION.items():
            note = f"  # {f['note']}" if f.get("note") else ""
            print(f"  {name:16s} [{f['sliding']:>5}, {f['torsional']:>6}, {f['rolling']:>7}] "
                  f"condim={f['condim']}{note}")

    def show_contacts():
        print(colour("\nContact stiffness presets (contact)", "1"))
        for name, c in library.CONTACT_PROFILES.items():
            note = f"  # {c['note']}" if c.get("note") else ""
            print(f"  {name:10s} solref={c['solref']} solimp={c['solimp']}{note}")

    def show_sky():
        print(colour("\nSky presets (sky.preset)", "1"))
        for name, s in library.SKY.items():
            print(f"  {name:12s} zenith={s['top']} horizon={s['bottom']} fog={s['fog']}")

    def show_lighting():
        print(colour("\nLighting presets (lighting.preset)", "1"))
        for name, l in library.LIGHTING.items():
            kinds = ", ".join(f"{x['type']}:{x['name']}" for x in l["lights"])
            print(f"  {name:16s} ambient={l['ambient']}  lights: {kinds}")

    def show_assemblies():
        print(colour("\nAssemblies (assemblies[].type)", "1"))
        for name in library.ASSEMBLIES:
            print(f"  {name:16s} {assemblies.DOCS.get(name, '')}")

    def show_generators():
        from ..build import procedural
        print(colour("\nProcedural asset generators", "1"))
        print("  " + procedural.describe().replace("\n", "\n  "))

    def show_terrain():
        print(colour("\nTerrain generators (ground.terrain.kind)", "1"))
        print("  " + ", ".join(library.TERRAIN_KINDS))

    def show_fields():
        print(colour("\nScene spec fields", "1"))
        for node, table in spec_mod.NODES.items():
            print(colour(f"\n  [{node}]", "36"))
            for key, f in table.items():
                kind = f.kind if f.kind != "enum" else f"enum{f.enum}"
                req = " (required)" if f.required else ""
                dv = "" if f.default is None else f"  default={f.default}"
                print(f"    {key:18s} {kind:12s}{req} {f.doc}{dv}")

    show = {"materials": show_materials, "frictions": show_frictions,
            "contacts": show_contacts, "sky": show_sky, "lighting": show_lighting,
            "assemblies": show_assemblies, "terrain": show_terrain, "fields": show_fields,
            "generators": show_generators,
            "shapes": lambda: print("\nShapes (objects[].shape): " + ", ".join(library.SHAPES)),
            "templates": lambda: print("\nTemplates (new --template): "
                                       + ", ".join(sorted(authoring.TEMPLATES)))}
    if topic == "all":
        for fn in (show_materials, show_frictions, show_contacts, show_sky, show_lighting,
                   show_assemblies, show_terrain, show_generators, show["shapes"],
                   show["templates"]):
            fn()
        print(f"\n{INFO} Field reference: python -m mjscene list fields")
    elif topic in show:
        show[topic]()
    else:
        print(f"{BAD} Unknown topic {topic!r}; available: {', '.join(sorted(show))}, all")
        return 1
    return 0


def cmd_schema(args) -> int:
    schema = spec_mod.json_schema()
    text = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        dest = ROOT / "schemas" / "scene.schema.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print(f"{OK} JSON Schema written to {dest}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_prompt(args) -> int:
    text = authoring.build_prompt()
    if args.write:
        dest = ROOT / "ai" / "PROMPT.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print(f"{OK} LLM prompt written to {dest} ({len(text.splitlines())} lines)")
    else:
        sys.stdout.write(text)
    return 0


def cmd_doctor(args) -> int:
    print(colour("Environment check", "1"))
    print(f"  {OK} python {sys.version.split()[0]}")
    if check.HAVE_MUJOCO:
        print(f"  {OK} mujoco {check.MUJOCO_VERSION} (compile validation and smoke tests available)")
    else:
        print(f"  {WARN} mujoco Python package is missing: spec validation and build still work, but MJCF validation is unavailable")
        print("      Fix: python3 -m venv .venv && .venv/bin/pip install mujoco")
    node_mods = ROOT / "web" / "node_modules" / "mujoco"
    if node_mods.exists():
        print(f"  {OK} web/node_modules/mujoco installed (browser WASM)")
    else:
        print(f"  {WARN} Frontend dependencies missing: cd web && npm install")
    schema = ROOT / "schemas" / "scene.schema.json"
    print(f"  {OK if schema.exists() else WARN} {schema}")
    scenes = sorted(WORKSPACE_DIR.glob(f"*/{SPEC_FILENAME}")) if WORKSPACE_DIR.exists() else []
    print(f"  {INFO} workspace/ contains {len(scenes)} scenes"
          + (": " + ", ".join(s.parent.name for s in scenes) if scenes else
             " (create one: python -m mjscene new <name>)"))
    return 0
