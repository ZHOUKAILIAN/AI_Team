from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .models import AcceptanceContract, EvidenceItem, Finding, GateResult, SessionRecord, StageContract, StageOutput, StageResultEnvelope
from .review_gates import apply_stage_gates


class Gatekeeper:
    def evaluate(
        self,
        *,
        session: SessionRecord,
        contract: StageContract,
        result: StageResultEnvelope,
        acceptance_contract: AcceptanceContract | None,
    ) -> GateResult:
        gate_result, _ = evaluate_candidate(
            session=session,
            contract=contract,
            result=result,
            acceptance_contract=acceptance_contract,
        )
        return gate_result


def evaluate_candidate(
    *,
    session: SessionRecord,
    contract: StageContract,
    result: StageResultEnvelope,
    acceptance_contract: AcceptanceContract | None,
) -> tuple[GateResult, StageResultEnvelope]:
    normalized = normalize_stage_result(
        session=session,
        result=result,
        acceptance_contract=acceptance_contract,
    )
    checked_at = datetime.now(timezone.utc).isoformat()

    structural_issues: list[str] = []
    evidence_items = list(normalized.evidence)
    missing_outputs = _missing_outputs(contract=contract, result=normalized)
    missing_evidence = _missing_evidence(contract=contract, evidence=evidence_items)
    evidence_diagnostics = _evidence_name_diagnostics(
        evidence=evidence_items,
        missing_evidence=missing_evidence,
    )
    audit_findings = _stage_audit_findings(contract=contract, result=normalized, evidence=evidence_items)
    if audit_findings:
        normalized.findings.extend(audit_findings)

    if contract.session_id != normalized.session_id:
        structural_issues.append("stage result session_id does not match contract")
    if contract.stage != normalized.stage:
        structural_issues.append("stage result stage does not match contract")
    if contract.contract_id != normalized.contract_id:
        structural_issues.append("stage result contract_id does not match contract")

    if normalized.status.strip().lower() == "blocked":
        return (
            GateResult(
                status="BLOCKED",
                reason=normalized.blocked_reason or normalized.summary or "Worker reported the stage as blocked.",
                missing_outputs=missing_outputs,
                missing_evidence=missing_evidence,
                findings=list(normalized.findings),
                checked_at=checked_at,
            ),
            normalized,
        )

    if normalized.blocked_reason:
        return (
            GateResult(
                status="BLOCKED",
                reason=normalized.blocked_reason,
                missing_outputs=missing_outputs,
                missing_evidence=missing_evidence,
                findings=list(normalized.findings),
                checked_at=checked_at,
            ),
            normalized,
        )

    if structural_issues or missing_outputs or missing_evidence:
        issue_parts = structural_issues[:]
        if missing_outputs:
            issue_parts.append("missing outputs: " + ", ".join(missing_outputs))
        if missing_evidence:
            issue_parts.append("missing evidence: " + ", ".join(missing_evidence))
        issue_parts.extend(evidence_diagnostics)
        return (
            GateResult(
                status="FAILED",
                reason="; ".join(issue_parts),
                missing_outputs=missing_outputs,
                missing_evidence=missing_evidence,
                findings=list(normalized.findings),
                checked_at=checked_at,
            ),
            normalized,
        )

    return (
        GateResult(
            status="PASSED",
            reason="All contract and evidence gates satisfied.",
            findings=list(normalized.findings),
            checked_at=checked_at,
        ),
        normalized,
    )


def normalize_stage_result(
    *,
    session: SessionRecord,
    result: StageResultEnvelope,
    acceptance_contract: AcceptanceContract | None,
) -> StageResultEnvelope:
    gated = apply_stage_gates(
        session=session,
        contract=acceptance_contract,
        output=StageOutput(
            stage=result.stage,
            artifact_name=result.artifact_name,
            artifact_content=result.artifact_content,
            journal=result.journal,
            findings=list(result.findings),
            acceptance_status=result.acceptance_status or None,
            supplemental_artifacts=dict(result.supplemental_artifacts),
            blocked_reason=result.blocked_reason,
        ),
    )
    return StageResultEnvelope(
        session_id=result.session_id,
        stage=result.stage,
        status=result.status,
        artifact_name=result.artifact_name,
        artifact_content=result.artifact_content,
        contract_id=result.contract_id,
        journal=result.journal,
        findings=list(gated.findings),
        evidence=list(result.evidence),
        suggested_next_owner=result.suggested_next_owner,
        summary=result.summary,
        acceptance_status=gated.acceptance_status or "",
        blocked_reason=gated.blocked_reason,
        verification_conclusion=result.verification_conclusion,
        release_recommendation=result.release_recommendation,
        gate_decision=result.gate_decision,
        supplemental_artifacts=dict(gated.supplemental_artifacts),
    )


def _stage_audit_findings(
    *,
    contract: StageContract,
    result: StageResultEnvelope,
    evidence: list[EvidenceItem],
) -> list[Finding]:
    if contract.stage != "GovernanceReview":
        return []
    if not _contract_requires_service_health_audit(contract):
        return []
    return _service_health_governance_findings(result=result, evidence=evidence)


def _contract_requires_service_health_audit(contract: StageContract) -> bool:
    evidence_names = set(contract.evidence_requirements) | {spec.name for spec in contract.evidence_specs}
    return "service_health_evidence_audit" in evidence_names


def _service_health_governance_findings(*, result: StageResultEnvelope, evidence: list[EvidenceItem]) -> list[Finding]:
    text = _combined_result_text(result, evidence).lower()
    findings: list[Finding] = []

    required_tokens = {
        "service_health_contract": "service health contract evidence",
        "service_health_in_process": "service health in-process evidence",
        "service_health_capability": "service health runtime capability evidence",
    }
    missing = [label for token, label in required_tokens.items() if token not in text]
    if missing:
        findings.append(
            Finding(
                source_stage="GovernanceReview",
                target_stage="Verification",
                issue="GovernanceReview did not audit required service_health evidence keys: " + ", ".join(missing),
                severity="high",
                evidence_kind="service_health_evidence_audit",
                required_evidence=list(required_tokens),
                completion_signal="Audit service_health_contract, service_health_in_process, and service_health_capability evidence before governance can pass.",
            )
        )

    has_real_http_gap = "real_http_evidence_pending" in text or "loopback" in text and "pending" in text
    has_capability_reason = any(
        phrase in text
        for phrase in (
            "eperm",
            "operation not permitted",
            "capability",
            "environment does not allow",
            "环境不允许",
            "禁止监听",
        )
    )
    if has_real_http_gap and not has_capability_reason:
        findings.append(
            Finding(
                source_stage="GovernanceReview",
                target_stage="Verification",
                issue="real_http_evidence_pending is recorded without an auditable runtime capability reason.",
                severity="high",
                evidence_kind="service_health_evidence_audit",
                required_evidence=["service_health_capability"],
                completion_signal="Record why real loopback HTTP evidence is unavailable, including the observed capability failure.",
            )
        )

    if "real_http_evidence_pending" in text and "passed" in text and "gap" not in text and "caution" not in text and "condition" not in text:
        findings.append(
            Finding(
                source_stage="GovernanceReview",
                target_stage="Verification",
                issue="real_http_evidence_pending must be treated as a coverage gap or condition, not silently accepted as complete.",
                severity="high",
                evidence_kind="service_health_evidence_audit",
                required_evidence=["service_health_capability"],
                completion_signal="Mark missing real HTTP evidence as a gap/condition or provide real loopback HTTP evidence.",
            )
        )

    return findings


def _combined_result_text(result: StageResultEnvelope, evidence: list[EvidenceItem]) -> str:
    parts = [
        result.artifact_name,
        result.artifact_content,
        result.journal,
        result.summary,
        result.blocked_reason,
    ]
    parts.extend(str(value) for value in result.supplemental_artifacts.values())
    for item in evidence:
        parts.extend(
            [
                item.name,
                item.kind,
                item.summary,
                item.artifact_path,
                item.command,
                str(item.metadata),
            ]
        )
    return "\n".join(part for part in parts if part)


def _missing_outputs(*, contract: StageContract, result: StageResultEnvelope) -> list[str]:
    present: set[str] = set()
    if result.artifact_name and result.artifact_content.strip():
        present.add(Path(result.artifact_name).name)
    for artifact_name, artifact_content in result.supplemental_artifacts.items():
        if str(artifact_content).strip():
            present.add(Path(artifact_name).name)
    return [name for name in contract.required_outputs if Path(name).name not in present]


def _missing_evidence(*, contract: StageContract, evidence: list[EvidenceItem]) -> list[str]:
    missing: list[str] = []
    evidence_by_name: dict[str, list[EvidenceItem]] = {}
    for item in evidence:
        evidence_by_name.setdefault(item.name, []).append(item)

    specs_by_name = {spec.name: spec for spec in contract.evidence_specs}
    for required_name in contract.evidence_requirements:
        items = evidence_by_name.get(required_name, [])
        spec = specs_by_name.get(required_name)
        minimum_items = spec.minimum_items if spec is not None else 1
        if len(items) < minimum_items:
            missing.append(required_name)
            continue
        if spec is None:
            continue

        for item in items:
            if spec.allowed_kinds and item.kind not in spec.allowed_kinds:
                missing.append(f"{required_name}.kind")
            for field_name in spec.required_fields:
                if not item.has_field(field_name):
                    missing.append(f"{required_name}.{field_name}")

    return sorted(set(missing))


def _evidence_name_diagnostics(
    *,
    evidence: list[EvidenceItem],
    missing_evidence: list[str],
) -> list[str]:
    evidence_names = sorted({item.name for item in evidence if item.name})
    diagnostics: list[str] = []
    for missing in missing_evidence:
        if "." in missing:
            continue
        near_matches = [name for name in evidence_names if name.startswith(f"{missing}_")]
        if not near_matches:
            continue
        diagnostics.append(
            "protocol violation: required evidence key "
            f"'{missing}' is missing; found derived key(s): "
            + ", ".join(near_matches)
            + "; use the exact required key and move sub-check details into metadata."
        )
    return diagnostics
