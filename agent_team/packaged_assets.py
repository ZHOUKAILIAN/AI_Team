from __future__ import annotations

from importlib.resources import files
from pathlib import Path


ASSET_ROOT = files("agent_team").joinpath("assets")


def packaged_text(*parts: str) -> str:
    return ASSET_ROOT.joinpath(*parts).read_text()


def copy_packaged_tree(parts: tuple[str, ...], destination: Path) -> list[Path]:
    source = ASSET_ROOT.joinpath(*parts)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            written.extend(copy_packaged_tree(parts + (item.name,), target))
            continue

        target.write_text(item.read_text())
        if target.suffix == ".sh":
            target.chmod(0o755)
        written.append(target)

    return written
