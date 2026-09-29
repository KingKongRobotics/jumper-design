"""Regression checks for public English package metadata."""
import importlib.util
from pathlib import Path
import tempfile
import subprocess
import unittest
import zipfile
from shellflow.package_io import PackageError
from shellflow.skin_package import export_skin
from shellflow.english_metadata import require_english_text

SPEC = importlib.util.spec_from_file_location("check_english", Path(__file__).resolve().parents[1] / "scripts/check_english.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class EnglishPackageTests(unittest.TestCase):
    def test_readme_translation_exception_is_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            label = "".join(chr(n) for n in (0x7b80, 0x4f53, 0x4e2d, 0x6587))
            nav = "**English** | [" + label + "](README.zh-CN.md)"
            (root / "README.md").write_text(nav, encoding="utf-8")
            (root / "README.zh-CN.md").write_text(label, encoding="utf-8")
            self.assertTrue(MODULE.audit(root)["ok"])
            (root / "README.md").write_text(nav + "\n" + label, encoding="utf-8")
            self.assertIn("README.md: non-English repository text", MODULE.audit(root)["issues"])
            (root / "README.md").write_text(nav, encoding="utf-8")
            (root / "other.md").write_text(label, encoding="utf-8")
            self.assertIn("other.md: non-English repository text", MODULE.audit(root)["issues"])

    def test_ignore_rules_cannot_hide_compiler_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            compiler = root / "src/mjscene/build/compiler.py"
            compiler.parent.mkdir(parents=True)
            compiler.write_text("# Scene compiler\n", encoding="utf-8")
            ignore = root / ".gitignore"
            ignore.write_text("build/\n", encoding="utf-8")
            self.assertIn("src/mjscene/build/compiler.py: Python source excluded by Git ignore rules", MODULE.audit(root)["issues"])
            ignore.write_text("/build/\n", encoding="utf-8")
            self.assertTrue(MODULE.audit(root)["ok"])

    def test_new_skin_rejects_non_english_title_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "example.skin"
            with self.assertRaisesRegex(PackageError, "translate"):
                export_skin(Path(directory), Path(directory) / "profile.json", None,
                            output, package_id="example", title=chr(0x573A))
            self.assertFalse(output.exists())

    def test_numeric_and_scientific_labels_remain_supported(self):
        for label in ("123", "Ramp 7.13 degrees", "Surface coefficient = 0.5"):
            require_english_text(label, "title")

    def test_escaped_display_title_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.map"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("scene-package.json", '{"title":"\\u573a\\u666f"}')
            self.assertTrue(MODULE.check_package(path))

    def test_english_metadata_and_opaque_mesh_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.skin"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("skin-package.json", '{"title":"Silver Armor Guardian"}')
                archive.writestr("meshes/body.stl", bytes([255, 0, 128]))
            self.assertEqual(MODULE.check_package(path), [])

    def test_member_name_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.map"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(chr(0x573A) + ".png", b"opaque")
            self.assertTrue(MODULE.check_package(path))
