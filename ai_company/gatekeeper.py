from __future__ import annotations

from datetime import datetime, timezone

from .models import AcceptanceContract, EvidenceItem, GateResult, SessionRecord, StageContract, StageOutput, StageResultEnvelope
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
    missing_outputs = _missing_outputs(contract=contract, result=normalized)
    missing_evidence = _missing_evidence(contract=contract, evidence=list(normalized.evidence))

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
        supplemental_artifacts=dict(gated.supplemental_artifacts),
    )


def _missing_outputs(*, contract: StageContract, result: StageResultEnvelope) -> list[str]:
    if result.artifact_name in contract.required_outputs and result.artifact_content.strip():
        return []
    return list(contract.required_outputs)


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
