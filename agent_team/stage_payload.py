from __future__ import annotations

from typing import Any

from .models import StageResultEnvelope


FORBIDDEN_STAGE_PAYLOAD_FIELDS = frozenset(
    {
        "session_id",
        "stage",
        "contract_id",
        "artifact_name",
        "current_state",
        "current_stage",
    }
)

ALLOWED_STAGE_PAYLOAD_FIELDS = frozenset(
    {
        "status",
        "artifact_content",
        "journal",
        "findings",
        "evidence",
        "evidence_by_name",
        "suggested_next_owner",
        "summary",
        "acceptance_status",
        "blocked_reason",
        "route_required_stages",
        "route_stage_decisions",
        "verification_mode",
        "product_definition_outcome",
        "service_profile",
        "verification_profile",
        "flow_ids",
        "evidence_paths",
    }
)


def envelope_from_stage_payload(
    *,
    payload: dict[str, Any],
    session_id: str,
    stage: str,
    contract_id: str,
    artifact_name: str,
) -> StageResultEnvelope:
    forbidden = sorted(FORBIDDEN_STAGE_PAYLOAD_FIELDS.intersection(payload))
    if forbidden:
        raise ValueError(
            "stage payload must not include runtime-controlled field(s): "
            + ", ".join(forbidden)
        )

    unexpected = sorted(set(payload).difference(ALLOWED_STAGE_PAYLOAD_FIELDS))
    if unexpected:
        raise ValueError(
            "stage payload includes unsupported field(s): "
            + ", ".join(unexpected)
        )

    envelope_payload = {
        "session_id": session_id,
        "stage": stage,
        "status": payload.get("status") or default_stage_payload_status(stage, payload),
        "artifact_name": artifact_name,
        "artifact_content": payload.get("artifact_content", ""),
        "contract_id": contract_id,
        "journal": payload.get("journal", ""),
        "findings": payload.get("findings", []),
        "evidence": payload.get("evidence", []),
        "evidence_by_name": payload.get("evidence_by_name", {}),
        "suggested_next_owner": payload.get("suggested_next_owner", ""),
        "summary": payload.get("summary", ""),
        "acceptance_status": payload.get("acceptance_status", ""),
        "blocked_reason": payload.get("blocked_reason", ""),
        "route_required_stages": payload.get("route_required_stages", []),
        "route_stage_decisions": payload.get("route_stage_decisions", {}),
        "verification_mode": payload.get("verification_mode", ""),
        "product_definition_outcome": payload.get("product_definition_outcome", ""),
        "service_profile": payload.get("service_profile", ""),
        "verification_profile": payload.get("verification_profile", ""),
        "flow_ids": payload.get("flow_ids", []),
        "evidence_paths": payload.get("evidence_paths", []),
        "supplemental_artifacts": {},
    }
    return StageResultEnvelope.from_dict(envelope_payload)


def default_stage_payload_status(stage: str, payload: dict[str, Any]) -> str:
    if payload.get("blocked_reason"):
        return "blocked"
    if stage == "Verification" and payload.get("findings"):
        return "failed"
    return "completed"
