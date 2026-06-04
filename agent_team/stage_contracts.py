from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .memory_layers import MemoryRetrievalResult, retrieve_role_memory
from .models import EvidenceRequirement, StageContract
from .roles import load_role_profiles
from .state import StateStore
from .stage_inputs import stage_input_artifact_paths
from .stage_policies import default_policy_registry

COMMON_FORBIDDEN_ACTIONS = [
    "must_not_change_stage_order",
    "must_not_skip_required_artifacts",
    "must_not_claim_workflow_done",
    "must_not_rewrite_upper_layer_truth_from_lower_layer",
    "must_not_promote_l5_or_research_to_formal_truth",
]


def _compose_role_context(role, retrieved_memory: MemoryRetrievalResult | None = None) -> str:
    if role is None:
        return ""

    sections: list[str] = []
    if role.effective_context_text.strip():
        sections.append("# Role Context\n\n" + role.effective_context_text.strip())
    if role.effective_contract_text.strip():
        sections.append("# Role Contract\n\n" + role.effective_contract_text.strip())
    if retrieved_memory is not None and retrieved_memory.matches:
        sections.append("# Relevant Memory (CLI Keyword Retrieval)\n\n" + retrieved_memory.to_markdown())
    return "\n\n".join(sections)


def build_stage_contract(
    *,
    repo_root: Path,
    state_store: StateStore,
    session_id: str,
    stage: str,
) -> StageContract:
    session = state_store.load_session(session_id)
    summary = state_store.load_workflow_summary(session_id)
    roles = load_role_profiles(repo_root=repo_root, state_root=state_store.root)
    role = roles.get(stage)
    registry = default_policy_registry()
    policy = registry.get(stage)
    retrieved_memory = (
        None
        if stage == "SessionHandoff"
        else retrieve_role_memory(
            state_root=state_store.root,
            role_name=stage,
            query=session.request,
            max_results=8,
        )
    )

    input_artifacts = stage_input_artifact_paths(
        artifact_paths=summary.artifact_paths,
        stage=stage,
    )
    required_outputs = list(policy.required_outputs)
    evidence_specs = _evidence_specs_for_summary(stage=stage, summary=summary, base_specs=policy.evidence_specs)
    evidence_requirements = [spec.name for spec in evidence_specs if spec.required]

    contract_id = _build_contract_id(
        session_id=session_id,
        stage=stage,
        summary=summary,
        required_outputs=required_outputs,
        evidence_requirements=evidence_requirements,
    )

    return StageContract(
        session_id=session_id,
        stage=stage,
        contract_id=contract_id,
        goal=policy.goal,
        input_artifacts=input_artifacts,
        required_outputs=list(policy.required_outputs),
        forbidden_actions=list(COMMON_FORBIDDEN_ACTIONS),
        evidence_requirements=evidence_requirements,
        evidence_specs=evidence_specs,
        role_context=_compose_role_context(role, retrieved_memory),
    )


def _evidence_specs_for_summary(*, stage: str, summary, base_specs: list[EvidenceRequirement]) -> list[EvidenceRequirement]:
    specs = list(base_specs)
    names = {spec.name for spec in specs}
    if stage == "Verification":
        for evidence_name in getattr(summary, "route_required_evidence", []) or []:
            evidence_name = str(evidence_name).strip()
            if evidence_name and evidence_name not in names:
                specs.append(
                    EvidenceRequirement(
                        name=evidence_name,
                        allowed_kinds=["command", "artifact", "report"],
                        required_fields=["summary"],
                    )
                )
                names.add(evidence_name)
    profile = str(getattr(summary, "verification_profile", "") or "").strip()
    if profile != "service_health":
        return specs
    additions: list[EvidenceRequirement] = []
    if stage == "Verification":
        additions.extend(
            [
                EvidenceRequirement(
                    name="service_health_contract",
                    allowed_kinds=["command", "artifact", "report"],
                    required_fields=["summary"],
                ),
                EvidenceRequirement(
                    name="service_health_in_process",
                    allowed_kinds=["command", "artifact", "report"],
                    required_fields=["summary"],
                ),
                EvidenceRequirement(
                    name="service_health_capability",
                    allowed_kinds=["command", "artifact", "report"],
                    required_fields=["summary"],
                ),
            ]
        )
    elif stage == "GovernanceReview":
        additions.append(
            EvidenceRequirement(
                name="service_health_evidence_audit",
                allowed_kinds=["artifact", "report"],
                required_fields=["summary"],
            )
        )
    else:
        return specs
    for spec in additions:
        if spec.name not in names:
            specs.append(spec)
    return specs


def _build_contract_id(
    *,
    session_id: str,
    stage: str,
    summary,
    required_outputs: list[str],
    evidence_requirements: list[str],
) -> str:
    payload = "|".join(
        [
            session_id,
            stage,
            summary.current_state,
            summary.current_stage,
            json.dumps(summary.stage_statuses, sort_keys=True, ensure_ascii=True),
            summary.acceptance_status,
            summary.human_decision,
            str(summary.verification_round),
            ",".join(required_outputs),
            ",".join(evidence_requirements),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
