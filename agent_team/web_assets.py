from __future__ import annotations

import shutil
import sys
from importlib.resources import files
from pathlib import Path


def bundled_web_dist() -> Path:
    return Path(str(files("agent_team").joinpath("web_dist")))


def resolve_web_dist(web_dist: Path | None = None) -> Path:
    if web_dist is not None:
        return web_dist
    bundled = bundled_web_dist()
    if (bundled / "index.html").exists():
        return bundled
    editable_dist = Path(__file__).resolve().parents[1] / "apps" / "web" / "dist"
    if (editable_dist / "index.html").exists():
        return editable_dist
    return bundled


def copy_web_dist(source: Path | None = None, destination: Path | None = None) -> list[Path]:
    source_dir = source or Path(__file__).resolve().parents[1] / "apps" / "web" / "dist"
    destination_dir = destination or bundled_web_dist()
    if not (source_dir / "index.html").exists():
        raise FileNotFoundError(f"React web build not found at {source_dir}. Run npm run build:web first.")
    if destination_dir.exists():
        shutil.rmtree(destination_dir)
    shutil.copytree(source_dir, destination_dir)
    return [path for path in destination_dir.rglob("*") if path.is_file()]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args != ["copy"]:
        raise SystemExit("Usage: python -m agent_team.web_assets copy")
    written = copy_web_dist()
    print(f"copied_web_assets: {len(written)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
