from __future__ import annotations

import hashlib
from pathlib import Path

from .models import EvidenceRequirement, StageContract
from .roles import load_role_profiles
from .state import StateStore, artifact_name_for_stage


STAGE_GOALS = {
    "Product": "Draft a PRD with explicit acceptance criteria and stop for CEO approval.",
    "Dev": "Implement the approved PRD and provide self-verification evidence.",
    "QA": "Independently rerun critical verification and report passed, failed, or blocked.",
    "Acceptance": "Validate user-visible behavior against the PRD and recommend go, no-go, or blocked.",
}

COMMON_FORBIDDEN_ACTIONS = [
    "must_not_change_stage_order",
    "must_not_skip_required_artifacts",
    "must_not_claim_workflow_done",
]

EVIDENCE_REQUIREMENTS = {
    "Product": ["explicit_acceptance_criteria"],
    "Dev": ["self_verification"],
    "QA": ["independent_verification"],
    "Acceptance": ["product_level_validation"],
}

EVIDENCE_SPECS = {
    "explicit_acceptance_criteria": EvidenceRequirement(
        name="explicit_acceptance_criteria",
        allowed_kinds=["artifact", "report"],
        required_fields=["summary"],
    ),
    "self_verification": EvidenceRequirement(
        name="self_verification",
        allowed_kinds=["command", "artifact", "report"],
        required_fields=["summary"],
    ),
    "independent_verification": EvidenceRequirement(
        name="independent_verification",
        allowed_kinds=["command", "artifact", "report"],
        required_fields=["summary"],
    ),
    "product_level_validation": EvidenceRequirement(
        name="product_level_validation",
        allowed_kinds=["artifact", "report"],
        required_fields=["summary"],
    ),
}


def _compose_role_context(role) -> str:
    if role is None:
        return ""

    sections: list[str] = []
    if role.effective_context_text.strip():
        sections.append("# Role Context\n\n" + role.effective_context_text.strip())
    if role.effective_memory_text.strip():
        sections.append("# Role Memory\n\n" + role.effective_memory_text.strip())
    if role.effective_skill_text.strip():
        sections.append("# Role Skill\n\n" + role.effective_skill_text.strip())
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

    input_artifacts = dict(summary.artifact_paths)
    input_artifacts["session"] = str(session.session_dir / "session.json")
    contract_id = _build_contract_id(
        session_id=session_id,
        stage=stage,
        summary=summary,
        required_outputs=[artifact_name_for_stage(stage)],
        evidence_requirements=list(EVIDENCE_REQUIREMENTS.get(stage, [])),
    )

    return StageContract(
        session_id=session_id,
        stage=stage,
        contract_id=contract_id,
        goal=STAGE_GOALS.get(stage, f"Execute the {stage} stage contract."),
        input_artifacts=input_artifacts,
        required_outputs=[artifact_name_for_stage(stage)],
        forbidden_actions=list(COMMON_FORBIDDEN_ACTIONS),
        evidence_requirements=list(EVIDENCE_REQUIREMENTS.get(stage, [])),
        evidence_specs=_evidence_specs_for_stage(stage),
        role_context=_compose_role_context(role),
    )


def _evidence_specs_for_stage(stage: str) -> list[EvidenceRequirement]:
    return [EVIDENCE_SPECS[name] for name in EVIDENCE_REQUIREMENTS.get(stage, []) if name in EVIDENCE_SPECS]


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
            summary.prd_status,
            summary.dev_status,
            summary.qa_status,
            summary.acceptance_status,
            summary.human_decision,
            str(summary.qa_round),
            ",".join(required_outputs),
            ",".join(evidence_requirements),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
