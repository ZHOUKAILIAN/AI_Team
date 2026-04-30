from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .harness_paths import _default_codex_home
from .models import GateResult, StageRunRecord, model_dataclass
from .state import StateStore
from .workspace_metadata import WorkspaceMetadata, load_workspace_metadata


@model_dataclass
class BoardSnapshot:
    payload: dict[str, Any]
    state_roots: list[Path]


def build_board_snapshot(*, codex_home: Path | None = None) -> dict[str, Any]:
    return build_board_snapshot_with_roots(codex_home=codex_home).payload


def build_board_snapshot_with_roots(*, codex_home: Path | None = None) -> BoardSnapshot:
    home = codex_home or _default_codex_home()
    workspaces_root = home / "agent-team" / "workspaces"
    state_roots = [path for path in sorted(workspaces_root.glob("*")) if path.is_dir()]
    projects_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    stats = {
        "projects": 0,
        "worktrees": 0,
        "sessions": 0,
        "blocked": 0,
        "waiting_human": 0,
        "submitted_runs": 0,
    }

    for state_root in state_roots:
        metadata = load_workspace_metadata(state_root)
        project_key = (metadata.project_root, metadata.project_name)
        project = projects_by_key.setdefault(
            project_key,
            {
                "project_name": metadata.project_name,
                "project_root": metadata.project_root,
                "worktrees": [],
            },
        )
        worktree = _worktree_payload(metadata)
        store = StateStore(state_root)
        for session_id in _session_ids(state_root):
            session_payload = _session_payload(store, session_id)
            if session_payload is None:
                continue
            stats["sessions"] += 1
            if session_payload["current_state"] == "Blocked":
                stats["blocked"] += 1
            if session_payload["current_state"] in {"WaitForCEOApproval", "WaitForHumanDecision"}:
                stats["waiting_human"] += 1
            active_run = session_payload.get("active_run") or {}
            if active_run.get("state") == "SUBMITTED":
                stats["submitted_runs"] += 1
            worktree["sessions"].append(session_payload)
        worktree["session_count"] = len(worktree["sessions"])
        project["worktrees"].append(worktree)

    projects = list(projects_by_key.values())
    for project in projects:
        project["worktree_count"] = len(project["worktrees"])
    stats["projects"] = len(projects)
    stats["worktrees"] = sum(len(project["worktrees"]) for project in projects)

    return BoardSnapshot(
        payload={
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "projects": projects,
        },
        state_roots=state_roots,
    )


def is_allowed_artifact_path(path: Path, state_roots: list[Path]) -> bool:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False

    for state_root in state_roots:
        try:
            resolved.relative_to(state_root.expanduser().resolve())
            return True
        except ValueError:
            continue
    return False


def _worktree_payload(metadata: WorkspaceMetadata) -> dict[str, Any]:
    return {
        "worktree_path": metadata.worktree_path,
        "branch": metadata.branch,
        "state_root": metadata.state_root,
        "session_count": 0,
        "sessions": [],
    }


def _session_ids(state_root: Path) -> list[str]:
    sessions_dir = state_root / "sessions"
    if sessions_dir.exists():
        return sorted((path.name for path in sessions_dir.iterdir() if path.is_dir()), reverse=True)
    return sorted(
        (
            path.name
            for path in state_root.iterdir()
            if path.is_dir() and (path / "session.json").exists()
        ),
        reverse=True,
    )


def _session_payload(store: StateStore, session_id: str) -> dict[str, Any] | None:
    try:
        session = store.load_session(session_id)
        summary = store.load_workflow_summary(session_id)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return None

    active_run = store.active_stage_run(session_id) or store.latest_stage_run(session_id)
    return {
        "session_id": session.session_id,
        "request": session.request,
        "created_at": session.created_at,
        "current_state": summary.current_state,
        "current_stage": summary.current_stage,
        "human_decision": summary.human_decision,
        "blocked_reason": summary.blocked_reason,
        "workflow_status": _workflow_status(summary.current_state),
        "active_run": _run_payload(active_run),
        "artifact_paths": dict(summary.artifact_paths),
    }


def _workflow_status(current_state: str) -> str:
    if current_state == "Done":
        return "done"
    if current_state == "Blocked":
        return "blocked"
    if current_state in {"WaitForCEOApproval", "WaitForHumanDecision"}:
        return "waiting_human"
    return "in_progress"


def _run_payload(run: StageRunRecord | None) -> dict[str, Any] | None:
    if run is None:
        return None

    gate_result = run.gate_result
    return {
        "run_id": run.run_id,
        "stage": run.stage,
        "state": run.state,
        "gate_status": gate_result.status if isinstance(gate_result, GateResult) else "",
        "gate_reason": gate_result.reason if isinstance(gate_result, GateResult) else "",
        "required_outputs": list(run.required_outputs),
        "required_evidence": list(run.required_evidence),
        "artifact_paths": dict(run.artifact_paths),
    }
