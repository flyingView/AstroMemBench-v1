"""Build reproducible release archives from an explicit publication allowlist."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
ROOT_FILES = ["README.md", "README.zh-CN.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
              "pyproject.toml", "MANIFEST.in", ".gitignore", ".gitattributes", "Start AstroMemBench.cmd"]
SOURCE_TREES = {"src": {".py", ".html", ".css", ".js"},
                "docs": {".md", ".png"}, "examples": {".py", ".json"},
                "scripts": {".py"}, "tests": {".py", ".json"}, ".github": {".yml"}}


def source_files():
    result = [ROOT / name for name in ROOT_FILES]
    for directory, suffixes in SOURCE_TREES.items():
        result.extend(path for path in (ROOT / directory).rglob("*")
                      if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts)
    return sorted(set(result))


def dataset_files():
    import json
    root = ROOT / "data/benchmark"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    result = [root / "manifest.json"]
    for relative, expected in manifest["files"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError(f"Invalid dataset member: {relative}")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != expected["sha256"] or path.stat().st_size != expected["bytes"]:
            raise ValueError(f"Dataset changed: {relative}")
        result.append(path)
    return sorted(set(result))


def archive(path, files, prefix=""):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for source in files:
            relative = source.relative_to(ROOT).as_posix()
            member = zipfile.ZipInfo(prefix + relative, date_time=(2026, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            member.external_attr = 0o644 << 16
            with source.open("rb") as reader, output.open(member, "w", force_zip64=True) as writer:
                for block in iter(lambda: reader.read(1024 * 1024), b""):
                    writer.write(block)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = dataset_files()
    products = [args.output / f"astromembench-benchmark-v{VERSION}.zip",
                args.output / f"astromembench-{VERSION}.zip"]
    archive(products[0], data)
    archive(products[1], source_files() + data, prefix=f"astromembench-{VERSION}/")
    lines = []
    for path in products:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        lines.append(f"{digest}  {path.name}")
        print(f"{path.name}: {path.stat().st_size:,} bytes")
    (args.output / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
