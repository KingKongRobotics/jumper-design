"""Geometry and recursive-paint checks for the display-only AMS adapter."""

from pathlib import Path
import importlib.util
import io
import json
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

AVAILABLE = all(importlib.util.find_spec(name) for name in ('numpy', 'trimesh'))
if AVAILABLE:
    import numpy as np
    import trimesh
    from shellflow.ams_colors import _adaptive_area_slot, colors_from_ams


@unittest.skipUnless(AVAILABLE, 'optional mesh dependencies are not installed')
class AmsColorsTests(unittest.TestCase):
    def setUp(self):
        self.mesh = trimesh.creation.box(extents=[10, 12, 4])

    def make_ams(self, *, damage=False, paint='444888833'):
        ns = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
        prod = 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
        main = (f'<model xmlns="{ns}" xmlns:p="{prod}" unit="millimeter">'
                '<resources><object><components><component p:path="/3D/object.model"/>'
                '</components></object></resources><build><item transform="1 0 0 0 1 0 0 0 1 100 100 0"/></build></model>')
        vertices = np.asarray(self.mesh.vertices) + [24.5, -7.25, 0.125]
        if damage:
            vertices[self.mesh.faces[0, 0], 0] += .1
        obj = [f'<model xmlns="{ns}"><resources><object><mesh><vertices>']
        obj.extend(f'<vertex x="{x:.17g}" y="{y:.17g}" z="{z:.17g}"/>' for x, y, z in vertices)
        obj.append('</vertices><triangles>')
        obj.extend(f'<triangle v1="{a}" v2="{b}" v3="{c}" paint_color="{paint if i == 0 else "8"}"/>'
                   for i, (a, b, c) in enumerate(self.mesh.faces))
        obj.append('</triangles></mesh></object></resources></model>')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('Metadata/project_settings.config',
                             json.dumps({'filament_colour': ['#C9102C', '#094BA4']}))
            archive.writestr('3D/3dmodel.model', main)
            archive.writestr('3D/object.model', ''.join(obj))
        stream.seek(0)
        return stream

    def test_recursive_area_beats_leaf_count(self):
        # Three red leaves each cover 1/4; four blue leaves cover 1/16 each.
        self.assertEqual(_adaptive_area_slot('444888833'), 0)
        self.assertEqual(_adaptive_area_slot('888444433'), 1)
        for malformed in ('4443', '444443', '4488', '444888834'):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                _adaptive_area_slot(malformed)

    def test_recentered_mesh_and_paint_are_attributed(self):
        colors, palette, report = colors_from_ams(self.make_ams(), self.mesh)
        self.assertEqual(palette, ['#C9102C', '#094BA4'])
        self.assertEqual(colors.tolist(), [0] + [1] * (len(self.mesh.faces) - 1))
        self.assertEqual(report['adaptive_paint_faces_approximated'], 1)
        self.assertFalse(report['exact_paint_boundary_preservation'])
        self.assertTrue(np.allclose(report['local_mesh_translation_from_stl_mm'],
                                    [24.5, -7.25, .125]))
        self.assertLess(report['max_coordinate_residual_mm'], 1e-12)

    def test_geometry_change_and_unknown_paint_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'CAD geometry'):
            colors_from_ams(self.make_ams(damage=True), self.mesh)
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            colors_from_ams(self.make_ams(paint='2343'), self.mesh)
