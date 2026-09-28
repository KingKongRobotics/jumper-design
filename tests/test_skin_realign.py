"""Migration orchestration tests; native geometry is covered by simulation tests."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "realign_skins.py"
spec = importlib.util.spec_from_file_location("realign_skins", SCRIPT)
realign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(realign)


class RealignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SCRIPT.parents[1])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        old_profile = self.root / "robots/jumper-v1-6/profile.json"
        old_profile.parent.mkdir(parents=True)
        old_profile.write_text('{"id":"jumper-v1-6"}', encoding="utf-8")
        repo_patch = patch.object(realign, "REPO", self.root)
        repo_patch.start()
        self.addCleanup(repo_patch.stop)
        self.profile = self.root / "profile.json"
        self.profile.write_text('{"id":"jumper"}', encoding="utf-8")
        self.sources = [self.root / "a.skin", self.root / "b.skin"]
        for source in self.sources:
            source.write_bytes(b"identical archive")
        self.inventory = self.root / "inventory.json"
        self.inventory.write_text(json.dumps({"skin_archives": [
            {"source_path": str(source), "sha256": realign.sha(source)}
            for source in self.sources]}), encoding="utf-8")
        self.old_files = {"skin-package.json": json.dumps({
            "id": "bee-a", "title": "Bee", "author": "A", "license_id": "L",
            "platform": {"id": "jumper-v1-6"}}).encode(),
            "print/shell.stl": b"original shell", "print/ams.3mf": b"original ams"}
        self.assemble_calls = []
        self.export_calls = []

    def mock_assemble(self, shell, output, profile, **kwargs):
        self.assemble_calls.append((shell.read_bytes(), kwargs["ams3mf"].read_bytes()))
        output.mkdir()

    def mock_export(self, simulation, profile, shell, output, **kwargs):
        self.export_calls.append(kwargs)
        output.write_bytes(b"new archive")

    def mock_read(self, path):
        return self.old_files

    def test_deduplicates_and_keeps_manufacturing_bytes(self):
        output = self.root / "result"
        with (patch.object(realign, "read_archive", side_effect=self.mock_read),
              patch.object(realign, "verify_package"),
              patch.object(realign, "assemble", side_effect=self.mock_assemble),
              patch.object(realign, "export_skin", side_effect=self.mock_export)):
            report = realign.migrate(self.inventory, self.profile, output, "2.0.0")
        self.assertEqual(len(self.assemble_calls), 1)
        self.assertEqual(self.assemble_calls[0], (b"original shell", b"original ams"))
        self.assertEqual(len(self.export_calls), 1)
        self.assertEqual(self.export_calls[0]["version"], "2.0.0")
        self.assertEqual(self.export_calls[0]["package_id"], "bee-a")
        self.assertEqual(report["distinct_source_contents"], 1)
        self.assertFalse(report["sources"][0]["deduplicated"])
        self.assertTrue(report["sources"][1]["deduplicated"])
        self.assertEqual((output / "skins" / "a.skin").read_bytes(), b"new archive")
        self.assertEqual((output / "skins" / "b.skin").read_bytes(), b"new archive")
        self.assertEqual(self.sources[0].read_bytes(), b"identical archive")
        self.assertFalse(report["physical_fit_tested"])

    def test_failure_keeps_output_absent_and_sources_unchanged(self):
        output = self.root / "failed"
        with (patch.object(realign, "read_archive", return_value=self.old_files),
              patch.object(realign, "verify_package"),
              patch.object(realign, "assemble", side_effect=ValueError("bad seam"))):
            with self.assertRaisesRegex(ValueError, "bad seam"):
                realign.migrate(self.inventory, self.profile, output, "2.0.0")
        self.assertFalse(output.exists())
        self.assertEqual(self.sources[0].read_bytes(), b"identical archive")

    def test_rejects_wrong_inventory_hash_before_output(self):
        inventory = json.loads(self.inventory.read_text(encoding="utf-8"))
        inventory["skin_archives"][0]["sha256"] = "0" * 64
        self.inventory.write_text(json.dumps(inventory), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            realign.migrate(self.inventory, self.profile, self.root / "no-output", "2.0.0")
        self.assertFalse((self.root / "no-output").exists())

    def test_profile_drift_aborts_publication(self):
        original_export = self.mock_export

        def drift(*args, **kwargs):
            original_export(*args, **kwargs)
            self.profile.write_text('{"id":"changed"}', encoding="utf-8")

        output = self.root / "drifted"
        with (patch.object(realign, "read_archive", return_value=self.old_files),
              patch.object(realign, "verify_package"),
              patch.object(realign, "assemble", side_effect=self.mock_assemble),
              patch.object(realign, "export_skin", side_effect=drift)):
            with self.assertRaisesRegex(ValueError, "profile changed"):
                realign.migrate(self.inventory, self.profile, output, "2.0.0")
        self.assertFalse(output.exists())

    def test_new_preview_is_rendered_outside_assembly(self):
        def fake_render(command, **kwargs):
            self.assertTrue(kwargs["check"])
            preview = Path(command[command.index("--render") + 1])
            self.assertNotIn("assembled", preview.parts)
            preview.write_bytes(b"\x89PNG\r\n\x1a\n")

        output = self.root / "previewed"
        with (patch.object(realign, "read_archive", return_value=self.old_files),
              patch.object(realign, "verify_package"),
              patch.object(realign, "assemble", side_effect=self.mock_assemble),
              patch.object(realign, "export_skin", side_effect=self.mock_export),
              patch.object(realign.subprocess, "run", side_effect=fake_render)):
            report = realign.migrate(self.inventory, self.profile, output, "2.0.0",
                                     render_preview=True)
        self.assertTrue(report["new_preview_rendered"])
        self.assertEqual(self.export_calls[0]["preview"].name, "preview.png")


if __name__ == "__main__":
    unittest.main()
