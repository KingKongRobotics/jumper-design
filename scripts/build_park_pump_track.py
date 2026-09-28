"""Build the authored, collision-safe Park Pump Track scene source.

The PNG heightfield alone supplies terrain contact. All triangulated meshes are
display-only because MuJoCo convexifies collision meshes, including open road
surfaces. Run from any directory with ``python scripts/build_park_pump_track.py``.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mjscene.build.png import write_gray


OUT = ROOT / "library/map-sources/authored/park-pump-track"
ASSETS = OUT / "assets"
HALF_X, HALF_Y = 5.0, 4.0
STRAIGHT, RADIUS = 2.25, 1.45
WIDTH = 1.04
HFIELD_Z = 0.30
SOUTH_LEN = 2 * STRAIGHT
ARC_LEN = math.pi * RADIUS
LAP_LEN = 2 * SOUTH_LEN + 2 * ARC_LEN
SPAWN_X, SPAWN_Y = -1.57, -RADIUS

COLORS = {
    "grass": "#78a45d",
    "grass_light": "#8db66d",
    "asphalt": "#344b50",
    "asphalt_warm": "#466368",
    "edge": "#f2d78d",
    "center": "#d9e7dc",
    "plaza": "#d1bd92",
    "wood": "#a66e43",
    "wood_dark": "#634a39",
    "metal": "#536c70",
    "trunk": "#786048",
    "canopy": "#4b8354",
    "canopy_light": "#74a65a",
    "shrub": "#66944f",
    "flower": "#e9a86a",
    "flower_alt": "#b7a7d7",
    "sign": "#f6edd2",
}


def smoothstep(a: float, b: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def centerline(s: float) -> tuple[float, float, float, float]:
    """Closed clockwise-in-plan lap, starting at the south-west tangent."""
    s %= LAP_LEN
    if s < SOUTH_LEN:
        return -STRAIGHT + s, -RADIUS, 1.0, 0.0
    s -= SOUTH_LEN
    if s < ARC_LEN:
        a = -math.pi / 2 + s / RADIUS
        return STRAIGHT + RADIUS * math.cos(a), RADIUS * math.sin(a), -math.sin(a), math.cos(a)
    s -= ARC_LEN
    if s < SOUTH_LEN:
        return STRAIGHT - s, RADIUS, -1.0, 0.0
    s -= SOUTH_LEN
    a = math.pi / 2 + s / RADIUS
    return -STRAIGHT + RADIUS * math.cos(a), RADIUS * math.sin(a), -math.sin(a), math.cos(a)


def nearest_track(x: float, y: float) -> tuple[float, float, float]:
    """Return lap station, signed right-hand offset, and turn weighting."""
    if -STRAIGHT <= x <= STRAIGHT:
        if y < 0:
            return x + STRAIGHT, -RADIUS - y, 0.0
        return SOUTH_LEN + ARC_LEN + STRAIGHT - x, y - RADIUS, 0.0
    if x > STRAIGHT:
        a = math.atan2(y, x - STRAIGHT)
        radial = math.hypot(x - STRAIGHT, y)
        return SOUTH_LEN + (a + math.pi / 2) * RADIUS, radial - RADIUS, 1.0
    a = math.atan2(y, x + STRAIGHT)
    if a < math.pi / 2:
        a += 2 * math.pi
    radial = math.hypot(x + STRAIGHT, y)
    return SOUTH_LEN * 2 + ARC_LEN + (a - math.pi / 2) * RADIUS, radial - RADIUS, 1.0


def lap_distance(s: float, other: float) -> float:
    delta = abs(s - other) % LAP_LEN
    return min(delta, LAP_LEN - delta)


def road_height(s: float, d: float, turn: float) -> float:
    # Wide cosine-shaped rollers have zero slope at their crests and blend into
    # the tangent. Keep the first 1.0 m from spawn nearly flat.
    rollers = ((2.35, 0.105, 0.72), (3.60, 0.085, 0.62),
               (SOUTH_LEN + ARC_LEN + 1.65, 0.11, 0.72),
               (SOUTH_LEN + ARC_LEN + 3.20, 0.09, 0.64))
    wave = 0.0
    for station, amplitude, half_length in rollers:
        distance = lap_distance(s, station)
        if distance < half_length:
            wave += amplitude * 0.5 * (1 + math.cos(math.pi * distance / half_length))
    # Turn banking rises toward the outer rim and remains lower at the inner
    # side; the transition to straight is continuously tapered in station.
    turn_ease = turn
    for seam in (SOUTH_LEN, SOUTH_LEN + ARC_LEN, SOUTH_LEN * 2 + ARC_LEN, 0):
        turn_ease *= smoothstep(0.0, 0.55, lap_distance(s, seam)) if turn else 1.0
    bank = turn_ease * 0.078 * smoothstep(-WIDTH / 2, WIDTH / 2, d)
    return 0.052 + wave + bank


def terrain_height(x: float, y: float) -> float:
    s, d, turn = nearest_track(x, y)
    road = road_height(s, d, turn)
    shoulder = 1 - smoothstep(WIDTH / 2, WIDTH / 2 + 0.42, abs(d))
    garden = 0.013 * math.exp(-((x / 1.45) ** 2 + (y / 0.52) ** 2))
    outer_lawn = 0.018 + garden
    return outer_lawn * (1 - shoulder) + road * shoulder


def fmt(*values: float) -> str:
    return " ".join(f"{v:.6f}" for v in values)


def write_obj(path: Path, vertices: list[tuple[float, float, float]], faces: list[tuple[int, int, int]]) -> None:
    with path.open("w", encoding="ascii", newline="\n") as stream:
        stream.write("# Display-only surface; collision is terrain_hfield.\n")
        for v in vertices:
            stream.write("v " + fmt(*v) + "\n")
        for face in faces:
            stream.write("f " + " ".join(str(i + 1) for i in face) + "\n")


def lawn_mesh(path: Path) -> None:
    """Tessellate the island and outer lawn without any triangles under road.

    Grid triangles interpolated across the rollers and poked through the road
    despite a nominal Z offset. Both lawn boundaries now share the road's 512
    station samples, leaving only a 1 cm overlap at each edge.
    """
    n = 512
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []

    # Six rings fill the center island, with one common center vertex.
    vertices.append((0.0, 0.0, terrain_height(0, 0) + 0.001))
    for ring in range(1, 7):
        fraction = ring / 6
        for i in range(n):
            s = LAP_LEN * i / n
            x, y, tx, ty = centerline(s)
            x, y = (x - ty * (WIDTH / 2 - 0.01)) * fraction, (y + tx * (WIDTH / 2 - 0.01)) * fraction
            vertices.append((x, y, terrain_height(x, y) + 0.001))
    for i in range(n):
        faces.append((0, 1 + i, 1 + (i + 1) % n))
    for ring in range(1, 6):
        base = 1 + (ring - 1) * n
        next_base = base + n
        for i in range(n):
            j = (i + 1) % n
            faces.extend(((base + i, next_base + i, base + j),
                          (next_base + i, next_base + j, base + j)))

    # Outer lawn goes from the outer road edge to the park rectangle. Mapping
    # each convex road boundary vertex radially gives a clean rectangular rim.
    outer_base = len(vertices)
    for ring in range(9):
        fraction = ring / 8
        for i in range(n):
            s = LAP_LEN * i / n
            x, y, tx, ty = centerline(s)
            road_x = x + ty * (WIDTH / 2 - 0.01)
            road_y = y - tx * (WIDTH / 2 - 0.01)
            reach = min(HALF_X / abs(road_x) if abs(road_x) > 1e-9 else math.inf,
                        HALF_Y / abs(road_y) if abs(road_y) > 1e-9 else math.inf)
            scale = 1 + fraction * (reach - 1)
            px, py = road_x * scale, road_y * scale
            vertices.append((px, py, terrain_height(px, py) + 0.001))
    for ring in range(8):
        base = outer_base + ring * n
        next_base = base + n
        for i in range(n):
            j = (i + 1) % n
            faces.extend(((base + i, next_base + i, base + j),
                          (next_base + i, next_base + j, base + j)))
    write_obj(path, vertices, faces)


def ribbon_mesh(path: Path, offsets: tuple[float, ...], lift: float) -> None:
    n = 512
    vertices = []
    for i in range(n):
        s = LAP_LEN * i / n
        x, y, tx, ty = centerline(s)
        turn = 1.0 if SOUTH_LEN < s < SOUTH_LEN + ARC_LEN or SOUTH_LEN * 2 + ARC_LEN < s else 0.0
        for d in offsets:
            px, py = x + ty * d, y - tx * d
            vertices.append((px, py, road_height(s, d, turn) + lift))
    faces = []
    cols = len(offsets)
    for i in range(n):
        j = (i + 1) % n
        for k in range(cols - 1):
            a, b, c, e = i * cols + k, i * cols + k + 1, j * cols + k, j * cols + k + 1
            faces.extend(((a, b, c), (b, e, c)))
    write_obj(path, vertices, faces)


def crest_marks_mesh(path: Path) -> None:
    """Paired narrow visual bands identify each rolling crest from above."""
    stations = (2.35, 3.60, SOUTH_LEN + ARC_LEN + 1.65,
                SOUTH_LEN + ARC_LEN + 3.20)
    vertices = []
    faces = []
    for crest in stations:
        for shift in (-0.13, 0.13):
            base = len(vertices)
            for along, across in ((-0.018, -0.36), (-0.018, 0.36),
                                  (0.018, -0.36), (0.018, 0.36)):
                s = crest + shift + along
                x, y, tx, ty = centerline(s)
                px, py = x + ty * across, y - tx * across
                vertices.append((px, py, road_height(s, across, 0) + 0.015))
            faces.extend(((base, base + 1, base + 2), (base + 1, base + 3, base + 2)))
    write_obj(path, vertices, faces)


def rgba(hex_color: str) -> str:
    return " ".join(f"{int(hex_color[i:i + 2], 16) / 255:.6f}" for i in (1, 3, 5)) + " 1"


def add_geom(parent: ET.Element, name: str, kind: str, material: str, *, pos=(0, 0, 0), size=None,
             euler=None, collision=False, **extra: str) -> ET.Element:
    attrs = {"name": name, "type": kind, "pos": fmt(*pos), "material": f"appearance_{material}"}
    if size is not None:
        attrs["size"] = fmt(*size)
    if euler is not None:
        attrs["euler"] = fmt(*euler)
    if not collision:
        attrs.update(contype="0", conaffinity="0", mass="0")
    attrs.update(extra)
    return ET.SubElement(parent, "geom", attrs)


def build_scene(field_min: int, field_max: int) -> tuple[int, int, int]:
    mj = ET.Element("mujoco", model="park-pump-track")
    ET.SubElement(mj, "compiler", angle="degree")
    assets = ET.SubElement(mj, "asset")
    # MuJoCo normalizes PNG grayscale to [0, 1]. Match its physical height to
    # the encoded sample range rather than the original 0.30 m PNG scale.
    field_min_z = HFIELD_Z * field_min / 255
    field_range_z = HFIELD_Z * (field_max - field_min) / 255
    ET.SubElement(assets, "hfield", name="terrain_hfield", file="assets/terrain.png",
                  size=fmt(HALF_X, HALF_Y, field_range_z, 0.08))
    mesh_files = {"grass_surface": "grass_surface.obj", "asphalt_surface": "asphalt_surface.obj",
                  "edge_inner": "edge_inner.obj", "edge_outer": "edge_outer.obj",
                  "lap_center": "lap_center.obj", "crest_marks": "crest_marks.obj"}
    for name, filename in mesh_files.items():
        ET.SubElement(assets, "mesh", name=name, file=f"assets/{filename}")
    for name, color in COLORS.items():
        ET.SubElement(assets, "material", name=f"appearance_{name}", rgba=rgba(color),
                      roughness="0.88" if name not in ("asphalt", "asphalt_warm", "metal") else "0.79",
                      metallic="0")
    world = ET.SubElement(mj, "worldbody")
    ET.SubElement(world, "geom", name="ground", type="hfield", hfield="terrain_hfield",
                  pos=fmt(0, 0, field_min_z), rgba="0 0 0 0", group="3",
                  friction="1.1 0.005 0.0001", margin="0.001")
    ET.SubElement(world, "light", name="sun", pos="0 0 8", dir="0 0 -1", directional="true",
                  diffuse="0.22 0.22 0.22")
    for name, mat in (("grass_surface", "grass"), ("asphalt_surface", "asphalt"),
                      ("edge_inner", "edge"), ("edge_outer", "edge"),
                      ("lap_center", "center"), ("crest_marks", "asphalt_warm")):
        add_geom(world, name, "mesh", mat, mesh=name)
    # The pad is a level section of the same hfield. Paint and station markers
    # have no collision so they cannot create a lip at the robot spawn.
    start_z = terrain_height(SPAWN_X, SPAWN_Y)
    add_geom(world, "start_mark", "box", "center", pos=(SPAWN_X - 0.24, SPAWN_Y, start_z + 0.006),
             size=(0.018, WIDTH * 0.43, 0.001))
    ET.SubElement(world, "site", name="start", pos=fmt(SPAWN_X, SPAWN_Y, start_z),
                  size="0.12 0.12 0.005", type="box", rgba="0 0 0 0")
    for i, station in enumerate((2.35, 3.60, SOUTH_LEN + ARC_LEN + 1.65, SOUTH_LEN + ARC_LEN + 3.20), 1):
        x, y, _, _ = centerline(station)
        ET.SubElement(world, "site", name=f"roller_{i}_crest", pos=fmt(x, y, road_height(station, 0, 0)),
                      size="0.04", rgba="0 0 0 0")
    # Off-course park furniture; all rigid supports are far from the road.
    for i, (x, y) in enumerate(((-4.45, -2.9), (4.45, -2.9), (-4.45, 2.9), (4.45, 2.9)), 1):
        ground_z = terrain_height(x, y)
        add_geom(world, f"tree_{i}_trunk", "cylinder", "trunk", pos=(x, y, ground_z + 0.31),
                 size=(0.065, 0.31), collision=True)
        add_geom(world, f"tree_{i}_crown", "sphere", "canopy", pos=(x, y, ground_z + 0.79),
                 size=(0.31, 0.31, 0.36))
        add_geom(world, f"tree_{i}_highlight", "sphere", "canopy_light",
                 pos=(x - 0.09, y - 0.04, ground_z + 0.91), size=(0.22, 0.22, 0.23))
    for i, (x, y) in enumerate(((-2.15, -3.22), (2.15, 3.22)), 1):
        z = terrain_height(x, y)
        add_geom(world, f"bench_{i}_seat", "box", "wood", pos=(x, y, z + 0.24),
                 size=(0.48, 0.15, 0.035), collision=True)
        add_geom(world, f"bench_{i}_back", "box", "wood_dark", pos=(x, y + 0.14, z + 0.43),
                 size=(0.48, 0.028, 0.19), collision=True)
        for side, dx in (("left", -0.37), ("right", 0.37)):
            add_geom(world, f"bench_{i}_{side}_leg", "box", "metal",
                     pos=(x + dx, y, z + 0.12), size=(0.025, 0.11, 0.12), collision=True)
    # Island planting remains safely inside the inner road edge (y= +/-0.93).
    for i, x in enumerate((-1.35, -0.67, 0, 0.67, 1.35), 1):
        for j, y in enumerate((-0.37, 0.37), 1):
            z = terrain_height(x, y)
            add_geom(world, f"island_shrub_{i}_{j}", "sphere", "shrub",
                     pos=(x, y, z + 0.11), size=(0.22, 0.19, 0.12))
            add_geom(world, f"island_flower_{i}_{j}", "sphere",
                     "flower" if (i + j) % 2 else "flower_alt",
                     pos=(x + 0.07, y - 0.04, z + 0.21), size=(0.065, 0.065, 0.045))
    ET.indent(mj, space="  ")
    (OUT / "scene.xml").write_bytes(ET.tostring(mj, encoding="utf-8", xml_declaration=True) + b"\n")
    return (len(world.findall(".//geom")), len(assets.findall("material")), len(assets.findall("mesh")))


def build_visual_appearance() -> None:
    materials = {}
    for name, color in COLORS.items():
        materials[f"appearance_{name}"] = {
            "color": color, "opacity": 1, "roughness": 0.88 if name not in ("asphalt", "asphalt_warm", "metal") else 0.79,
            "metalness": 0, "emissive": "#000000", "emissiveIntensity": 0,
            "unlit": False, "side": "double" if name in ("grass", "asphalt", "edge", "center") else "front",
            "flatShading": False,
        }
    data = {"schema": "kk-web-appearance/1", "profile": "be-web/1", "colorSpace": "srgb",
            "materials": materials, "lighting": {"mode": "web-default", "builtInScale": 1},
            "renderer": {"toneMapping": "aces-filmic", "exposure": 0.95,
                         "outputColorSpace": "srgb", "background": "#eef1ed",
                         "fog": {"near": 6, "far": 16, "color": "#eef1ed"}}}
    (OUT / "visual-appearance.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def build_manifest(counts: tuple[int, int, int]) -> None:
    geoms, materials, meshes = counts
    files = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "scene-package.json":
            rel = path.relative_to(OUT).as_posix()
            contents = path.read_bytes()
            files[rel] = {"bytes": len(contents), "sha256": hashlib.sha256(contents).hexdigest()}
    data = {
        "schema": "kk-scene-package/1", "id": "park-pump-track", "title": "Park Pump Track",
        "version": "1.0.0", "use": "watching",
        "exportedBy": {"repo": "robot-shell-workflow", "tool": "scripts/build_park_pump_track.py"},
        "source": {"repository": "robot-shell-workflow", "authoredGround": True},
        "requiredCapabilities": ["rigid", "hfield"],
        "world": {"file": "scene.xml", "assetDir": "", "terrainType": "hfield",
                  "ground": {"geom": "ground"},
                  "counts": {"geoms": geoms, "bodies": 0, "lights": 1, "textures": 0,
                             "materials": materials, "meshes": meshes},
                  "attach": {"prefix": "scn_"}},
        "props": [], "flex": [], "lights": [{"name": "sun"}], "cameras": [],
        "spawn": {"position": [SPAWN_X, SPAWN_Y, round(terrain_height(SPAWN_X, SPAWN_Y), 6)], "yaw": 0},
        "files": files,
    }
    (OUT / "scene-package.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    # PNG image top row corresponds to +Y in the visual surface. MuJoCo's
    # hfield data is inspected after load by the validation command below.
    field = []
    for row in range(321):
        y = HALF_Y - 2 * HALF_Y * row / 320
        field.append([round(255 * terrain_height(-HALF_X + 2 * HALF_X * col / 400, y) / HFIELD_Z)
                      for col in range(401)])
    write_gray(ASSETS / "terrain.png", field)
    lawn_mesh(ASSETS / "grass_surface.obj")
    ribbon_mesh(ASSETS / "asphalt_surface.obj", tuple(-WIDTH / 2 + WIDTH * i / 8 for i in range(9)), 0.009)
    ribbon_mesh(ASSETS / "edge_inner.obj", (-WIDTH / 2 + 0.026, -WIDTH / 2 + 0.062), 0.017)
    ribbon_mesh(ASSETS / "edge_outer.obj", (WIDTH / 2 - 0.062, WIDTH / 2 - 0.026), 0.017)
    ribbon_mesh(ASSETS / "lap_center.obj", (-0.017, 0.017), 0.017)
    crest_marks_mesh(ASSETS / "crest_marks.obj")
    build_visual_appearance()
    counts = build_scene(min(map(min, field)), max(map(max, field)))
    build_manifest(counts)
    print(f"Built {OUT} with {LAP_LEN:.3f} m lap, {WIDTH:.2f} m road, {counts[0]} geoms")


if __name__ == "__main__":
    main()
