from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


if sys.version_info >= (3, 10):
    def model_dataclass(_cls=None, **kwargs):
        return dataclass(_cls, slots=True, **kwargs)
else:
    def model_dataclass(_cls=None, **kwargs):
        return dataclass(_cls, **kwargs)


@model_dataclass
class Finding:
    source_stage: str
    target_stage: str
    issue: str
    severity: str = "medium"
    lesson: str = ""
    proposed_context_update: str = ""
    proposed_skill_update: str = ""
    evidence: str = ""
    evidence_kind: str = ""
    required_evidence: list[str] = field(default_factory=list)
    completion_signal: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Finding":
        return cls(
            source_stage=payload.get("source_stage", ""),
            target_stage=payload.get("target_stage", ""),
            issue=payload.get("issue", ""),
            severity=payload.get("severity", "medium"),
            lesson=payload.get("lesson", ""),
            proposed_context_update=payload.get("proposed_context_update", ""),
            proposed_skill_update=payload.get("proposed_skill_update", ""),
            evidence=payload.get("evidence", ""),
            evidence_kind=payload.get("evidence_kind", ""),
            required_evidence=list(payload.get("required_evidence", [])),
            completion_signal=payload.get("completion_signal", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@model_dataclass
class AcceptanceContract:
    review_method: str = ""
    boundary: str = ""
    recursive: bool = False
    tolerance_px: float | None = None
    required_dimensions: list[str] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    native_node_policy: str = ""
    allow_host_environment_changes: bool = False
    read_only_review: bool = False
    acceptance_criteria: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AcceptanceContract":
        return cls(
            review_method=payload.get("review_method", ""),
            boundary=payload.get("boundary", ""),
            recursive=bool(payload.get("recursive", False)),
            tolerance_px=payload.get("tolerance_px"),
            required_dimensions=list(payload.get("required_dimensions", [])),
            required_artifacts=list(payload.get("required_artifacts", [])),
            required_evidence=list(payload.get("required_evidence", [])),
            native_node_policy=payload.get("native_node_policy", ""),
            allow_host_environment_changes=bool(payload.get("allow_host_environment_changes", False)),
            read_only_review=bool(payload.get("read_only_review", False)),
            acceptance_criteria=list(payload.get("acceptance_criteria", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def has_constraints(self) -> bool:
        return any(
            (
                self.review_method,
                self.boundary,
                self.recursive,
                self.tolerance_px is not None,
                self.required_dimensions,
                self.required_artifacts,
                self.required_evidence,
                self.native_node_policy,
                not self.allow_host_environment_changes,
                self.read_only_review,
                self.acceptance_criteria,
            )
        )


@model_dataclass
class RoleProfile:
    name: str
    role_dir: Path
    context_path: Path
    memory_path: Path
    skill_path: Path
    base_context_text: str
    base_memory_text: str
    base_skill_text: str
    learned_context_text: str = ""
    learned_memory_text: str = ""
    learned_skill_text: str = ""

    @property
    def effective_context_text(self) -> str:
        return _join_sections(self.base_context_text, self.learned_context_text)

    @property
    def effective_memory_text(self) -> str:
        return _join_sections(self.base_memory_text, self.learned_memory_text)

    @property
    def effective_skill_text(self) -> str:
        return _join_sections(self.base_skill_text, self.learned_skill_text)


@model_dataclass
class SessionRecord:
    session_id: str
    request: str
    created_at: str
    session_dir: Path
    artifact_dir: Path
    raw_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "session_id": self.session_id,
            "request": self.request,
            "created_at": self.created_at,
            "session_dir": str(self.session_dir),
            "artifact_dir": str(self.artifact_dir),
        }
        if self.raw_message is not None:
            payload["raw_message"] = self.raw_message
        return payload


@model_dataclass
class FeedbackRecord:
    session_id: str
    source_stage: str
    target_stage: str
    issue: str
    severity: str
    created_at: str
    lesson: str = ""
    proposed_context_update: str = ""
    proposed_skill_update: str = ""
    evidence: str = ""
    evidence_kind: str = ""
    required_evidence: list[str] = field(default_factory=list)
    completion_signal: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@model_dataclass
class WorkflowSummary:
    session_id: str
    runtime_mode: str
    current_state: str
    current_stage: str
    prd_status: str = "pending"
    dev_status: str = "pending"
    qa_status: str = "pending"
    acceptance_status: str = "pending"
    human_decision: str = "pending"
    qa_round: int = 0
    blocked_reason: str = ""
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "runtime_mode": self.runtime_mode,
            "current_state": self.current_state,
            "current_stage": self.current_stage,
            "prd_status": self.prd_status,
            "dev_status": self.dev_status,
            "qa_status": self.qa_status,
            "acceptance_status": self.acceptance_status,
            "human_decision": self.human_decision,
            "qa_round": self.qa_round,
            "blocked_reason": self.blocked_reason,
            "artifact_paths": dict(self.artifact_paths),
        }


@model_dataclass
class EvidenceRequirement:
    name: str
    required: bool = True
    allowed_kinds: list[str] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)
    minimum_items: int = 1

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceRequirement":
        return cls(
            name=payload.get("name", ""),
            required=bool(payload.get("required", True)),
            allowed_kinds=list(payload.get("allowed_kinds", [])),
            required_fields=list(payload.get("required_fields", [])),
            minimum_items=int(payload.get("minimum_items", 1)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "allowed_kinds": list(self.allowed_kinds),
            "required_fields": list(self.required_fields),
            "minimum_items": self.minimum_items,
        }


@model_dataclass
class EvidenceItem:
    name: str
    kind: str = ""
    summary: str = ""
    artifact_path: str = ""
    command: str = ""
    exit_code: int | None = None
    producer: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_value(cls, value: Any) -> "EvidenceItem":
        if isinstance(value, EvidenceItem):
            return value
        if isinstance(value, str):
            return cls(name=value)
        if isinstance(value, dict):
            return cls(
                name=value.get("name", ""),
                kind=value.get("kind", ""),
                summary=value.get("summary", ""),
                artifact_path=value.get("artifact_path", ""),
                command=value.get("command", ""),
                exit_code=value.get("exit_code"),
                producer=value.get("producer", ""),
                created_at=value.get("created_at", ""),
                metadata=dict(value.get("metadata", {})),
            )
        return cls(name=str(value))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "summary": self.summary,
        }
        if self.artifact_path:
            payload["artifact_path"] = self.artifact_path
        if self.command:
            payload["command"] = self.command
        if self.exit_code is not None:
            payload["exit_code"] = self.exit_code
        if self.producer:
            payload["producer"] = self.producer
        if self.created_at:
            payload["created_at"] = self.created_at
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    def has_field(self, field_name: str) -> bool:
        return bool(getattr(self, field_name, ""))


@model_dataclass
class StageContract:
    session_id: str
    stage: str
    goal: str
    contract_id: str = ""
    input_artifacts: dict[str, str] = field(default_factory=dict)
    required_outputs: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)
    evidence_specs: list[EvidenceRequirement] = field(default_factory=list)
    role_context: str = ""

    def __post_init__(self) -> None:
        self.evidence_specs = [
            item if isinstance(item, EvidenceRequirement) else EvidenceRequirement.from_dict(item)
            for item in self.evidence_specs
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "stage": self.stage,
            "contract_id": self.contract_id,
            "goal": self.goal,
            "input_artifacts": dict(self.input_artifacts),
            "required_outputs": list(self.required_outputs),
            "forbidden_actions": list(self.forbidden_actions),
            "evidence_requirements": list(self.evidence_requirements),
            "evidence_specs": [item.to_dict() for item in self.evidence_specs],
            "role_context": self.role_context,
        }


@model_dataclass
class StageResultEnvelope:
    session_id: str
    stage: str
    status: str
    artifact_name: str
    artifact_content: str
    contract_id: str = ""
    journal: str = ""
    findings: list[Finding] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    suggested_next_owner: str = ""
    summary: str = ""
    acceptance_status: str = ""
    blocked_reason: str = ""
    supplemental_artifacts: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.evidence = [EvidenceItem.from_value(item) for item in self.evidence]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StageResultEnvelope":
        return cls(
            session_id=payload.get("session_id", ""),
            stage=payload.get("stage", ""),
            status=payload.get("status", ""),
            artifact_name=payload.get("artifact_name", ""),
            artifact_content=payload.get("artifact_content", ""),
            contract_id=payload.get("contract_id", ""),
            journal=payload.get("journal", ""),
            findings=[Finding.from_dict(item) for item in payload.get("findings", [])],
            evidence=[EvidenceItem.from_value(item) for item in payload.get("evidence", [])],
            suggested_next_owner=payload.get("suggested_next_owner", ""),
            summary=payload.get("summary", ""),
            acceptance_status=payload.get("acceptance_status", ""),
            blocked_reason=payload.get("blocked_reason", ""),
            supplemental_artifacts=dict(payload.get("supplemental_artifacts", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "stage": self.stage,
            "status": self.status,
            "artifact_name": self.artifact_name,
            "artifact_content": self.artifact_content,
            "contract_id": self.contract_id,
            "journal": self.journal,
            "findings": [finding.to_dict() for finding in self.findings],
            "evidence": [item.to_dict() for item in self.evidence],
            "suggested_next_owner": self.suggested_next_owner,
            "summary": self.summary,
            "acceptance_status": self.acceptance_status,
            "blocked_reason": self.blocked_reason,
            "supplemental_artifacts": dict(self.supplemental_artifacts),
        }


@model_dataclass
class GateResult:
    status: str
    reason: str = ""
    missing_outputs: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    checked_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "GateResult | None":
        if payload is None:
            return None
        return cls(
            status=payload.get("status", ""),
            reason=payload.get("reason", ""),
            missing_outputs=list(payload.get("missing_outputs", [])),
            missing_evidence=list(payload.get("missing_evidence", [])),
            findings=[Finding.from_dict(item) for item in payload.get("findings", [])],
            checked_at=payload.get("checked_at", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "missing_outputs": list(self.missing_outputs),
            "missing_evidence": list(self.missing_evidence),
            "findings": [finding.to_dict() for finding in self.findings],
            "checked_at": self.checked_at,
        }


@model_dataclass
class StageRunRecord:
    run_id: str
    session_id: str
    stage: str
    state: str
    contract_id: str
    attempt: int
    required_outputs: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    worker: str = ""
    created_at: str = ""
    updated_at: str = ""
    candidate_bundle_path: str = ""
    gate_result: GateResult | None = None
    blocked_reason: str = ""
    artifact_paths: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StageRunRecord":
        return cls(
            run_id=payload.get("run_id", ""),
            session_id=payload.get("session_id", ""),
            stage=payload.get("stage", ""),
            state=payload.get("state", ""),
            contract_id=payload.get("contract_id", ""),
            attempt=int(payload.get("attempt", 0)),
            required_outputs=list(payload.get("required_outputs", [])),
            required_evidence=list(payload.get("required_evidence", [])),
            worker=payload.get("worker", ""),
            created_at=payload.get("created_at", ""),
            updated_at=payload.get("updated_at", ""),
            candidate_bundle_path=payload.get("candidate_bundle_path", ""),
            gate_result=GateResult.from_dict(payload.get("gate_result")),
            blocked_reason=payload.get("blocked_reason", ""),
            artifact_paths=dict(payload.get("artifact_paths", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "stage": self.stage,
            "state": self.state,
            "contract_id": self.contract_id,
            "attempt": self.attempt,
            "required_outputs": list(self.required_outputs),
            "required_evidence": list(self.required_evidence),
            "worker": self.worker,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "candidate_bundle_path": self.candidate_bundle_path,
            "blocked_reason": self.blocked_reason,
            "artifact_paths": dict(self.artifact_paths),
        }
        if self.gate_result is not None:
            payload["gate_result"] = self.gate_result.to_dict()
        return payload


@model_dataclass
class StageOutput:
    stage: str
    artifact_name: str
    artifact_content: str
    journal: str
    findings: list[Finding] = field(default_factory=list)
    acceptance_status: str | None = None
    supplemental_artifacts: dict[str, str] = field(default_factory=dict)
    blocked_reason: str = ""


@model_dataclass
class StageRecord:
    stage: str
    artifact_name: str
    artifact_path: Path
    journal_path: Path
    findings_path: Path
    acceptance_status: str | None = None
    round_index: int = 1
    archive_path: Path | None = None
    supplemental_artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "stage": self.stage,
            "artifact_name": self.artifact_name,
            "artifact_path": str(self.artifact_path),
            "journal_path": str(self.journal_path),
            "findings_path": str(self.findings_path),
            "acceptance_status": self.acceptance_status,
            "round_index": self.round_index,
            "supplemental_artifact_paths": dict(self.supplemental_artifact_paths),
        }
        if self.archive_path is not None:
            payload["archive_path"] = str(self.archive_path)
        return payload


@model_dataclass
class WorkflowResult:
    session_id: str
    acceptance_status: str
    review_path: Path
    stage_records: list[StageRecord] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def _join_sections(primary: str, secondary: str) -> str:
    parts = [segment.strip() for segment in (primary, secondary) if segment.strip()]
    return "\n\n".join(parts)
