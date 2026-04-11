from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path


def default_state_root(*, repo_root: Path, codex_home: Path | None = None) -> Path:
    home = codex_home or _default_codex_home()
    return home / "ai-team" / "workspaces" / workspace_fingerprint(repo_root)


def workspace_fingerprint(repo_root: Path) -> str:
    resolved = str(repo_root.expanduser().resolve())
    slug = _slugify(repo_root.name)
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{digest}"


def _default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".codex"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "workspace"
