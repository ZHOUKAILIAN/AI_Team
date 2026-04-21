from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol

from .acceptance_policy import match_visual_evidence_profile
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
    supports_rework_routing: ClassVar[bool] = False
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
        normalized_report = acceptance_report.lower()
        if "blocked" in normalized_report:
            acceptance_status = "blocked"
        elif "no-go" in normalized_report or "recommended_no_go" in normalized_report or "reject" in normalized_report:
            acceptance_status = "recommended_no_go"
        elif findings:
            acceptance_status = "blocked"
        else:
            acceptance_status = "recommended_go"
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
                    "journal": "# Acceptance Journal\n\nRecorded the AI acceptance recommendation for the human decision maker.\n",
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
        stage_findings = [Finding.from_dict(item) for item in payload.get("findings", [])]
        if stage == "Acceptance" and not stage_findings:
            stage_findings = _synthesize_acceptance_findings(
                acceptance_report=str(payload["artifact_content"]),
                acceptance_status=payload.get("acceptance_status"),
                existing_findings=findings,
            )
        return StageOutput(
            stage=stage,
            artifact_name=artifact_name_for_stage(stage),
            artifact_content=str(payload["artifact_content"]),
            journal=str(payload["journal"]),
            findings=stage_findings,
            acceptance_status=payload.get("acceptance_status"),
        )


class DeterministicBackend:
    supports_rework_routing = False

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
            "## Raw Request\n"
            f"{request.strip()}\n\n"
            "## Problem Statement\n"
            f"{request.strip()}\n\n"
            "## Goals\n"
            "- Convert the request into a workflow-ready deliverable.\n"
            "- Make downstream QA and Acceptance checks auditable.\n"
            "- Clarify acceptance before Dev starts.\n\n"
            "## Non-Goals\n"
            "- Final human Go/No-Go decision.\n"
            "- Replacing QA or Acceptance with Dev self-verification.\n\n"
            "## User Scenarios\n"
            "- A stakeholder submits a requirement and expects a structured PRD.\n"
            "- Dev needs explicit acceptance criteria before implementation starts.\n"
            "- QA and Acceptance need traceable expectations for independent verification.\n\n"
            "## Acceptance Criteria\n"
            "- Product writes a PRD with explicit acceptance criteria before Dev starts.\n"
            "- Dev, QA, and Acceptance each write their own session-scoped handoff artifact.\n"
            "- QA independently reruns critical verification and records evidence.\n"
            "- Acceptance outputs an AI recommendation, then waits for a human Go/No-Go decision.\n\n"
            "## QA Verification Focus\n"
            "- Validate that acceptance criteria are measurable.\n"
            "- Confirm Dev exposes enough concrete verification evidence for rerun.\n\n"
            "## Acceptance Verification Focus\n"
            "- Validate user-visible behavior against the PRD.\n"
            "- Block when product-level evidence is missing.\n\n"
            "## Risks And Assumptions\n"
            "- This deterministic backend only demonstrates artifact structure, not real repository verification.\n"
            "- Human approval checkpoints still need to happen outside this demo backend.\n\n"
            "## CEO Confirmation Questions\n"
            "- Are the drafted acceptance criteria complete enough for Dev to start?\n"
            "- Are there any non-goals or constraints that should be added before implementation?\n\n"
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
            "# Implementation\n\n"
            "## Implementation Target\n"
            f"{_excerpt(prd)}\n\n"
            "## Change Summary\n"
            "- Load role context, base memory, and learned overlay memory.\n"
            "- Persist sessions, artifacts, journals, findings, and reviews under the configured runtime state root.\n"
            "- Keep learned context and skill updates as auditable overlays instead of mutating seed files.\n\n"
            "## Changed Files\n"
            "- Demo backend placeholder: no repository files were modified by the deterministic runtime.\n\n"
            "## Self-Verification Evidence\n"
            "- Demo backend placeholder: real Dev runs must attach methodology-specific self-verification evidence here.\n\n"
            "## Commands Executed\n"
            "- Demo backend placeholder: no real commands were executed.\n\n"
            "## Command Result Summary\n"
            "- Deterministic runtime generated structure only; QA must not treat this as independent evidence.\n\n"
            "## Known Limitations\n"
            "- No real code changes or test reruns occurred in this backend.\n\n"
            "## QA Regression Checklist\n"
            "- Re-run the workflow entrypoints and artifact persistence checks in a real session.\n"
            "- Independently verify any repository changes before reporting passed.\n\n"
            "## QA Finding To Fix Mapping\n"
            "- No QA rework mapping in the initial demo pass.\n"
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

        if "QA Regression Checklist" not in tech_spec:
            qa_findings.append(
                Finding(
                    source_stage="QA",
                    target_stage="Dev",
                    issue="Dev implementation handoff is missing a QA regression checklist.",
                    severity="medium",
                    lesson="Include a concrete QA rerun checklist in the implementation handoff.",
                    proposed_context_update="Every implementation handoff must define how QA reruns critical verification.",
                )
            )

        qa_findings.append(
            Finding(
                source_stage="QA",
                target_stage="",
                issue="Deterministic demo runtime did not execute real independent verification commands.",
                severity="high",
                evidence="demo_only_runtime",
                evidence_kind="qa_review",
                required_evidence=["qa_command_rerun"],
                completion_signal="Attach QA-owned rerun evidence showing the critical commands were independently executed.",
            )
        )

        status = "blocked"
        artifact_content = (
            "# QA Report\n\n"
            "## QA Objective For This Round\n"
            "- Confirm the Product and Dev handoff is independently verifiable.\n\n"
            "## Independently Executed Commands\n"
            "- Demo runtime only: reviewed generated PRD and implementation artifact content.\n"
            "- Demo runtime only: no real repository commands were executed.\n\n"
            "## Observed Results\n"
            "- Product artifact includes explicit acceptance criteria only if the generated PRD contains that section.\n"
            "- Dev artifact is acceptable only if it documents a concrete verification strategy.\n\n"
            "## Failures Or Risks\n"
            f"{_format_findings(qa_findings)}\n\n"
            "## PRD Acceptance Criteria Mapping\n"
            "- Artifact contract present: checked via generated session artifacts.\n"
            "- Independent verification evidence present: blocked in demo mode because no real rerun evidence exists.\n\n"
            f"## Decision\n{status}\n\n"
            "## Defects Returned To Dev\n"
            f"{_format_findings(qa_findings)}\n"
        )
        journal = (
            "# QA Journal\n\n"
            "## Verification Notes\n"
            "- Compared PRD and implementation handoff for downstream testability.\n"
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
        acceptance_status = "recommended_go" if not findings else "blocked"
        artifact_content = (
            "# Acceptance Report\n\n"
            "## Acceptance Inputs\n"
            "- PRD artifact from Product.\n"
            "- QA report from the latest QA round.\n"
            "- Demo-only implementation artifact from Dev.\n\n"
            "## Criterion-By-Criterion Judgment\n"
            "- Product supplied acceptance criteria: yes.\n"
            "- QA independently reran critical verification: no, this deterministic backend cannot prove that.\n"
            "- Human Go/No-Go already provided: no.\n\n"
            "## Product-Level Observations\n"
            "- The deterministic runtime demonstrates artifact flow, not user-visible product validation.\n\n"
            "## Remaining Risks\n"
            f"{_format_findings(findings)}\n\n"
            f"## Recommendation\n{acceptance_status}\n\n"
            "## Recommendation To CEO\n"
            f"{'AI Acceptance recommends waiting for the human Go/No-Go decision after real QA evidence is attached.' if acceptance_status == 'recommended_go' else 'AI Acceptance recommends blocking the workflow until unresolved downstream findings are cleared with real evidence.'}\n"
        )
        journal = (
            "# Acceptance Journal\n\n"
            "## Review Summary\n"
            "- Verified that the workflow produced the required artifact set.\n"
            "- Produced an AI recommendation only; the human still owns final Go/No-Go.\n"
        )
        return StageOutput(
            stage="Acceptance",
            artifact_name=artifact_name_for_stage("Acceptance"),
            artifact_content=artifact_content,
            journal=journal,
            findings=_synthesize_acceptance_findings(
                acceptance_report=artifact_content,
                acceptance_status=acceptance_status,
                existing_findings=findings,
            ),
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


def _synthesize_acceptance_findings(
    *,
    acceptance_report: str,
    acceptance_status: str | None,
    existing_findings: list[Finding],
) -> list[Finding]:
    if acceptance_status not in {"recommended_no_go", "blocked"}:
        return []
    if existing_findings:
        return []

    normalized = acceptance_report.strip()
    lowered = normalized.lower()
    if any(
        phrase in lowered
        for phrase in ("credential", "credentials", "environment unavailable", "external system unavailable")
    ):
        return []

    target_stage = "Product" if any(
        phrase in lowered
        for phrase in ("acceptance criteria", "scope", "requirement", "prd", "user scenario", "business intent")
    ) else "Dev"
    profile = match_visual_evidence_profile(normalized)
    required_evidence = list(profile.get("required_evidence", [])) if profile else []
    completion_signal = str(profile.get("completion_signal", "")) if profile else ""

    context_update = (
        "Clarify acceptance criteria and user scenarios before implementation begins."
        if target_stage == "Product"
        else "Review user-visible behavior against the PRD before closing implementation."
    )
    skill_update = (
        "Produce measurable acceptance criteria and scenario coverage before handoff."
        if target_stage == "Product"
        else "Require product-level evidence for the user-visible behavior before reporting completion."
    )
    lesson = (
        "Make acceptance expectations explicit before implementation starts."
        if target_stage == "Product"
        else "Preserve product-visible outcomes until acceptance evidence is complete."
    )

    return [
        Finding(
            source_stage="Acceptance",
            target_stage=target_stage,
            issue=_acceptance_issue_summary(normalized),
            severity="high",
            lesson=lesson,
            proposed_context_update=context_update,
            proposed_skill_update=skill_update,
            evidence=normalized,
            evidence_kind="acceptance_report",
            required_evidence=required_evidence,
            completion_signal=completion_signal,
        )
    ]


def _acceptance_issue_summary(report: str) -> str:
    lowered = report.lower()
    if "because" in lowered:
        _, suffix = report.split("because", 1)
        return suffix.strip().rstrip(".")

    lines = [line.strip() for line in report.splitlines() if line.strip()]
    return lines[0] if lines else "Acceptance reported an actionable product-level issue."
