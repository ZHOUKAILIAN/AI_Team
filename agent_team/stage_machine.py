from __future__ import annotations

import json
from dataclasses import replace

from .models import StageResultEnvelope, WorkflowSummary
from .workflow import HUMAN_REWORK_TARGETS, STAGES, WAIT_STATES, next_required_stage, ordered_required_stages


INTERACTIVE_RUNTIME_MODES = {"runtime_driver_interactive"}
FIXED_SUCCESSORS = {
    "Route": "ProductDefinition",
    "ProductDefinition": "ProjectRuntime",
    "ProjectRuntime": "TechnicalDesign",
    "TechnicalDesign": "Implementation",
    "Implementation": "Verification",
    "Verification": "GovernanceReview",
    "GovernanceReview": "Acceptance",
    "Acceptance": "SessionHandoff",
}


class StageTransitionError(ValueError):
    pass


class StageMachine:
    def advance(self, *, summary: WorkflowSummary, stage_result: StageResultEnvelope) -> WorkflowSummary:
        if summary.session_id != stage_result.session_id:
            raise StageTransitionError("Stage result session_id does not match workflow summary.")
        if summary.current_state in WAIT_STATES:
            raise StageTransitionError(
                f"Cannot advance from {summary.current_state} without an explicit human decision."
            )
        if stage_result.status == "blocked":
            return _set_stage_status(
                summary,
                stage_result.stage,
                "blocked",
                current_state="Blocked",
                current_stage=stage_result.stage,
                blocked_reason=stage_result.summary or stage_result.blocked_reason or "Stage result is blocked.",
            )

        if stage_result.stage == "Route":
            (
                required_stages,
                stage_decisions,
                verification_mode,
                verification_profile,
                route_required_evidence,
                route_private_config_required,
                route_fixture_preconditions,
                verification_reason,
            ) = _parse_route_packet(stage_result)
            next_state, next_stage = _transition_to_next_stage(required_stages=required_stages, after_stage="Route")
            updated = _set_stage_status(
                summary,
                "Route",
                "completed",
                current_state=next_state,
                current_stage=next_stage,
                route_required_stages=required_stages,
                route_stage_decisions=stage_decisions,
                verification_mode=verification_mode,
                verification_profile=verification_profile,
                route_required_evidence=route_required_evidence,
                route_private_config_required=route_private_config_required,
                route_fixture_preconditions=route_fixture_preconditions,
                verification_reason=verification_reason,
            )
            for stage_name, item in stage_decisions.items():
                if item.get("decision") == "skipped":
                    updated = _set_stage_status(updated, stage_name, "skipped")
            return updated

        if stage_result.stage == "ProductDefinition":
            outcome = stage_result.product_definition_outcome or "l1_delta_pending_approval"
            if outcome == "no_l1_delta":
                next_state, next_stage = _transition_to_next_stage(
                    required_stages=summary.route_required_stages,
                    after_stage="ProductDefinition",
                )
                return _set_stage_status(
                    summary,
                    "ProductDefinition",
                    "skipped",
                    current_state=next_state,
                    current_stage=next_stage,
                    product_definition_outcome=outcome,
                )
            if _requires_approval_wait(summary.route_required_stages, "ProductDefinition"):
                return _set_stage_status(
                    summary,
                    "ProductDefinition",
                    "drafted",
                    current_state="WaitForProductDefinitionApproval",
                    current_stage="ProductDefinition",
                    human_decision="pending",
                    product_definition_outcome=outcome,
                )
            next_state, next_stage = _transition_to_next_stage(
                required_stages=summary.route_required_stages,
                after_stage="ProductDefinition",
            )
            return _set_stage_status(
                summary,
                "ProductDefinition",
                "completed",
                current_state=next_state,
                current_stage=next_stage,
                product_definition_outcome=outcome,
            )

        if stage_result.stage == "ProjectRuntime":
            next_state, next_stage = _transition_to_next_stage(
                required_stages=summary.route_required_stages,
                after_stage="ProjectRuntime",
            )
            return _set_stage_status(
                summary,
                "ProjectRuntime",
                "completed",
                current_state=next_state,
                current_stage=next_stage,
            )

        if stage_result.stage == "TechnicalDesign":
            if _requires_approval_wait(summary.route_required_stages, "TechnicalDesign"):
                return _set_stage_status(
                    summary,
                    "TechnicalDesign",
                    "drafted",
                    current_state="WaitForTechnicalDesignApproval",
                    current_stage="TechnicalDesign",
                    human_decision="pending",
                )
            next_state, next_stage = _transition_to_next_stage(
                required_stages=summary.route_required_stages,
                after_stage="TechnicalDesign",
            )
            return _set_stage_status(
                summary,
                "TechnicalDesign",
                "completed",
                current_state=next_state,
                current_stage=next_stage,
            )

        if stage_result.stage == "Implementation":
            next_state, next_stage = _transition_to_next_stage(
                required_stages=summary.route_required_stages,
                after_stage="Implementation",
            )
            return _set_stage_status(
                summary,
                "Implementation",
                "completed",
                current_state=next_state,
                current_stage=next_stage,
            )

        if stage_result.stage == "Verification":
            next_verification_round = summary.verification_round + 1
            verification_status = _verification_stage_status(stage_result)
            if verification_status == "failed":
                target_stage = _verification_rework_target(summary.route_required_stages, stage_result.findings)
                return _set_stage_status(
                    summary,
                    "Verification",
                    "failed",
                    current_state=target_stage,
                    current_stage=target_stage,
                    verification_round=next_verification_round,
                )
            next_state, next_stage = _transition_to_next_stage(
                required_stages=summary.route_required_stages,
                after_stage="Verification",
            )
            acceptance_status = (
                "needs_verification"
                if verification_status == "needs_verification"
                else summary.acceptance_status
            )
            return _set_stage_status(
                summary,
                "Verification",
                verification_status,
                current_state=next_state,
                current_stage=next_stage,
                verification_round=next_verification_round,
                acceptance_status=acceptance_status,
            )

        if stage_result.stage == "GovernanceReview":
            if stage_result.status == "failed" or _has_blocking_findings(stage_result.findings):
                return _set_stage_status(
                    summary,
                    "GovernanceReview",
                    "blocked",
                    current_state="Blocked",
                    current_stage="GovernanceReview",
                    blocked_reason=stage_result.summary or "Governance review found blocking issues.",
                )
            next_state, next_stage = _transition_to_next_stage(
                required_stages=summary.route_required_stages,
                after_stage="GovernanceReview",
            )
            return _set_stage_status(
                summary,
                "GovernanceReview",
                "passed_with_cautions" if stage_result.findings else "passed",
                current_state=next_state,
                current_stage=next_stage,
            )

        if stage_result.stage == "Acceptance":
            acceptance_status = stage_result.acceptance_status or stage_result.release_recommendation or (
                "blocked" if stage_result.findings else "recommended_go"
            )
            if acceptance_status == "blocked":
                return _set_stage_status(
                    summary,
                    "Acceptance",
                    "blocked",
                    current_state="Blocked",
                    current_stage="Acceptance",
                    acceptance_status=acceptance_status,
                    blocked_reason=stage_result.summary or "Acceptance result is blocked.",
                )
            next_state, next_stage = _transition_to_next_stage(
                required_stages=summary.route_required_stages,
                after_stage="Acceptance",
            )
            return _set_stage_status(
                summary,
                "Acceptance",
                acceptance_status,
                current_state=next_state,
                current_stage=next_stage,
                acceptance_status=acceptance_status,
            )

        if stage_result.stage == "SessionHandoff":
            if _requires_session_handoff_wait(summary.route_required_stages):
                return _set_stage_status(
                    summary,
                    "SessionHandoff",
                    "completed",
                    current_state="WaitForHumanDecision",
                    current_stage="SessionHandoff",
                    human_decision="pending",
                )
            return _set_stage_status(
                summary,
                "SessionHandoff",
                "completed",
                current_state="Done",
                current_stage="SessionHandoff",
            )

        raise StageTransitionError(f"Unsupported stage result: {stage_result.stage}")

    def apply_human_decision(
        self,
        *,
        summary: WorkflowSummary,
        decision: str,
        target_stage: str | None = None,
    ) -> WorkflowSummary:
        normalized = decision.strip().lower()
        if normalized not in {"go", "no-go", "rework"}:
            raise StageTransitionError(f"Unsupported human decision: {decision}")

        if summary.current_state == "WaitForProductDefinitionApproval":
            if normalized == "go":
                next_state, next_stage = _transition_to_next_stage(
                    required_stages=summary.route_required_stages,
                    after_stage="ProductDefinition",
                )
                return _set_stage_status(
                    summary,
                    "ProductDefinition",
                    "approved",
                    current_state=next_state,
                    current_stage=next_stage,
                    human_decision=normalized,
                )
            if normalized == "rework":
                return _set_stage_status(
                    summary,
                    "ProductDefinition",
                    "rework_requested",
                    current_state="ProductDefinition",
                    current_stage="ProductDefinition",
                    human_decision=normalized,
                )
            return replace(
                summary,
                current_state="Done",
                current_stage="ProductDefinition",
                human_decision=normalized,
                blocked_reason="",
            )

        if summary.current_state == "WaitForTechnicalDesignApproval":
            if normalized == "go":
                next_state, next_stage = _transition_to_next_stage(
                    required_stages=summary.route_required_stages,
                    after_stage="TechnicalDesign",
                )
                return _set_stage_status(
                    summary,
                    "TechnicalDesign",
                    "approved",
                    current_state=next_state,
                    current_stage=next_stage,
                    human_decision=normalized,
                )
            if normalized == "rework":
                return _set_stage_status(
                    summary,
                    "TechnicalDesign",
                    "rework_requested",
                    current_state="TechnicalDesign",
                    current_stage="TechnicalDesign",
                    human_decision=normalized,
                )
            return replace(
                summary,
                current_state="Done",
                current_stage="TechnicalDesign",
                human_decision=normalized,
                blocked_reason="",
            )

        if summary.current_state == "WaitForHumanDecision":
            if normalized in {"go", "no-go"}:
                return replace(
                    summary,
                    current_state="Done",
                    current_stage="SessionHandoff",
                    human_decision=normalized,
                    blocked_reason="",
                )
            target = target_stage or ""
            if target not in HUMAN_REWORK_TARGETS:
                raise StageTransitionError(
                    "Rework decisions require a five-layer target stage before SessionHandoff."
                )
            return _set_stage_status(
                summary,
                target,
                "rework_requested",
                current_state=target,
                current_stage=target,
                human_decision=normalized,
            )

        if normalized == "rework":
            target = target_stage or summary.current_stage or summary.current_state
            if target not in HUMAN_REWORK_TARGETS:
                raise StageTransitionError(
                    "Rework decisions require a five-layer target stage before SessionHandoff."
                )
            return _set_stage_status(
                summary,
                target,
                "rework_requested",
                current_state=target,
                current_stage=target,
                human_decision=normalized,
            )

        raise StageTransitionError(
            f"Human decisions are only valid from wait states, not {summary.current_state}."
        )


def _is_interactive_runtime(summary: WorkflowSummary) -> bool:
    return summary.runtime_mode in INTERACTIVE_RUNTIME_MODES


ROUTE_STAGE_ALIASES = {
    "design": "TechnicalDesign",
    "technicaldesign": "TechnicalDesign",
    "technical_design": "TechnicalDesign",
    "technical-design": "TechnicalDesign",
    "implement": "Implementation",
    "implementation": "Implementation",
    "verify": "Verification",
    "verification": "Verification",
    "governance": "GovernanceReview",
    "governancereview": "GovernanceReview",
    "governance_review": "GovernanceReview",
    "governance-review": "GovernanceReview",
    "accept": "Acceptance",
    "acceptance": "Acceptance",
    "handoff": "SessionHandoff",
    "sessionhandoff": "SessionHandoff",
    "session_handoff": "SessionHandoff",
    "session-handoff": "SessionHandoff",
    "productdefinition": "ProductDefinition",
    "product_definition": "ProductDefinition",
    "product-definition": "ProductDefinition",
    "projectruntime": "ProjectRuntime",
    "project_runtime": "ProjectRuntime",
    "project-runtime": "ProjectRuntime",
}


def _route_required_stage_names(raw_required_stages: object) -> list[str]:
    names: list[str] = []
    if not isinstance(raw_required_stages, list):
        return names
    for item in raw_required_stages:
        raw_name = ""
        if isinstance(item, str):
            raw_name = item
        elif isinstance(item, dict):
            raw_name = str(item.get("stage", "") or "")
        if not raw_name:
            continue
        normalized_key = raw_name.strip().replace(" ", "").lower()
        names.append(ROUTE_STAGE_ALIASES.get(normalized_key, raw_name))
    return names

def _route_required_stages_from_affected_layers(raw_affected_layers: object) -> list[str]:
    if not isinstance(raw_affected_layers, list):
        return []
    layers = {str(layer).strip().upper() for layer in raw_affected_layers}
    stages: list[str] = []
    if "L1" in layers:
        stages.append("ProductDefinition")
    if "L3" in layers:
        stages.append("ProjectRuntime")
    if "L2" in layers:
        stages.extend(["TechnicalDesign", "Implementation"])
    if "L4" in layers:
        stages.append("GovernanceReview")
    return stages

def _normalize_required_stages(route_required_stages: list[str]) -> list[str]:
    ordered = ordered_required_stages([str(stage) for stage in route_required_stages])
    for stage in ("Verification", "GovernanceReview", "Acceptance", "SessionHandoff"):
        if stage not in ordered:
            ordered.append(stage)
    return [stage for stage in STAGES if stage in ordered]

def _verification_rework_target(required_stages: list[str], findings: list[object]) -> str:
    for finding in findings:
        if _finding_severity(finding) not in {"critical", "high", "blocking", "blocker", "error"}:
            continue
        target = _finding_target_stage(finding)
        if target in HUMAN_REWORK_TARGETS and (not required_stages or target in required_stages):
            return target
    if not required_stages or "Implementation" in required_stages:
        return "Implementation"
    for stage in reversed(ordered_required_stages(required_stages)):
        if stage in {"ProductDefinition", "ProjectRuntime", "TechnicalDesign"}:
            return stage
    return "Verification"


def _verification_stage_status(stage_result: StageResultEnvelope) -> str:
    status = stage_result.status.strip().lower()
    conclusion = stage_result.verification_conclusion.strip().lower()
    release_recommendation = stage_result.release_recommendation.strip().lower()
    gate_decision = stage_result.gate_decision.strip().lower()

    if status == "failed" or conclusion == "fail" or gate_decision in {"rework", "fail"}:
        return "failed"
    if gate_decision in {"block", "blocked"}:
        return "failed"
    if status == "needs_verification" or conclusion == "needs_verification" or release_recommendation == "needs_verification":
        return "needs_verification"
    if status == "partial" or conclusion == "partial":
        return "partial"
    if _has_blocking_findings(stage_result.findings) and gate_decision != "proceed":
        return "failed"
    return "passed_with_cautions" if stage_result.findings else "passed"


def _finding_target_stage(finding: object) -> str:
    if isinstance(finding, dict):
        return str(finding.get("target_stage", "") or "")
    return str(getattr(finding, "target_stage", "") or "")


def _has_blocking_findings(findings: list[object]) -> bool:
    return any(_finding_severity(item) in {"critical", "high", "blocking", "blocker", "error"} for item in findings)


def _finding_severity(finding: object) -> str:
    if isinstance(finding, dict):
        return str(finding.get("severity", "") or "").strip().lower()
    return str(getattr(finding, "severity", "") or "").strip().lower()

def _parse_route_packet(
    stage_result: StageResultEnvelope,
) -> tuple[list[str], dict[str, dict[str, str]], str, str, list[str], bool, list[str], str]:
    try:
        payload = json.loads(stage_result.artifact_content)
    except json.JSONDecodeError as exc:
        raise StageTransitionError(f"Route artifact is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise StageTransitionError("Route artifact must be a JSON object.")
    required_stages = _route_required_stage_names(payload.get("required_stages", []))
    if not required_stages:
        required_stages = _route_required_stages_from_affected_layers(payload.get("affected_layers", []))
    required_stages = _add_document_delivery_implementation_stage(required_stages, payload)
    required_stages = _normalize_required_stages(required_stages)
    stage_decisions = {
        str(name): {str(key): str(value) for key, value in dict(item).items()}
        for name, item in dict(payload.get("stage_decisions", {})).items()
    }
    verification_mode = str(payload.get("verification_mode", ""))
    verification_profile = str(payload.get("verification_profile", payload.get("service_profile", "")))
    route_required_evidence = _string_list(payload.get("required_evidence", []))
    route_private_config_required = bool(payload.get("private_config_required", False))
    route_fixture_preconditions = _route_fixture_preconditions(payload.get("fixture_preconditions", []))
    verification_reason = str(payload.get("verification_reason", ""))
    return (
        required_stages,
        stage_decisions,
        verification_mode,
        verification_profile,
        route_required_evidence,
        route_private_config_required,
        route_fixture_preconditions,
        verification_reason,
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _route_fixture_preconditions(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            summary = str(item.get("summary", item.get("description", ""))).strip()
            text = ": ".join(part for part in (name, summary) if part)
        else:
            text = str(item).strip()
        if text:
            items.append(text)
    return items


def _add_document_delivery_implementation_stage(required_stages: list[str], payload: dict[str, object]) -> list[str]:
    if "Implementation" in required_stages:
        return required_stages
    if not _route_requires_repository_document_delivery(payload):
        return required_stages
    stages = list(required_stages)
    if "TechnicalDesign" in stages:
        stages.insert(stages.index("TechnicalDesign") + 1, "Implementation")
    elif "ProjectRuntime" in stages:
        stages.insert(stages.index("ProjectRuntime") + 1, "Implementation")
    else:
        stages.append("Implementation")
    return stages


def _route_requires_repository_document_delivery(payload: dict[str, object]) -> bool:
    text_parts: list[str] = []
    for key in (
        "delivery_type",
        "deliverable_type",
        "artifact_type",
        "implementation_type",
        "summary",
        "reason",
        "notes",
        "scope",
        "implementation_required",
    ):
        value = payload.get(key)
        if value is not None:
            text_parts.append(str(value))
    for key in ("required_artifacts", "deliverables", "output_artifacts", "target_files", "red_lines", "acceptance_criteria"):
        value = payload.get(key)
        if isinstance(value, list):
            text_parts.extend(str(item) for item in value)
        elif value is not None:
            text_parts.append(str(value))
    stage_decisions = payload.get("stage_decisions")
    if isinstance(stage_decisions, dict):
        text_parts.append(str(stage_decisions))
    text = "\n".join(text_parts).lower()
    if not text:
        return False
    has_repo_doc_target = any(
        token in text
        for token in (
            "docs/",
            "readme",
            "repository document",
            "formal document",
            "formal artifact",
            "repo document",
            "document delivery",
            "doc delivery",
            "正式文档",
            "仓库文档",
            "落为仓库",
            "落库",
        )
    )
    has_delivery_signal = any(
        token in text
        for token in (
            "deliver",
            "delivery",
            "write",
            "create",
            "update",
            "add",
            "implementation must",
            "必须",
            "交付",
            "写入",
            "新增",
            "更新",
            "创建",
        )
    )
    return has_repo_doc_target and has_delivery_signal


def _requires_approval_wait(required_stages: list[str], stage: str) -> bool:
    return not required_stages or stage in required_stages


def _requires_session_handoff_wait(required_stages: list[str]) -> bool:
    return _requires_approval_wait(required_stages, "SessionHandoff")


def _transition_to_next_stage(*, required_stages: list[str], after_stage: str) -> tuple[str, str]:
    next_stage = _next_stage_after(required_stages=required_stages, after_stage=after_stage)
    if next_stage is None:
        return "Done", after_stage
    return next_stage, next_stage


def _next_stage_after(*, required_stages: list[str], after_stage: str) -> str | None:
    if required_stages:
        return next_required_stage(required_stages=required_stages, after_stage=after_stage)
    return FIXED_SUCCESSORS.get(after_stage)


def _set_stage_status(summary: WorkflowSummary, stage: str, status: str, **changes: object) -> WorkflowSummary:
    stage_statuses = dict(summary.stage_statuses)
    stage_statuses[stage] = status
    if status not in {"blocked", "failed"} and "blocked_reason" not in changes:
        changes["blocked_reason"] = ""
    return replace(summary, stage_statuses=stage_statuses, **changes)
