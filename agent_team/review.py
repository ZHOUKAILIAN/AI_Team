from __future__ import annotations

from difflib import unified_diff

from .models import Finding, WorkflowSummary


def build_session_review(
    *,
    stage_artifacts: dict[str, str],
    findings: list[Finding | dict[str, str]],
    acceptance_status: str = "pending",
    workflow_summary: WorkflowSummary | None = None,
) -> str:
    normalized_findings = [_normalize_finding(item) for item in findings]
    lines = [
        "# Session Review",
        "",
        f"acceptance_status: {acceptance_status}",
        "",
    ]
    if workflow_summary is not None:
        lines.extend(_build_workflow_status_section(workflow_summary))

    lines.extend(["## Findings", ""])

    if normalized_findings:
        for finding in normalized_findings:
            lines.append(
                f"- [{finding.severity}] {finding.source_stage} -> {finding.target_stage}: {finding.issue}"
            )
            if finding.lesson:
                lines.append(f"lesson: {finding.lesson}")
            if finding.evidence_kind:
                lines.append(f"evidence_kind: {finding.evidence_kind}")
            if finding.required_evidence:
                lines.append(f"required_evidence: {', '.join(finding.required_evidence)}")
            if finding.completion_signal:
                lines.append(f"completion_signal: {finding.completion_signal}")
            if finding.proposed_context_update:
                lines.append(f"proposed_context_update: {finding.proposed_context_update}")
            if finding.proposed_skill_update:
                lines.append(f"proposed_skill_update: {finding.proposed_skill_update}")
            lines.append("")
    else:
        lines.append("- No downstream findings recorded.")
        lines.append("")

    lines.extend(["## Artifact Diffs", ""])
    lines.extend(_build_diff_sections(stage_artifacts))
    return "\n".join(lines).rstrip() + "\n"


def _build_diff_sections(stage_artifacts: dict[str, str]) -> list[str]:
    stages = list(stage_artifacts.keys())
    if len(stages) < 2:
        return ["No artifact diffs available yet.", ""]

    lines: list[str] = []
    for left_stage, right_stage in zip(stages, stages[1:]):
        diff_lines = list(
            unified_diff(
                stage_artifacts[left_stage].splitlines(),
                stage_artifacts[right_stage].splitlines(),
                fromfile=left_stage,
                tofile=right_stage,
                lineterm="",
            )
        )
        if not diff_lines:
            diff_lines = [f"--- {left_stage}", f"+++ {right_stage}", "(no textual diff)"]

        lines.append(f"### {left_stage} -> {right_stage}")
        lines.append("```diff")
        lines.extend(diff_lines)
        lines.append("```")
        lines.append("")
    return lines


def _normalize_finding(item: Finding | dict[str, str]) -> Finding:
    if isinstance(item, Finding):
        return item
    return Finding.from_dict(item)


def _build_workflow_status_section(workflow_summary: WorkflowSummary) -> list[str]:
    return [
        "## Workflow Status",
        "",
        f"runtime_mode: {workflow_summary.runtime_mode}",
        f"current_state: {workflow_summary.current_state}",
        f"current_stage: {workflow_summary.current_stage}",
        f"prd_status: {workflow_summary.prd_status}",
        f"dev_status: {workflow_summary.dev_status}",
        f"qa_status: {workflow_summary.qa_status}",
        f"acceptance_status: {workflow_summary.acceptance_status}",
        f"human_decision: {workflow_summary.human_decision}",
        f"qa_round: {workflow_summary.qa_round}",
        "",
    ]
