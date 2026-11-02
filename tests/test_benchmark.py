"""Protect fixed input identity independently of editable dataset sidecars."""
from pathlib import Path
import json
import shutil

import pytest

from astromembench.benchmark import bank_identity, _safe_path, iter_bank, validate_bank
from astromembench.environment import Environment
from astromembench.payloads import attach_images
from astromembench.tasks import template_module

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


def test_validation_rejects_a_substituted_visual_audit_manifest(tmp_path):
    source = ROOT / "data/benchmark"
    (tmp_path / "assets").mkdir()
    shutil.copyfile(source / "assets/manifest.json", tmp_path / "assets/manifest.json")
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest["files"]["assets/manifest.json"]["sha256"] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="reviewed image metadata"):
        validate_bank(tmp_path)


def test_public_visual_packets_reconstruct_all_32_scored_locations():
    data = ROOT / "data/benchmark"
    assets = data / "assets"
    if not (assets / "landmarks").is_dir():
        pytest.skip("Install the benchmark images for visual replay")
    templates = ("FM-E3-P1", "FM-E3-P2")
    ids = {f"{name}-{i:03d}" for name in templates for i in range(1, 17)}
    # CI checkouts include the images and template sources. Release archives
    # additionally exercise the actual frozen tasks with their background records.
    tasks = (iter_bank(data, case_ids=ids) if (data / "tasks.jsonl").exists() else
             (template_module(name).build(i) for name in templates for i in range(16)))
    replayed = set()
    for task in tasks:
        module = template_module(task.template)
        env = Environment(task)
        history = [attach_images(event.public_input(), assets) for event in task.history]
        current = attach_images(env.observation(), assets)
        facts = module.reconstruct(history, current, assets=assets)
        module.check_world(task, facts)
        env.step(module.next_action(facts, current))
        assert env.result()["score"] == 100, task.case_id
        replayed.add(task.case_id)
    assert replayed == ids
