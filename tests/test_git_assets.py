"""Git must preserve frozen asset bytes while normalizing ordinary source text."""
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GitAssetTests(unittest.TestCase):
    def test_frozen_crlf_assets_survive_add_and_checkout(self):
        protected = (
            "library/catalog.json",
            "library/assets/example/asset.json",
            "library/simulations/example/robot.xml",
            "library/simulations/example/robot.urdf",
            "library/simulations/example/README.md",
            "library/simulations/example/preview.py",
            "robots/hexa-v1/profile.json",
            "robots/hexa-v1/baseline.xml",
            "robots/hexa-v1/seam-reference.json",
            "src/shellflow/simulation.py",
            "src/shellflow/urdf.py",
            "scripts/preview_simulation.py",
        )
        source = "src/example.py"
        raw = b"frozen first line\r\nfrozen second line\r\n"
        normalized = raw.replace(b"\r\n", b"\n")
        for autocrlf in ("true", "false"):
            with self.subTest(autocrlf=autocrlf), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)

                def git(*args):
                    return subprocess.run(
                        ["git", "-C", str(root), *args], capture_output=True,
                        check=True,
                    ).stdout

                git("init", "--quiet")
                git("config", "core.autocrlf", autocrlf)
                # Keep user-global attributes and safecrlf policies out of this fixture.
                empty_attributes = root / ".git" / "empty-attributes"
                empty_attributes.write_bytes(b"")
                git("config", "core.attributesFile", str(empty_attributes))
                git("config", "core.safecrlf", "false")
                (root / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
                for name in (*protected, source):
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                git("add", "--", ".gitattributes", *protected, source)
                for name in (*protected, source):
                    expected = normalized if name == source else raw
                    self.assertEqual(git("show", ":" + name), expected, name)
                    # Force a real checkout to restore data from the index, not cached files.
                    (root / name).write_bytes(b"replace me before checkout")
                git("checkout-index", "--force", "--all")
                for name in (*protected, source):
                    expected = normalized if name == source else raw
                    self.assertEqual((root / name).read_bytes(), expected, name)


if __name__ == "__main__":
    unittest.main()
