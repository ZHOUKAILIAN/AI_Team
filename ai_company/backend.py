from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import Finding, RoleProfile, StageOutput
from .state import artifact_name_for_stage


class WorkflowBackend(Protocol):
    def run_stage(
        self,
        *,
        stage: str,
        request: str,
        role: RoleProfile,
        stage_artifacts: dict[str, str],
        findings: list[Finding],
    ) -> StageOutput: ...


@dataclass
class StaticBackend:
    stage_payloads: dict[str, dict[str, object]]

    @classmethod
    def fixture(
        cls,
        *,
        product_requirements: str,
        prd: str,
        tech_spec: str,
        qa_report: str,
        acceptance_report: str,
        findings: list[dict[str, str]],
    ) -> "StaticBackend":
        acceptance_status = "rejected" if "reject" in acceptance_report.lower() or findings else "accepted"
        return cls(
            stage_payloads={
                "Product": {
                    "artifact_content": prd,
                    "journal": (
                        "# Product Journal\n\n"
                        "## Raw Request\n"
                        f"{product_requirements}\n\n"
                        "## Output\n"
                        "Captured the request as a PRD artifact.\n"
                    ),
                },
                "Dev": {
                    "artifact_content": tech_spec,
                    "journal": "# Dev Journal\n\nTranslated the PRD into a technical plan.\n",
                },
                "QA": {
                    "artifact_content": qa_report,
                    "journal": "# QA Journal\n\nExecuted downstream checks and emitted findings.\n",
                    "findings": findings,
                },
                "Acceptance": {
                    "artifact_content": acceptance_report,
                    "journal": "# Acceptance Journal\n\nRecorded the final sign-off decision.\n",
                    "acceptance_status": acceptance_status,
                },
            }
        )

    def run_stage(
        self,
        *,
        stage: str,
        request: str,
        role: RoleProfile,
        stage_artifacts: dict[str, str],
        findings: list[Finding],
    ) -> StageOutput:
        payload = self.stage_payloads[stage]
        return StageOutput(
            stage=stage,
            artifact_name=artifact_name_for_stage(stage),
            artifact_content=str(payload["artifact_content"]),
            journal=str(payload["journal"]),
            findings=[Finding.from_dict(item) for item in payload.get("findings", [])],
            acceptance_status=payload.get("acceptance_status"),
        )


class DeterministicBackend:
    def run_stage(
        self,
        *,
        stage: str,
        request: str,
        role: RoleProfile,
        stage_artifacts: dict[str, str],
        findings: list[Finding],
    ) -> StageOutput:
        method_name = f"_run_{stage.lower()}"
        handler = getattr(self, method_name)
        return handler(request=request, role=role, stage_artifacts=stage_artifacts, findings=findings)

    def _run_product(
        self,
        *,
        request: str,
        role: RoleProfile,
        stage_artifacts: dict[str, str],
        findings: list[Finding],
    ) -> StageOutput:
        guardrails = _memory_highlights(role)
        artifact_content = (
            "# Product PRD\n\n"
            "## Problem Statement\n"
            f"{request.strip()}\n\n"
            "## Goals\n"
            "- Convert the request into a workflow-ready deliverable.\n"
            "- Make downstream QA and Acceptance checks auditable.\n\n"
            "## Scope\n"
            "- Product stage produces an explicit PRD.\n"
            "- Dev stage produces a technical plan.\n"
            "- QA and Acceptance can send issues upstream.\n\n"
            "## Acceptance Criteria\n"
            "- Every stage writes an artifact and a journal.\n"
            "- Downstream findings update learned memory overlays.\n"
            "- Final review includes diffs and proposed improvements.\n\n"
            "## Learned Guardrails\n"
            f"{guardrails}\n"
        )
        journal = (
            "# Product Journal\n\n"
            "## Effective Context Snapshot\n"
            f"{_excerpt(role.effective_context_text)}\n\n"
            "## Decisions\n"
            "- Added explicit acceptance criteria for downstream review.\n"
            "- Preserved a learned-guardrail section so QA can trace expectations.\n"
        )
        return StageOutput(
            stage="Product",
            artifact_name=artifact_name_for_stage("Product"),
            artifact_content=artifact_content,
            journal=journal,
        )

    def _run_dev(
        self,
        *,
        request: str,
        role: RoleProfile,
        stage_artifacts: dict[str, str],
        findings: list[Finding],
    ) -> StageOutput:
        prd = stage_artifacts.get("Product", "")
        artifact_content = (
            "# Dev Technical Plan\n\n"
            "## Source PRD\n"
            f"{_excerpt(prd)}\n\n"
            "## Architecture\n"
            "- Load role context, base memory, and learned overlay memory.\n"
            "- Persist sessions, artifacts, journals, findings, and reviews under `.ai_company_state/`.\n"
            "- Keep learned context and skill updates as auditable overlays instead of mutating seed files.\n\n"
            "## Test Strategy\n"
            "- Verify CLI entrypoints.\n"
            "- Verify session creation and artifact persistence.\n"
            "- Verify downstream findings update the target role learning records.\n"
        )
        journal = (
            "# Dev Journal\n\n"
            "## Effective Memory Snapshot\n"
            f"{_excerpt(role.effective_memory_text)}\n\n"
            "## Decisions\n"
            "- Chose append-only learning records for traceability.\n"
            "- Kept context and skill evolution as overlays to avoid destructive prompt drift.\n"
        )
        return StageOutput(
            stage="Dev",
            artifact_name=artifact_name_for_stage("Dev"),
            artifact_content=artifact_content,
            journal=journal,
        )

    def _run_qa(
        self,
        *,
        request: str,
        role: RoleProfile,
        stage_artifacts: dict[str, str],
        findings: list[Finding],
    ) -> StageOutput:
        prd = stage_artifacts.get("Product", "")
        tech_spec = stage_artifacts.get("Dev", "")
        qa_findings: list[Finding] = []

        if "Acceptance Criteria" not in prd:
            qa_findings.append(
                Finding(
                    source_stage="QA",
                    target_stage="Product",
                    issue="Product PRD is missing acceptance criteria.",
                    severity="high",
                    lesson="Always define acceptance criteria before handoff.",
                    proposed_context_update="Product outputs must include measurable acceptance criteria.",
                )
            )

        if "Test Strategy" not in tech_spec:
            qa_findings.append(
                Finding(
                    source_stage="QA",
                    target_stage="Dev",
                    issue="Dev technical plan is missing a test strategy.",
                    severity="medium",
                    lesson="Include a concrete test strategy in the technical plan.",
                    proposed_context_update="Every technical plan must define how QA verifies it.",
                )
            )

        status = "passed" if not qa_findings else "rejected"
        artifact_content = (
            "# QA Report\n\n"
            f"status: {status}\n\n"
            "## Checks\n"
            "- Product artifact includes explicit acceptance criteria.\n"
            "- Dev artifact includes a test strategy and persistence plan.\n\n"
            "## Findings\n"
            f"{_format_findings(qa_findings)}\n"
        )
        journal = (
            "# QA Journal\n\n"
            "## Verification Notes\n"
            "- Compared PRD and technical plan for downstream testability.\n"
            "- Emitted structured findings only when a handoff gap was visible.\n"
        )
        return StageOutput(
            stage="QA",
            artifact_name=artifact_name_for_stage("QA"),
            artifact_content=artifact_content,
            journal=journal,
            findings=qa_findings,
        )

    def _run_acceptance(
        self,
        *,
        request: str,
        role: RoleProfile,
        stage_artifacts: dict[str, str],
        findings: list[Finding],
    ) -> StageOutput:
        acceptance_status = "accepted" if not findings else "rejected"
        artifact_content = (
            "# Acceptance Report\n\n"
            f"acceptance_status: {acceptance_status}\n\n"
            "## Decision\n"
            f"{'The workflow passed the acceptance gate.' if acceptance_status == 'accepted' else 'The workflow is blocked by open downstream findings.'}\n\n"
            "## Open Findings\n"
            f"{_format_findings(findings)}\n"
        )
        journal = (
            "# Acceptance Journal\n\n"
            "## Review Summary\n"
            "- Verified that the workflow produced all required artifacts.\n"
            "- Used downstream findings as the release gate.\n"
        )
        return StageOutput(
            stage="Acceptance",
            artifact_name=artifact_name_for_stage("Acceptance"),
            artifact_content=artifact_content,
            journal=journal,
            acceptance_status=acceptance_status,
        )


def _excerpt(text: str, limit: int = 500) -> str:
    normalized = text.strip()
    if not normalized:
        return "(empty)"
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _memory_highlights(role: RoleProfile) -> str:
    learned = role.learned_memory_text.strip()
    if learned:
        return learned
    return "- No learned guardrails yet."


def _format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "- No downstream findings."

    lines = []
    for finding in findings:
        lines.append(
            f"- [{finding.severity}] {finding.source_stage} -> {finding.target_stage}: "
            f"{finding.issue}"
        )
    return "\n".join(lines)
