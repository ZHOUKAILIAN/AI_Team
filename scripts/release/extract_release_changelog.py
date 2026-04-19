from __future__ import annotations

import argparse
import sys
from pathlib import Path


def extract_version_section(markdown: str, version: str) -> str:
    header = f"## [{version}]"
    lines = markdown.splitlines()
    start = next((index for index, line in enumerate(lines) if line.startswith(header)), None)
    if start is None:
        raise ValueError(f"CHANGELOG.md is missing a section for {version}")

    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## [")), len(lines))
    return "\n".join(lines[start:end]).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--changelog", type=Path, required=True)
    args = parser.parse_args()

    try:
        print(extract_version_section(args.changelog.read_text(), args.version), end="")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
