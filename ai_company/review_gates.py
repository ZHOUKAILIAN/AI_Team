from __future__ import annotations

import json
from pathlib import Path

from .models import AcceptanceContract, Finding, SessionRecord, StageOutput


def apply_stage_gates(
    *,
    session: SessionRecord,
    contract: AcceptanceContract | None,
    output: StageOutput,
) -> StageOutput:
    if contract is None or not contract.has_constraints():
        return output

    findings = list(output.findings)
    blocked_reason = output.blocked_reason
    acceptance_status = output.acceptance_status

    if output.stage in {"QA", "Acceptance"} and (
        _requires_host_environment_change(output.artifact_content)
        or any(_requires_host_environment_change(item.issue) for item in findings)
    ):
        if not contract.allow_host_environment_changes:
            findings.append(
                Finding(
                    source_stage=output.stage,
                    target_stage="",
                    issue="Host environment change requires explicit user approval before review can continue.",
                    severity="high",
                    evidence=output.artifact_content.strip(),
                    evidence_kind="host_environment_change",
                    completion_signal=(
                        "Wait for explicit user approval before restarting external tools or mutating local configuration."
                    ),
                )
            )
            acceptance_status = "blocked" if output.stage == "Acceptance" else acceptance_status
            blocked_reason = "Host environment change requires explicit user approval."

    if output.stage == "Acceptance" and contract.review_method:
        review_completion = _load_review_completion(
            session.artifact_dir,
            output.supplemental_artifacts,
        )
        review_findings, review_blocked_reason = _evaluate_review_completion(
            contract=contract,
            review_completion=review_completion,
        )
        if review_findings:
            findings.extend(review_findings)
            acceptance_status = "blocked"
            blocked_reason = review_blocked_reason

    return StageOutput(
        stage=output.stage,
        artifact_name=output.artifact_name,
        artifact_content=output.artifact_content,
        journal=output.journal,
        findings=findings,
        acceptance_status=acceptance_status,
        supplemental_artifacts=dict(output.supplemental_artifacts),
        blocked_reason=blocked_reason,
    )


def _evaluate_review_completion(
    *,
    contract: AcceptanceContract,
    review_completion: dict[str, object] | None,
) -> tuple[list[Finding], str]:
    if review_completion is None:
        return (
            [
                Finding(
                    source_stage="Acceptance",
                    target_stage="",
                    issue="review_completion.json is missing or invalid.",
                    severity="high",
                    evidence_kind="review_completion_gate",
                    completion_signal="Provide a valid review_completion.json before closing the review.",
                )
            ],
            "Review completion gate is incomplete.",
        )

    findings: list[Finding] = []
    produced_artifacts = {str(item) for item in review_completion.get("produced_artifacts", [])}
    dimensions_evaluated = {str(item) for item in review_completion.get("dimensions_evaluated", [])}
    evidence_provided = {str(item) for item in review_completion.get("evidence_provided", [])}
    criteria_covered = {str(item) for item in review_completion.get("criteria_covered", [])}
    unresolved_items = [str(item) for item in review_completion.get("unresolved_items", [])]
    completed = bool(review_completion.get("completed"))

    missing_artifacts = [item for item in contract.required_artifacts if item not in produced_artifacts]
    missing_dimensions = [item for item in contract.required_dimensions if item not in dimensions_evaluated]
    missing_evidence = [item for item in contract.required_evidence if item not in evidence_provided]
    missing_criteria = [item for item in contract.acceptance_criteria if item not in criteria_covered]
    review_started = bool(
        completed
        or produced_artifacts
        or dimensions_evaluated
        or evidence_provided
        or criteria_covered
        or any(item != "Pending review execution." for item in unresolved_items)
    )

    if missing_evidence and review_started:
        findings.append(
            Finding(
                source_stage="Acceptance",
                target_stage="Dev",
                issue="Review is missing required runtime evidence: " + ", ".join(missing_evidence),
                severity="high",
                evidence_kind="review_completion_gate",
                required_evidence=missing_evidence,
                completion_signal=(
                    "Attach "
                    + ", ".join(missing_evidence)
                    + " before claiming the review satisfies the acceptance contract."
                ),
            )
        )

    if not completed or missing_artifacts or missing_dimensions or missing_criteria or unresolved_items:
        issue_parts = []
        if not completed:
            issue_parts.append("review_completion.json still reports completed=false")
        if missing_artifacts:
            issue_parts.append("missing artifacts: " + ", ".join(missing_artifacts))
        if missing_dimensions:
            issue_parts.append("missing dimensions: " + ", ".join(missing_dimensions))
        if missing_criteria:
            issue_parts.append("missing acceptance coverage: " + ", ".join(missing_criteria))
        if unresolved_items:
            issue_parts.append("unresolved items remain")
        findings.append(
            Finding(
                source_stage="Acceptance",
                target_stage="",
                issue="Review completion gate is incomplete: " + "; ".join(issue_parts),
                severity="high",
                evidence_kind="review_completion_gate",
                completion_signal=(
                    "Mark review_completion.json as completed only after every required artifact, dimension, and acceptance criterion is covered."
                ),
            )
        )

    return findings, "Review completion gate is incomplete."


def _load_review_completion(
    artifact_dir: Path,
    supplemental_artifacts: dict[str, str],
) -> dict[str, object] | None:
    raw_content = supplemental_artifacts.get("review_completion.json")
    if raw_content is None:
        path = artifact_dir / "review_completion.json"
        if not path.exists():
            return None
        raw_content = path.read_text()

    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _requires_host_environment_change(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "restart wechat devtools",
            "restart developer tools",
            "modify local config",
            "change local config",
            "host configuration",
            "重启微信开发者工具",
            "修改本机配置",
            "改本机环境",
            "重启开发者工具",
        )
    )
