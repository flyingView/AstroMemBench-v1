"""Start the UI from a source checkout or the extracted release directory."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    try:
        import psutil  # noqa: F401 -- check the only runtime dependency first
        from astromembench.cli import main as cli
    except ImportError as exc:
        print(f"Missing dependency: {exc}. From {ROOT}, run: python -m pip install -e .", file=sys.stderr)
        return 2
    # Keep all relative adapter and output paths within this release directory.
    import os
    os.chdir(ROOT)
    return cli(["webui", "--data", str(ROOT / "data/benchmark"), "--port", "0", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
