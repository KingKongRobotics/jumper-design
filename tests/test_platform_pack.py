from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


pack = module("platform_pack")
publish = module("check_publish")


class PlatformPackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.content = b"synthetic CAD fixture\n"
        self.manifest = {"schema_version": 1, "id": "test-platform", "redistribution_status": "unconfirmed",
            "files": [{"role": "source_step", "path": "source.step", "bytes": len(self.content),
                       "sha256": hashlib.sha256(self.content).hexdigest()}]}

    def archive(self, changes=None, manifest=None, extras=None):
        target = self.base / "input.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("platform.json", json.dumps(manifest or self.manifest))
            archive.writestr("source.step", self.content if changes is None else changes)
            for name, data in extras or []:
                archive.writestr(name, data)
        return target

    def test_install_readback_and_no_overwrite(self):
        source = self.archive()
        destination = self.base / "installed"
        result = pack.install_pack(source, destination)
        self.assertEqual(result["asset_count"], 1)
        self.assertEqual((destination / "test-platform/source.step").read_bytes(), self.content)
        with self.assertRaises(pack.PackError):
            pack.install_pack(source, destination)

    def test_rejects_parent_traversal(self):
        source = self.archive(extras=[("../outside", b"bad")])
        with self.assertRaises(pack.PackError):
            pack.install_pack(source, self.base / "installed")
        self.assertFalse((self.base / "outside").exists())

    def test_rejects_corrupt_asset_without_installing(self):
        source = self.archive(changes=b"x" * len(self.content))
        with self.assertRaises(pack.PackError):
            pack.install_pack(source, self.base / "installed")
        self.assertFalse((self.base / "installed/test-platform").exists())

    def test_rejects_symlink(self):
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        source = self.archive(extras=[(link, b"source.step")])
        with self.assertRaises(pack.PackError):
            pack.inspect_archive(source)

    def test_rejects_windows_case_collision(self):
        source = self.archive(extras=[("SOURCE.STEP", self.content)])
        with self.assertRaises(pack.PackError):
            pack.inspect_archive(source)

    def test_rejects_absolute_and_device_names(self):
        for value in ["/outside", "../outside", "a/../b", "a\\b", "con", "a:", "folder/aux.txt", "x."]:
            with self.subTest(value=value), self.assertRaises(pack.PackError):
                pack.safe_relative(value)

    def test_rejects_declared_excessive_size(self):
        self.manifest["files"][0]["bytes"] = pack.MAX_FILE_BYTES + 1
        source = self.archive()
        with self.assertRaises(pack.PackError):
            pack.inspect_archive(source)

    def test_export_only_declared_assets(self):
        suite = self.base / "suite"
        (suite / "platforms").mkdir(parents=True)
        (suite / "private-input").mkdir()
        (suite / "private-input/source.step").write_bytes(self.content)
        (suite / "private-input/unrelated.glb").write_bytes(b"not included")
        descriptor = {"id": "test-platform", "units": "millimeter", "files": [
            {**self.manifest["files"][0], "path": "private-input/source.step", "copy_as": "source.step"}]}
        (suite / "platforms/test-platform.json").write_text(json.dumps(descriptor), encoding="utf-8")
        archive = self.base / "output.zip"
        result = pack.export_pack(suite, "test-platform", archive)
        self.assertEqual(result["asset_count"], 1)
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(set(bundle.namelist()), {"source.step", "platform.json", pack.METADATA})
        with self.assertRaises(pack.PackError):
            pack.export_pack(suite, "test-platform", archive)


class PublicationTests(unittest.TestCase):
    def repository(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        subprocess.run(["git", "init", str(root)], capture_output=True, check=True)
        return root

    def stage_bytes_without_filters(self, root, name, content):
        """Place exact bytes in the real index, even when a global LFS clean filter exists."""
        oid = subprocess.run(["git", "-C", str(root), "hash-object", "-w", "--stdin"],
                             input=content, capture_output=True, check=True).stdout.decode().strip()
        subprocess.run(["git", "-C", str(root), "update-index", "--add", "--cacheinfo", "100644", oid, name],
                       capture_output=True, check=True)

    def lfs_pointer(self, content):
        return ("version https://git-lfs.github.com/spec/v1\n"
                "oid sha256:" + hashlib.sha256(content).hexdigest() + "\nsize " + str(len(content)) + "\n").encode()

    def test_environment_examples_are_not_secrets(self):
        sample = ('api_key = "${PROVIDER_API_KEY}"\npassword = "<YOUR_PASSWORD_VALUE>"\n'
                  'api_key = $PROVIDER_API_KEY\naccess_token: ${PROVIDER_ACCESS_TOKEN}\n'
                  'Authorization: Bearer ${PROVIDER_ACCESS_TOKEN}\n')
        self.assertEqual(publish.text_findings(sample.encode()), [])

    def test_unquoted_and_utf16_credentials_are_detected(self):
        value = "abcd1234" * 4
        for sample in ("api" + "_key: " + value, "Authorization: Bear" + "er " + value):
            for encoding in ("utf-8", "utf-16", "utf-32"):
                with self.subTest(encoding=encoding):
                    findings = publish.text_findings(sample.encode(encoding))
                    self.assertEqual(findings, [("suspected_credential", 1)])

    def test_secret_and_path_report_omit_values(self):
        secret = "sk" + "-" + "aBcDef1234567890" * 2
        machine_path = "Q" + ":" + "/example/private.bin"
        findings = publish.text_findings((secret + "\n" + machine_path).encode())
        self.assertEqual({kind for kind, _ in findings}, {"suspected_credential", "machine_absolute_path"})
        self.assertNotIn(secret, json.dumps(findings))

    def test_index_is_checked_and_ignored_local_files_are_excluded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", str(root)], capture_output=True, check=True)
            (root / ".gitignore").write_text(".local/\n", encoding="utf-8")
            (root / ".local").mkdir()
            secret = "ghp" + "_" + "abcdefgh12345678" * 2
            (root / ".local/key.txt").write_text(secret, encoding="utf-8")
            (root / "config.txt").write_text(secret, encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "config.txt", ".gitignore"], check=True)
            (root / "config.txt").write_text("clean working copy", encoding="utf-8")
            report = publish.audit(root, 1024 * 1024)
            self.assertFalse(report["passed"])
            self.assertEqual(report["candidate_files"], 2)
            self.assertTrue(any(f["source"] == "index" for f in report["findings"]))
            self.assertFalse(any(f["file"].startswith(".local") for f in report["findings"]))

    def test_untracked_lfs_binary_is_exempt_and_not_read_in_full(self):
        root = self.repository()
        (root / ".gitattributes").write_text("*.stl filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")
        path = root / "model with spaces.stl"
        content = b"\x00" * (2 * 1024 * 1024)
        path.write_bytes(content)
        original = Path.read_bytes
        def guarded_read_bytes(candidate):
            if candidate == path:
                raise AssertionError("Large LFS binary must only receive a prefix probe")
            return original(candidate)
        with patch.object(Path, "read_bytes", guarded_read_bytes):
            report = publish.audit(root, 1024)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["lfs_files"], 1)
        self.assertEqual(report["lfs_working_tree_bytes"], len(content))
        self.assertEqual(report["lfs_index_files_checked"], 0)

    def test_real_index_lfs_pointer_passes_with_large_working_binary(self):
        root = self.repository()
        attributes = b"*.stl filter=lfs diff=lfs merge=lfs -text\n"
        (root / ".gitattributes").write_bytes(attributes)
        self.stage_bytes_without_filters(root, ".gitattributes", attributes)
        content = b"\x00" * 8192
        (root / "model.stl").write_bytes(content)
        self.stage_bytes_without_filters(root, "model.stl", self.lfs_pointer(content))
        report = publish.audit(root, 1024)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["lfs_files"], 1)
        self.assertEqual(report["lfs_index_files_checked"], 1)

    def test_raw_staged_binary_cannot_be_hidden_by_unstaged_lfs_rule(self):
        root = self.repository()
        (root / ".gitattributes").write_text("*.stl filter=lfs\n", encoding="utf-8")
        content = b"\x00" * 8192
        (root / "model.stl").write_bytes(content)
        self.stage_bytes_without_filters(root, "model.stl", content)
        report = publish.audit(root, 1024)
        self.assertFalse(report["passed"])
        self.assertTrue(any(f["type"] == "lfs_index_not_pointer" and f["source"] == "index" for f in report["findings"]))
        self.assertFalse(any(f["type"] == "file_exceeds_size_limit" and f["source"] == "working_tree" for f in report["findings"]))

    def test_cached_lfs_rule_still_requires_pointer_when_working_rule_removed(self):
        root = self.repository()
        self.stage_bytes_without_filters(root, ".gitattributes", b"*.stl filter=lfs\n")
        (root / ".gitattributes").write_text("", encoding="utf-8")
        (root / "model.stl").write_bytes(b"tiny raw mesh")
        self.stage_bytes_without_filters(root, "model.stl", b"tiny raw mesh")
        report = publish.audit(root, 1024)
        self.assertFalse(report["passed"])
        self.assertTrue(any(f["type"] == "lfs_index_not_pointer" for f in report["findings"]))

    def test_malformed_pointer_is_rejected_even_when_small(self):
        root = self.repository()
        (root / ".gitattributes").write_text("*.stl filter=lfs\n", encoding="utf-8")
        malformed = b"version https://git-lfs.github.com/spec/v1\noid sha256:abcd\nsize -1\n"
        (root / "model.stl").write_bytes(malformed)
        self.stage_bytes_without_filters(root, "model.stl", malformed)
        report = publish.audit(root, 1024)
        self.assertFalse(report["passed"])
        self.assertEqual({f["type"] for f in report["findings"]}, {"lfs_index_not_pointer", "invalid_lfs_worktree_pointer"})

    def test_large_non_lfs_binary_is_still_rejected(self):
        root = self.repository()
        (root / "model.bin").write_bytes(b"\x00" * 8192)
        report = publish.audit(root, 1024)
        self.assertFalse(report["passed"])
        self.assertTrue(any(f["type"] == "file_exceeds_size_limit" for f in report["findings"]))
        self.assertEqual(report["lfs_files"], 0)

    def test_lfs_text_is_still_scanned_beyond_prefix(self):
        root = self.repository()
        (root / ".gitattributes").write_text("*.txt filter=lfs\n", encoding="utf-8")
        secret = "ghp" + "_" + "abcdefgh12345678" * 2
        (root / "large.txt").write_text("harmless text line\n" * 1000 + secret + "\n", encoding="utf-8")
        report = publish.audit(root, 1024)
        self.assertFalse(report["passed"])
        self.assertTrue(any(f["type"] == "suspected_credential" and f.get("line") == 1001 for f in report["findings"]))
        self.assertFalse(any(f["type"] == "file_exceeds_size_limit" for f in report["findings"]))
        self.assertNotIn(secret, json.dumps(report))


if __name__ == "__main__":
    unittest.main()
