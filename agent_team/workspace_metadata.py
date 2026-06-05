from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import tomllib

from .models import model_dataclass


@model_dataclass
class WorkspaceMetadata:
    project_name: str
    project_root: str
    worktree_path: str
    branch: str
    state_root: str
    updated_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, object], *, state_root: Path) -> "WorkspaceMetadata":
        return cls(
            project_name=str(payload.get("project_name") or state_root.name),
            project_root=str(payload.get("project_root") or ""),
            worktree_path=str(payload.get("worktree_path") or ""),
            branch=str(payload.get("branch") or ""),
            state_root=str(payload.get("state_root") or state_root.resolve()),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def refresh_workspace_metadata(*, state_root: Path, repo_root: Path) -> WorkspaceMetadata:
    state_root = state_root.resolve()
    repo_root = repo_root.resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = _project_root(repo_root)

    metadata = WorkspaceMetadata(
        project_name=_project_name(project_root=project_root),
        project_root=str(project_root),
        worktree_path=str(repo_root),
        branch=_current_branch(repo_root),
        state_root=str(state_root),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    (state_root / "workspace.json").write_text(json.dumps(metadata.to_dict(), indent=2))
    return metadata


def load_workspace_metadata(state_root: Path) -> WorkspaceMetadata:
    state_root = state_root.resolve()
    metadata_path = state_root / "workspace.json"
    if not metadata_path.exists():
        return WorkspaceMetadata(
            project_name=state_root.name,
            project_root="",
            worktree_path="",
            branch="",
            state_root=str(state_root),
            updated_at="",
        )

    try:
        payload = json.loads(metadata_path.read_text())
    except json.JSONDecodeError:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}
    return WorkspaceMetadata.from_dict(payload, state_root=state_root)


def _current_branch(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""

    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _project_root(repo_root: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return repo_root

    if result.returncode != 0:
        return repo_root
    raw_common_dir = result.stdout.strip()
    if not raw_common_dir:
        return repo_root
    common_dir = Path(raw_common_dir)
    if not common_dir.is_absolute():
        common_dir = repo_root / common_dir
    common_dir = common_dir.resolve()
    if common_dir.name == ".git":
        return common_dir.parent
    return repo_root


def _project_name(*, project_root: Path) -> str:
    pyproject_path = project_root / "pyproject.toml"
    if pyproject_path.exists():
        try:
            payload = tomllib.loads(pyproject_path.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            payload = {}
        if isinstance(payload, dict):
            project_payload = payload.get("project", {})
            if isinstance(project_payload, dict):
                name = str(project_payload.get("name") or "").strip()
                if name:
                    return name
    return project_root.name
