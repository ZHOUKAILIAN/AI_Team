from __future__ import annotations

import os
from pathlib import Path


def _default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def default_state_root(*, repo_root: Path, codex_home: Path | None = None) -> Path:
    del codex_home
    return repo_root.resolve() / ".ai-team"
