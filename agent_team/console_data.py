from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .board import build_board_snapshot, build_board_snapshot_with_roots
from .panel import build_panel_snapshot
from .state import StateStore


def build_console_snapshot(*, codex_home: Path | None = None) -> dict[str, Any]:
    board = build_board_snapshot(codex_home=codex_home)
    projects = [_normalize_project(project, board["generated_at"]) for project in board.get("projects", [])]
    return {
        "generated_at": board["generated_at"],
        "stats": _console_stats(projects),
        "projects": projects,
    }


def build_project_detail(project_id: str, *, codex_home: Path | None = None) -> dict[str, Any]:
    snapshot = build_console_snapshot(codex_home=codex_home)
    project = _find_project(snapshot["projects"], project_id)
    return {
        "generated_at": snapshot["generated_at"],
        "project": project,
    }


def build_project_sessions(project_id: str, *, codex_home: Path | None = None) -> dict[str, Any]:
    detail = build_project_detail(project_id, codex_home=codex_home)
    project = detail["project"]
    return {
        "generated_at": detail["generated_at"],
        "project_id": project["project_id"],
        "sessions": project["sessions"],
    }


def build_session_detail(
    session_id: str,
    *,
    state_root: Path | None = None,
    repo_root: Path | None = None,
    codex_home: Path | None = None,
) -> dict[str, Any]:
    resolved_state_root = state_root or _state_root_for_session(session_id, codex_home=codex_home)
    store = StateStore(resolved_state_root)
    snapshot = build_panel_snapshot(store, session_id, repo_root=repo_root)
    return {
        "generated_at": snapshot["overview"].get("generated_at", ""),
        "session_id": session_id,
        "snapshot": snapshot,
    }


def _normalize_project(project: dict[str, Any], generated_at: str) -> dict[str, Any]:
    sessions = []
    worktrees = []
    for worktree in project.get("worktrees", []):
        worktree_sessions = [
            _normalize_session(project, worktree, session, generated_at)
            for session in worktree.get("sessions", [])
        ]
        sessions.extend(worktree_sessions)
        worktrees.append(
            {
                "worktree_path": worktree.get("worktree_path", ""),
                "branch": worktree.get("branch", ""),
                "state_root": worktree.get("state_root", ""),
                "session_count": len(worktree_sessions),
                "active_count": sum(1 for session in worktree_sessions if session["workflow_status"] == "in_progress"),
                "waiting_human_count": sum(
                    1 for session in worktree_sessions if session["workflow_status"] == "waiting_human"
                ),
                "blocked_count": sum(1 for session in worktree_sessions if session["workflow_status"] == "blocked"),
            }
        )

    project_id = _project_id(project.get("project_name", ""), project.get("project_root", ""))
    return {
        "project_id": project_id,
        "project_name": project.get("project_name", ""),
        "project_root": project.get("project_root", ""),
        "worktree_count": len(worktrees),
        "session_count": len(sessions),
        "active_count": sum(1 for session in sessions if session["workflow_status"] == "in_progress"),
        "waiting_human_count": sum(1 for session in sessions if session["workflow_status"] == "waiting_human"),
        "blocked_count": sum(1 for session in sessions if session["workflow_status"] == "blocked"),
        "updated_at": generated_at,
        "worktrees": worktrees,
        "sessions": sessions,
    }


def _normalize_session(
    project: dict[str, Any],
    worktree: dict[str, Any],
    session: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    return {
        "session_id": session.get("session_id", ""),
        "project_id": _project_id(project.get("project_name", ""), project.get("project_root", "")),
        "project_name": project.get("project_name", ""),
        "project_root": project.get("project_root", ""),
        "worktree_path": worktree.get("worktree_path", ""),
        "branch": worktree.get("branch", ""),
        "state_root": worktree.get("state_root", ""),
        "request": session.get("request", ""),
        "current_state": session.get("current_state", ""),
        "current_stage": session.get("current_stage", ""),
        "workflow_status": session.get("workflow_status", ""),
        "blocked_reason": session.get("blocked_reason", ""),
        "active_run": session.get("active_run"),
        "artifact_paths": session.get("artifact_paths", {}),
        "created_at": session.get("created_at", ""),
        "updated_at": generated_at,
    }


def _console_stats(projects: list[dict[str, Any]]) -> dict[str, int]:
    sessions = [session for project in projects for session in project["sessions"]]
    return {
        "projects": len(projects),
        "worktrees": sum(project["worktree_count"] for project in projects),
        "sessions": len(sessions),
        "active": sum(1 for session in sessions if session["workflow_status"] == "in_progress"),
        "waiting_human": sum(1 for session in sessions if session["workflow_status"] == "waiting_human"),
        "blocked": sum(1 for session in sessions if session["workflow_status"] == "blocked"),
    }


def _find_project(projects: list[dict[str, Any]], project_id: str) -> dict[str, Any]:
    for project in projects:
        if project["project_id"] == project_id:
            return project
    raise FileNotFoundError(f"Project not found: {project_id}")


def _state_root_for_session(session_id: str, *, codex_home: Path | None) -> Path:
    snapshot = build_board_snapshot_with_roots(codex_home=codex_home)
    for project in snapshot.payload.get("projects", []):
        for worktree in project.get("worktrees", []):
            for session in worktree.get("sessions", []):
                if session.get("session_id") == session_id:
                    return Path(worktree["state_root"])
    raise FileNotFoundError(f"Session not found: {session_id}")


def _project_id(project_name: str, project_root: str) -> str:
    source = project_root or project_name
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", project_name.strip().lower()).strip("-")
    if not slug:
        slug = "project"
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"
