"""Protect fixed input identity independently of editable dataset sidecars."""
from pathlib import Path
import json
import shutil

import pytest

from astromembench.benchmark import bank_identity, _safe_path, iter_bank

ROOT = Path(__file__).resolve().parents[1]


def test_image_changes_cannot_keep_the_same_data_identity(tmp_path):
    data = tmp_path / "data"
    (data / "assets").mkdir(parents=True)
    for name in ["manifest.json", "assets/manifest.json"]:
        shutil.copyfile(ROOT / "data/benchmark" / name, data / name)
    expected = bank_identity(data)
    manifest = json.loads((data / "assets/manifest.json").read_text(encoding="utf-8"))
    manifest["assets"][0]["sha256"] = "0" * 64
    (data / "assets/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Image identities"):
        bank_identity(data)
    assert len(expected) == 64


def test_dataset_manifest_paths_cannot_escape_the_data_directory(tmp_path):
    for relative in ["../outside.json", str(tmp_path.parent / "outside.json"), "..\\outside.json"]:
        with pytest.raises(ValueError):
            _safe_path(tmp_path, relative)


def test_unknown_case_is_rejected_before_opening_the_large_bank():
    with pytest.raises(ValueError, match="Unknown case"):
        list(iter_bank(ROOT / "data/benchmark", case_ids=["NOT-A-CASE"]))
