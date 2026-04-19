from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path


def package_version(pyproject_path: Path) -> str:
    return tomllib.loads(pyproject_path.read_text())["project"]["version"]


def version_from_tag(tag: str) -> str:
    return tag.removeprefix("refs/tags/").removeprefix("v")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args()

    expected = package_version(args.pyproject)
    actual = version_from_tag(args.tag)
    if actual != expected:
        print(f"tag {actual} does not match package version {expected}", file=sys.stderr)
        return 1

    print(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
