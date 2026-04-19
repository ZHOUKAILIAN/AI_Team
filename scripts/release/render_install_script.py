from __future__ import annotations

import argparse
from pathlib import Path


def render_install_script(
    *,
    repo: str,
    tag: str,
    version: str,
    wheel: str,
    template_path: Path,
) -> str:
    content = template_path.read_text()
    replacements = {
        "{{ repo }}": repo,
        "{{ tag }}": tag,
        "{{ version }}": version,
        "{{ wheel }}": wheel,
    }
    for token, value in replacements.items():
        content = content.replace(token, value)
    return content


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--wheel", required=True)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).with_name("install.sh.template"),
    )
    args = parser.parse_args()

    print(
        render_install_script(
            repo=args.repo,
            tag=args.tag,
            version=args.version,
            wheel=args.wheel,
            template_path=args.template,
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
