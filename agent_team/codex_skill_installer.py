from __future__ import annotations

import os
from pathlib import Path

from .packaged_assets import copy_packaged_tree


def install_codex_skill(codex_home: Path | None = None) -> Path:
    root = codex_home or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    target = root / "skills" / "agent-team-workflow"
    copy_packaged_tree(("codex_skill", "agent-team-workflow"), target)
    return target
