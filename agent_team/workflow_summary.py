from __future__ import annotations

from .models import WorkflowSummary


def render_workflow_summary(summary: WorkflowSummary) -> str:
    lines = [
        "# Workflow Summary",
        "",
        f"- session_id: {summary.session_id}",
        f"- runtime_mode: {summary.runtime_mode}",
        f"- current_state: {summary.current_state}",
        f"- current_stage: {summary.current_stage}",
        f"- prd_status: {summary.prd_status}",
        f"- dev_status: {summary.dev_status}",
        f"- qa_status: {summary.qa_status}",
        f"- acceptance_status: {summary.acceptance_status}",
        f"- human_decision: {summary.human_decision}",
        f"- qa_round: {summary.qa_round}",
        f"- blocked_reason: {summary.blocked_reason}",
        "",
        "## Artifact Paths",
    ]
    for key in sorted(summary.artifact_paths):
        lines.append(f"- {key}: {summary.artifact_paths[key]}")
    lines.append("")
    return "\n".join(lines)
