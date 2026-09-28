"""New package producers reject non-English public display metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shellflow.english_metadata import require_english_text
from shellflow.map_package import export_map
from shellflow.package_io import PackageError
from shellflow.skin_package import export_skin


def test_english_metadata_accepts_latin_and_rejects_decoded_unicode():
    require_english_text("Narrow Bridge", "title")
    require_english_text("Caf\u00e9 Course", "title")
    require_english_text("22.5°", "title")
    with pytest.raises(PackageError, match="English text"):
        require_english_text(json.loads('"\\u72ec\\u6728\\u6865"'), "title")


def test_skin_export_rejects_non_english_title_before_accessing_sources(tmp_path: Path):
    with pytest.raises(PackageError, match="skin title must be English"):
        export_skin(tmp_path / "absent-simulation", tmp_path / "absent-profile", None,
                    tmp_path / "out.skin", package_id="example", title="\u72ec\u6728\u6865")
    assert not (tmp_path / "out.skin").exists()


def test_map_export_rejects_decoded_description_before_compilation(tmp_path: Path):
    spec = tmp_path / "scene.json"
    spec.write_text(json.dumps({"name": "sample", "title": "Sample Scene",
                                "description": "\u72ec\u6728\u6865"}), encoding="utf-8")
    with pytest.raises(PackageError, match="map description must be English"):
        export_map(spec, tmp_path / "out.map", default_skin=tmp_path / "absent.skin",
                   profile=tmp_path / "absent-profile")
    assert not (tmp_path / "out.map").exists()
