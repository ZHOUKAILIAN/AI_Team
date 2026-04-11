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
