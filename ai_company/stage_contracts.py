from __future__ import annotations

from pathlib import Path

from .models import StageContract
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

    return StageContract(
        session_id=session_id,
        stage=stage,
        goal=STAGE_GOALS.get(stage, f"Execute the {stage} stage contract."),
        input_artifacts=input_artifacts,
        required_outputs=[artifact_name_for_stage(stage)],
        forbidden_actions=list(COMMON_FORBIDDEN_ACTIONS),
        evidence_requirements=list(EVIDENCE_REQUIREMENTS.get(stage, [])),
        role_context=role.effective_skill_text if role else "",
    )
