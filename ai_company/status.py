from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import WorkflowSummary


def build_status_overview(
    *,
    summary: WorkflowSummary,
    state_root: Path,
    repo_root: Path | None = None,
) -> dict[str, str]:
    project = _project_name(state_root=state_root, repo_root=repo_root)
    role = summary.current_stage or summary.current_state or "Unknown"
    status = _status(summary)
    detail = _status_detail(summary)
    return {
        "project": project,
        "role": role,
        "status": status,
        "detail": detail,
        "text": f"{project} / {role} / {status}: {detail}",
    }


def render_status_markdown(
    *,
    summary: WorkflowSummary,
    state_root: Path,
    events: list[dict[str, object]],
    repo_root: Path | None = None,
) -> str:
    overview = build_status_overview(summary=summary, state_root=state_root, repo_root=repo_root)
    lines = [
        "# AI_Team Status",
        "",
        f"- project: {overview['project']}",
        f"- role: {overview['role']}",
        f"- status: {overview['status']}",
        f"- detail: {overview['detail']}",
        f"- session_id: {summary.session_id}",
        f"- current_state: {summary.current_state}",
        f"- acceptance_status: {summary.acceptance_status}",
        f"- human_decision: {summary.human_decision}",
        "",
        "## Replay",
        "",
        "- workflow_summary: workflow_summary.md",
        "- events: events.jsonl",
        "",
        "## Recent Events",
        "",
    ]
    if events:
        for event in events[-10:]:
            lines.append(f"- {event.get('at', '')} {event.get('kind', '')}: {event.get('message', '')}")
    else:
        lines.append("- No events recorded yet.")
    lines.append("")
    return "\n".join(lines)


def _project_name(*, state_root: Path, repo_root: Path | None) -> str:
    if repo_root is not None:
        return repo_root.resolve().name
    if state_root.name == ".ai-team":
        return state_root.parent.name
    return state_root.name


def _status(summary: WorkflowSummary) -> str:
    if summary.blocked_reason or summary.acceptance_status == "blocked" or summary.qa_status == "blocked":
        return "blocked"
    if summary.current_state in {"WaitForCEOApproval", "WaitForHumanDecision"}:
        return "waiting"
    if summary.current_state == "Done":
        return "done"
    if summary.acceptance_status in {"recommended_go", "recommended_no_go"}:
        return summary.acceptance_status
    return "in_progress"


def _status_detail(summary: WorkflowSummary) -> str:
    if summary.blocked_reason:
        return summary.blocked_reason
    if summary.current_state == "WaitForCEOApproval":
        return "Waiting for CEO approval."
    if summary.current_state == "WaitForHumanDecision":
        return "Waiting for human Go/No-Go decision."
    if summary.acceptance_status in {"recommended_go", "recommended_no_go"}:
        return f"Acceptance reported {summary.acceptance_status}."
    return f"{summary.current_stage} is active in {summary.current_state}."
