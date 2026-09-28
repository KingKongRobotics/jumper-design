"""Read Bambu face paint for a CAD-frame visual mesh.

The 3MF mesh may have been recentered by Bambu Studio.  Its build-plate
placement is irrelevant here: only a constant local-mesh translation is
accepted, and every directed triangle must still match the frozen STL.
"""

from __future__ import annotations

from array import array
import json
import re
import xml.etree.ElementTree as ET
import zipfile

import numpy as np


PAINT_CODES = {'4': 0, '8': 1, '0C': 2, '1C': 3}
_IDENTITY = np.array([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0], dtype=float)
_MAX_RESIDUAL_MM = 2e-5


def _tag(element):
    return element.tag.rsplit('}', 1)[-1]


def _adaptive_area_slot(code):
    """Decode the observed Bambu 3/4/8 recursive paint tree by surface area.

    A hex nibble of 3 is a three-edge split into four equal-area children;
    4 and 8 are filament-one/two leaves.  Bambu serializes the nibbles in
    reverse tree order.  Other split kinds and extended filament states are
    outside this adapter and rejected.
    """
    pending = [1.0]
    areas = [0.0, 0.0]
    saw_split = False
    for nibble in reversed(code):
        if not pending:
            raise ValueError('Malformed adaptive AMS paint tree: trailing nibble')
        area = pending.pop()
        if nibble == '3':
            saw_split = True
            pending.extend((area / 4,) * 4)
        elif nibble == '4':
            areas[0] += area
        elif nibble == '8':
            areas[1] += area
        else:
            raise ValueError('Unsupported adaptive AMS paint nibble')
    if pending or not saw_split or abs(sum(areas) - 1.0) > 1e-9:
        raise ValueError('Malformed adaptive AMS paint tree: incomplete subdivision')
    return 0 if areas[0] >= areas[1] else 1


def _paint_slot(value, palette_size):
    code = (value or '').upper()
    if code in PAINT_CODES:
        slot = PAINT_CODES[code]
        if slot >= palette_size:
            raise ValueError('AMS paint code exceeds its filament palette')
        return slot, False
    # A display face has one color, so the area-largest recursive paint region
    # represents each mixed triangle.  The internal paint edge is approximated.
    if len(code) > 1 and re.fullmatch(r'[348]+', code):
        slot = _adaptive_area_slot(code)
        if slot >= palette_size:
            raise ValueError('Adaptive AMS paint exceeds its filament palette')
        return slot, True
    raise ValueError('Unsupported or missing AMS paint code')


def colors_from_ams(path, source_mesh):
    """Return ``(face_slots, palette, report)`` after full geometry matching.

    ``source_mesh`` must retain STL triangle order.  The report distinguishes
    Bambu's local recentering and the few adaptive mixed-color triangles whose
    internal paint boundaries cannot survive one-color-per-face display.
    """
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if any(m.file_size > 1024**3 for m in members):
            raise ValueError('3MF member exceeds display adapter size limit')
        if len({m.filename for m in members}) != len(members):
            raise ValueError('3MF contains duplicate member names')
        settings = json.loads(archive.read('Metadata/project_settings.config'))
        palette = settings['filament_colour']
        if not isinstance(palette, list) or not 1 <= len(palette) <= 4 or any(
                not isinstance(c, str) or re.fullmatch(r'#[0-9A-Fa-f]{6}', c) is None for c in palette):
            raise ValueError('Unsupported AMS filament palette')
        palette = [c.upper() for c in palette]
        main = ET.fromstring(archive.read('3D/3dmodel.model'))
        if main.get('unit', 'millimeter') != 'millimeter':
            raise ValueError('AMS model must use millimeters')
        components = [e for e in main.iter() if _tag(e) == 'component']
        if len(components) != 1:
            raise ValueError('Expected one AMS mesh component')
        transform = np.fromstring(components[0].get('transform', '1 0 0 0 1 0 0 0 1 0 0 0'), sep=' ')
        if transform.shape != (12,) or not np.array_equal(transform, _IDENTITY):
            raise ValueError('Non-identity AMS component transform')
        model_path = next((v.lstrip('/') for k, v in components[0].attrib.items()
                           if k.endswith('}path')), None)
        if not model_path or model_path not in archive.namelist():
            raise ValueError('AMS mesh component path is missing')

        vertices = array('d')
        face_slots = np.empty(len(source_mesh.faces), dtype=np.uint8)
        offset = None
        largest_residual = 0.0
        mixed = 0
        count = 0
        batch = []
        mesh_vertices = None

        def verify_batch():
            nonlocal offset, largest_residual
            if not batch:
                return
            start = count - len(batch)
            if count > len(source_mesh.faces):
                raise ValueError('AMS has more triangles than the selected STL')
            indices = np.asarray(batch, dtype=np.int64)
            if np.any(indices < 0) or np.any(indices >= len(mesh_vertices)):
                raise ValueError('AMS triangle references an invalid vertex')
            actual = mesh_vertices[indices]
            expected = np.asarray(source_mesh.vertices[source_mesh.faces[start:count]], dtype=np.float64)
            if offset is None:
                offset = np.median((actual - expected).reshape(-1, 3), axis=0)
            residual = float(np.max(np.abs(actual - expected - offset)))
            largest_residual = max(largest_residual, residual)
            if not np.isfinite(residual) or residual > _MAX_RESIDUAL_MM:
                raise ValueError('AMS triangles do not match the selected STL in order and CAD geometry')
            batch.clear()

        with archive.open(model_path) as stream:
            for _, element in ET.iterparse(stream, events=['end']):
                tag = _tag(element)
                if tag == 'vertex':
                    if mesh_vertices is not None:
                        raise ValueError('AMS vertices follow its triangles')
                    vertices.extend(float(element.get(k)) for k in ('x', 'y', 'z'))
                elif tag == 'triangle':
                    if mesh_vertices is None:
                        mesh_vertices = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
                    if count >= len(face_slots):
                        raise ValueError('AMS has more triangles than the selected STL')
                    face_slots[count], is_mixed = _paint_slot(element.get('paint_color'), len(palette))
                    mixed += is_mixed
                    batch.append(tuple(int(element.get(k)) for k in ('v1', 'v2', 'v3')))
                    count += 1
                    if len(batch) == 20000:
                        verify_batch()
                element.clear()
        verify_batch()
        if count != len(face_slots):
            raise ValueError('AMS and selected STL have different triangle counts')
        report = {
            'mode': 'palette_from_geometry_matching_ams',
            'matched_faces': count,
            'local_mesh_translation_from_stl_mm': offset.tolist(),
            'max_coordinate_residual_mm': largest_residual,
            'adaptive_paint_faces_approximated': mixed,
            'exact_paint_boundary_preservation': mixed == 0,
            'color_scope': 'source triangles; visual decimation may further approximate boundaries',
        }
        return face_slots, palette, report
