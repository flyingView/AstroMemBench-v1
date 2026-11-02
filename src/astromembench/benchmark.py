"""Stream and verify the immutable dataset distributed with version 1.0.0."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from .schema import Task

BANK_SHA256 = "637209e356e134641a8f8779801918a35cfcc48e76e9e4fd76313b8600cdf41c"
BANK_BYTES = 788488913
VISUAL_MANIFEST_SHA256 = "dcbbf2f941f856c653623a347565e98919aecf6e165941799edc0b9e3135242c"
TASK_COUNT = 2240
TEMPLATE_COUNT = 140
EXPECTED_ASSETS = {'landmarks/a01.jpg': 'e58f22d989a5cb3a486df0891662e965dec3ba65e6e4a5d07934734e1afa77b7',
 'landmarks/a02.jpg': '5a5bc3e2411f3667dd26132fe9aee8b435fc49e567a2dea6cb5c62ba90d63bd8',
 'landmarks/a03.jpg': '1f170e2876b212633ac2f46280f3e545ec0aca6130b229976f2057441d2ac519',
 'landmarks/a04.jpg': '484e89379abbb81b36d8d390a463216b6a6d7f68cb717ce1519644a50a6980c5',
 'landmarks/a05.jpg': 'e750ed54a731b6916898d945a3bc791cf5fe1b77bf10ff20f094316ff34f438e',
 'landmarks/a06.jpg': '4abeea6d57599bbeb37575c17637d8e2183282a7bc3a4f3bcc964b5cedb8e794',
 'landmarks/a07.jpg': '0fe1c246004b82ca264826c3c53991161e8408c6821a2e00a13f2b259cbcf8be',
 'landmarks/a08.jpg': '269dfb0de437334e1a42aeff24bed12acbf5510db82f5509d13316db3e15812e',
 'landmarks/a09.jpg': 'cd13a229ad66da98ceb6b7459a3f468afd74b01d02a09453de1cc6406c6ae2ac',
 'landmarks/a10.jpg': '34d6fa93bef244c93be3d9c32566786ba934a6f750f01f773fb4e9f9befaac4b',
 'landmarks/a11.jpg': 'f162368192748e01b395c87fd5432700f9b8a1dc4e17e63fd7e31d79bd96cedf',
 'landmarks/a12.jpg': '0ea149ec400b712c4c270576aec853f9d16a2a86f81c0f475e97b17e2a0644db',
 'landmarks/a13.jpg': '5eb3d44ccaa8c836cf9e0e71dfce8c564ceee2bf086f708b61b42c7e9dfe49f5',
 'landmarks/p1-gallery/a01.jpg': '33f6b5e0d7284446554e9990d87a63b9ea4f3bbdd5aba5a0ef2ac315d15afff0',
 'landmarks/p1-gallery/a03.jpg': '397193a1b36caf1ab124682c244de051a2074d2da1051bb39da322e25d1d046a',
 'landmarks/p1-gallery/a05.jpg': 'e5cd84bfae9046abae2c5b9ffdb1e16b20be8909bb15dccadbec3c7c9c5a2ad6',
 'landmarks/p1-gallery/a07.png': 'b4d6eecb70fe35d6baa65a9dbf98560497e4899ac3050de11b03f9b560e42bcb',
 'landmarks/p1-gallery/a09.jpg': 'ef0e3542a9b148c003c875c0db9e3ff6b0aeb3157b41bcc69939e35699bf3cbd',
 'landmarks/p1-gallery/a10.jpg': 'd7edd91a149048bbc30ebae03ef1aca8af1478a77dd40de30dc263f8c73e45fc',
 'landmarks/p1-gallery/a11.jpg': '68104535d194698d0f24c4260898865fddd82bdba3e91cef92fb02305814edd0',
 'landmarks/p1-gallery/a12.jpg': 'e382cb6c26fe8cef320716287196f3e8b635756dad68c09121d36055b550b360',
 'landmarks/p1-gallery/a13.jpg': 'aea641a4ef3a13fafbc7a358ecc5cb42e9d1e2044c888f46385eb5e5f773bd46'}


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(
            f"Dataset file is missing: {path}. Extract the benchmark Release archive "
            "and pass its data/benchmark directory with --data."
        ) from exc
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"Invalid dataset metadata: {path}") from exc


def _safe_path(data, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("Dataset manifest paths must be relative POSIX paths")
    root = Path(data).resolve()
    path = root / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(root):
        raise ValueError("Dataset manifest path escapes the dataset directory")
    return path


def _hash(path):
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assets_path(data):
    return Path(data).resolve() / "assets"


def bank_identity(data):
    """Dataset identity is independent of its extraction directory."""
    manifest = _read_json(Path(data) / "manifest.json")
    declaration = manifest.get("files", {}).get("tasks.jsonl", {})
    if declaration.get("sha256") != BANK_SHA256 or declaration.get("bytes") != BANK_BYTES:
        raise ValueError("This is not the fixed AstroMemBench 1.0.0 dataset")
    images = _read_json(Path(data) / "assets/manifest.json").get("assets", [])
    declared = {entry.get("path"): entry.get("sha256") for entry in images if isinstance(entry, dict)}
    if len(images) != len(EXPECTED_ASSETS) or declared != EXPECTED_ASSETS:
        raise ValueError("Image identities differ from the fixed AstroMemBench dataset")
    identity = {"tasks.jsonl": BANK_SHA256, **{"assets/" + key: value for key, value in EXPECTED_ASSETS.items()}}
    return sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def load_index(data):
    index = _read_json(Path(data) / "index.json")
    rows = index.get("cases") if isinstance(index, dict) else None
    if not isinstance(rows, list) or len(rows) != TASK_COUNT:
        raise ValueError("Dataset index must contain all 2240 cases")
    identities = [row.get("case_id") for row in rows if isinstance(row, dict)]
    if len(identities) != TASK_COUNT or any(not isinstance(v, str) for v in identities) or len(set(identities)) != TASK_COUNT:
        raise ValueError("Dataset index contains invalid or duplicate case IDs")
    return index


def iter_bank(data, variant="noisy", case_ids=None):
    """Read one task at a time; selecting a subset never loads the whole bank."""
    if variant != "noisy":
        raise ValueError("This release contains the fixed full-history dataset only")
    requested = None if case_ids is None else set(case_ids)
    if requested is not None:
        known = {row["case_id"] for row in load_index(data)["cases"]}
        unknown = requested - known
        if unknown:
            raise ValueError("Unknown case ID(s): " + ", ".join(sorted(unknown)))
        if not requested:
            return
    path = Path(data) / "tasks.jsonl"
    if not path.is_file():
        raise ValueError(f"Dataset is missing: {path}. Extract the benchmark Release archive first.")
    remaining = None if requested is None else set(requested)
    with path.open("r", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"Empty dataset row at line {number}")
            try:
                row = json.loads(line)
                if remaining is not None and row.get("case_id") not in remaining:
                    continue
                task = Task.from_dict(row)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise ValueError(f"Invalid dataset row at line {number}: {exc}") from exc
            yield task
            if remaining is not None:
                remaining.remove(task.case_id)
                if not remaining:
                    return
    if remaining:
        raise ValueError("Dataset is missing case(s): " + ", ".join(sorted(remaining)))


def load_bank(data, variant="noisy", case_ids=None):
    """Load an explicitly selected small subset; use iter_bank for a full run."""
    if case_ids is None:
        raise ValueError("Use iter_bank to stream the complete dataset, or provide case_ids")
    return list(iter_bank(data, variant=variant, case_ids=case_ids))


def validate_bank(data):
    """Verify release checksums and every task without regenerating anything."""
    root = Path(data).resolve()
    bank_identity(root)
    manifest = _read_json(root / "manifest.json")
    if manifest.get("schema") != "astromembench/fixed-bank/1":
        raise ValueError("Unsupported dataset manifest")
    files = manifest.get("files")
    required = {"tasks.jsonl", "index.json", "assets/manifest.json", "assets/sources.json"}
    if not isinstance(files, dict) or not required.issubset(files):
        raise ValueError("Dataset manifest is incomplete")
    if files["assets/manifest.json"] != {"bytes": 6558, "sha256": VISUAL_MANIFEST_SHA256}:
        raise ValueError("The reviewed image metadata is missing or changed. Extract the v1.0.1 benchmark archive.")
    for relative, expected in files.items():
        if not isinstance(expected, dict):
            raise ValueError(f"Invalid manifest entry: {relative}")
        path = _safe_path(root, relative)
        if not path.is_file():
            raise ValueError(f"Dataset file is missing: {relative}")
        if path.stat().st_size != expected.get("bytes") or _hash(path) != expected.get("sha256"):
            raise ValueError(f"Dataset checksum mismatch: {relative}. Extract a fresh Release archive.")
    images = _read_json(root / "assets/manifest.json").get("assets", [])
    if not isinstance(images, list) or len(images) != 22:
        raise ValueError("The fixed visual tasks require 22 image files")
    for entry in images:
        relative = "assets/" + entry["path"]
        if relative not in files or files[relative].get("sha256") != entry.get("sha256"):
            raise ValueError(f"Image is not covered by the release manifest: {relative}")
    index = load_index(root)
    expected_rows = iter(index["cases"])
    counts = Counter()
    identities = set()
    for task in iter_bank(root):
        if task.case_id in identities:
            raise ValueError(f"Duplicate case: {task.case_id}")
        identities.add(task.case_id)
        counts[task.template] += 1
        expected = next(expected_rows, None)
        if expected != {"case_id": task.case_id, "template": task.template, "difficulty": task.difficulty}:
            raise ValueError("Dataset index differs from task order or identity")
    if len(identities) != TASK_COUNT or len(counts) != TEMPLATE_COUNT or set(counts.values()) != {16}:
        raise ValueError("Expected 2240 cases across 140 templates, with 16 cases per template")
    return {"version": "1.0.0", "task_count": len(identities), "template_count": len(counts),
            "history_rounds": 30, "image_count": len(images), "sha256": BANK_SHA256,
            "data": str(root)}
