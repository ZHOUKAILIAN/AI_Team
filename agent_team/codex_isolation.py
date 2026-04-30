from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


@contextmanager
def isolated_codex_env() -> Iterator[dict[str, str]]:
    with TemporaryDirectory(prefix="agent-team-codex-home-") as temp_dir:
        target_home = Path(temp_dir)
        prepare_isolated_codex_home(source_home=default_codex_home(), target_home=target_home)
        env = os.environ.copy()
        env["CODEX_HOME"] = str(target_home)
        yield env


def prepare_isolated_codex_home(*, source_home: Path, target_home: Path) -> None:
    target_home.mkdir(parents=True, exist_ok=True)
    _copy_file_if_exists(source_home / "auth.json", target_home / "auth.json")

    source_config = source_home / "config.toml"
    if source_config.exists():
        sanitized_config = sanitize_codex_config(source_config.read_text())
        (target_home / "config.toml").write_text(sanitized_config)


def sanitize_codex_config(text: str) -> str:
    lines: list[str] = []
    skip_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if _starts_filtered_section(stripped):
            skip_section = True
            continue
        if stripped.startswith("["):
            skip_section = False
        if not skip_section:
            lines.append(line)
    return "\n".join(lines).rstrip() + "\n"


def _starts_filtered_section(stripped_line: str) -> bool:
    return (
        stripped_line.startswith("[mcp_servers.")
        or stripped_line == "[mcp_servers]"
        or stripped_line.startswith("[plugins.")
        or stripped_line == "[plugins]"
        or stripped_line.startswith("[marketplaces.")
        or stripped_line == "[marketplaces]"
        or stripped_line == "[[skills.config]]"
    )


def _copy_file_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copy2(source, destination)
