from pathlib import Path
import hashlib
import json
import stat
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from shellflow.package_io import (Limits, PackageError, extract_files, file_records, json_object,
                                  parse_xml, read_archive, safe_path, validate_files, write_archive)


class PackageTransportTests(unittest.TestCase):
    def test_portable_paths_reject_cross_platform_escapes(self):
        for name in ("/etc/passwd", "../x", "a/../x", "a//x", "a/./x", "C" + ":/x", "a\\b",
                     "a:stream", "NUL.txt", "com1.xml", "a. /x", "a./x", "a /x", "x\x00y", "e\u0301.txt"):
            with self.subTest(name=name), self.assertRaises(PackageError):
                safe_path(name)
        self.assertEqual(safe_path("\u6a21\u578b/\u58f3.stl"), "\u6a21\u578b/\u58f3.stl")

    def test_deterministic_archive_and_new_destination_only(self):
        files = {"\u6a21\u578b/\u58f3.stl": b"mesh", "scene.xml": b"<mujoco/>"}
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.map", Path(tmp) / "b.map"
            write_archive(a, files)
            write_archive(b, dict(reversed(list(files.items()))))
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(read_archive(a), files)
            with self.assertRaises(FileExistsError):
                write_archive(a, files)
            target = Path(tmp) / "imported"
            extract_files(files, target)
            self.assertEqual((target / "\u6a21\u578b/\u58f3.stl").read_bytes(), b"mesh")
            with self.assertRaises(FileExistsError):
                extract_files(files, target)

    def test_hash_inventory_rejects_tamper_and_extra_files(self):
        files = {"scene.xml": b"<mujoco/>"}
        manifest = {"files": file_records(files)}
        files["scene-package.json"] = json.dumps(manifest).encode()
        validate_files(manifest, files, "scene-package.json")
        for changed in ({**files, "scene.xml": b"tampered"}, {**files, "evil.py": b"pass"},
                        {"scene-package.json": files["scene-package.json"]}):
            with self.assertRaises(PackageError):
                validate_files(manifest, changed, "scene-package.json")

    def test_zip_links_collisions_and_budgets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.map"
            for names in (("a", "A"), ("a", "a/b"), ("a", "a/b/"), ("../escape",), ("NUL",)):
                with zipfile.ZipFile(path, "w") as archive:
                    for name in names:
                        archive.writestr(name, b"x")
                with self.subTest(names=names), self.assertRaises(PackageError):
                    read_archive(path)
            with zipfile.ZipFile(path, "w") as archive:
                entry = zipfile.ZipInfo("link")
                entry.create_system = 3
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(entry, b"../outside")
            with self.assertRaises(PackageError):
                read_archive(path)
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("large", b"0" * 2000)
            with self.assertRaises(PackageError):
                read_archive(path, limits=Limits(file_bytes=100))
            with self.assertRaises(PackageError):
                read_archive(path, limits=Limits(expanded_bytes=100))

    def test_xml_and_json_parser_ambiguities_rejected(self):
        for data in (b'<!DOCTYPE a [<!ENTITY x "x">]><a>&x;</a>',
                     '<!DOCTYPE a><a/>'.encode("utf-16"), b'<?xml version="1.0" encoding="latin1"?><a/>'):
            with self.assertRaises(PackageError):
                parse_xml(data)
        for data in (b'{"id":"a","id":"b"}', b'{"v":NaN}', b'{"v":1e999}', b'[]'):
            with self.assertRaises(PackageError):
                json_object(data)


if __name__ == "__main__":
    unittest.main()
