from __future__ import annotations

from difflib import unified_diff

from .models import Finding


def build_session_review(
    *,
    stage_artifacts: dict[str, str],
    findings: list[Finding | dict[str, str]],
    acceptance_status: str = "pending",
) -> str:
    normalized_findings = [_normalize_finding(item) for item in findings]
    lines = [
        "# Session Review",
        "",
        f"acceptance_status: {acceptance_status}",
        "",
        "## Findings",
        "",
    ]

    if normalized_findings:
        for finding in normalized_findings:
            lines.append(
                f"- [{finding.severity}] {finding.source_stage} -> {finding.target_stage}: {finding.issue}"
            )
            if finding.lesson:
                lines.append(f"lesson: {finding.lesson}")
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
