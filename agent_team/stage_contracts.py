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
    private_config_contract = _private_config_contract(repo_root=repo_root, stage=stage, summary=summary)

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
        route_required_evidence=list(getattr(summary, "route_required_evidence", []) or []),
        private_config_contract=private_config_contract,
        role_context=_compose_role_context(role, retrieved_memory),
    )


def _evidence_specs_for_summary(*, stage: str, summary, base_specs: list[EvidenceRequirement]) -> list[EvidenceRequirement]:
    specs = list(base_specs)
    names = {spec.name for spec in specs}
    profile = str(getattr(summary, "verification_profile", "") or "").strip()
    if stage == "Verification":
        for evidence_name in getattr(summary, "route_required_evidence", []) or []:
            evidence_name = str(evidence_name).strip()
            if _route_evidence_is_profile_alias(evidence_name=evidence_name, profile=profile):
                continue
            if evidence_name and evidence_name not in names:
                specs.append(
                    EvidenceRequirement(
                        name=evidence_name,
                        allowed_kinds=["command", "artifact", "report"],
                        required_fields=["summary"],
                    )
                )
                names.add(evidence_name)
        if getattr(summary, "route_private_config_required", False) and "private_config_contract" not in names:
            specs.append(
                EvidenceRequirement(
                    name="private_config_contract",
                    allowed_kinds=["artifact", "report"],
                    required_fields=["summary"],
                )
            )
            names.add("private_config_contract")
    elif stage == "GovernanceReview" and getattr(summary, "route_required_evidence", None):
        specs.append(
            EvidenceRequirement(
                name="verification_evidence_depth_audit",
                allowed_kinds=["artifact", "report"],
                required_fields=["summary"],
            )
        )
        names.add("verification_evidence_depth_audit")
    additions = _profile_evidence_specs(stage=stage, profile=profile, summary=summary)
    for spec in additions:
        if spec.name not in names:
            specs.append(spec)
    return specs


def _profile_evidence_specs(*, stage: str, profile: str, summary) -> list[EvidenceRequirement]:
    if profile == "service_health":
        return _service_health_evidence_specs(stage=stage)
    if profile == "backend_api_db":
        return _backend_api_db_evidence_specs(stage=stage, summary=summary)
    return []


def _service_health_evidence_specs(*, stage: str) -> list[EvidenceRequirement]:
    if stage == "Verification":
        return [
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
    if stage == "GovernanceReview":
        return [
            EvidenceRequirement(
                name="service_health_evidence_audit",
                allowed_kinds=["artifact", "report"],
                required_fields=["summary"],
            )
        ]
    return []


_BACKEND_ROUTE_EVIDENCE_ALIASES = {
    "api_response": "backend_api_response",
    "db_precondition": "backend_db_precondition",
    "database_precondition": "backend_db_precondition",
    "fixture_precondition": "backend_fixture_precondition",
    "private_config": "backend_private_config_summary",
    "private_config_summary": "backend_private_config_summary",
    "logs": "backend_logs",
    "log": "backend_logs",
    "idempotency": "backend_idempotency",
    "consistency": "backend_consistency",
    "permission": "backend_permission",
    "permissions": "backend_permission",
    "concurrency": "backend_concurrency",
    "side_effect": "backend_side_effect",
    "side_effects": "backend_side_effect",
}


def _route_evidence_is_profile_alias(*, evidence_name: str, profile: str) -> bool:
    if profile != "backend_api_db":
        return False
    return evidence_name.strip().lower() in _BACKEND_ROUTE_EVIDENCE_ALIASES


def _backend_api_db_evidence_specs(*, stage: str, summary) -> list[EvidenceRequirement]:
    if stage == "GovernanceReview":
        return [
            EvidenceRequirement(
                name="backend_api_db_evidence_audit",
                allowed_kinds=["artifact", "report"],
                required_fields=["summary"],
            )
        ]
    if stage != "Verification":
        return []

    required_names = {
        "backend_api_response",
        "backend_db_precondition",
        "backend_fixture_precondition",
        "backend_private_config_summary",
    }
    for evidence_name in getattr(summary, "route_required_evidence", []) or []:
        normalized = str(evidence_name).strip().lower()
        mapped = _BACKEND_ROUTE_EVIDENCE_ALIASES.get(normalized)
        if mapped:
            required_names.add(mapped)
    if getattr(summary, "route_private_config_required", False):
        required_names.add("backend_private_config_summary")

    ordered_names = [
        "backend_api_response",
        "backend_db_precondition",
        "backend_fixture_precondition",
        "backend_private_config_summary",
        "backend_logs",
        "backend_idempotency",
        "backend_consistency",
        "backend_permission",
        "backend_concurrency",
        "backend_side_effect",
    ]
    return [
        EvidenceRequirement(
            name=name,
            allowed_kinds=["command", "artifact", "report"],
            required_fields=["summary"],
        )
        for name in ordered_names
        if name in required_names
    ]


_PRIVATE_CONFIG_RECOMMENDED_PROFILE_KEYS = ("TEST_BASE_URL", "TEST_AUTH_TOKEN", "TEST_DB_READONLY_DSN")


def _private_config_contract(*, repo_root: Path, stage: str, summary) -> dict[str, object]:
    required = bool(getattr(summary, "route_private_config_required", False)) and stage == "Verification"
    path = repo_root / ".agt" / "local" / "verification-private.json"
    contract: dict[str, object] = {
        "required": required,
        "path": str(path),
        "exists": path.exists(),
        "readonly": True,
        "missing_keys": [],
        "profiles": {},
    }
    if not required and not path.exists():
        return contract
    if not path.exists():
        contract["missing_keys"] = ["profiles"]
        return contract

    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        contract["missing_keys"] = ["valid_json", "profiles"]
        return contract
    if not isinstance(payload, dict):
        contract["missing_keys"] = ["profiles"]
        return contract

    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        contract["missing_keys"] = ["profiles"]
        return contract

    missing_keys: list[str] = []
    redacted_profiles: dict[str, object] = {}
    for profile_name, raw_profile in profiles.items():
        profile_key = str(profile_name)
        if isinstance(raw_profile, dict):
            raw_keys = {str(key) for key in raw_profile}
            for required_key in _PRIVATE_CONFIG_RECOMMENDED_PROFILE_KEYS:
                if required_key not in raw_keys:
                    missing_keys.append(f"profiles.{profile_key}.{required_key}")
            redacted_profiles[profile_key] = {
                str(key): _redacted_private_config_value(value) for key, value in raw_profile.items()
            }
        else:
            missing_keys.append(f"profiles.{profile_key}")
            redacted_profiles[profile_key] = "<redacted>"
    contract["missing_keys"] = missing_keys
    contract["profiles"] = redacted_profiles
    return contract


def _redacted_private_config_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _redacted_private_config_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return ["<redacted>" for _item in value]
    return "<redacted>"


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
