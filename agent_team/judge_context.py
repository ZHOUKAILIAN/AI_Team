from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .models import EvidenceItem, Finding, GateResult, StageContract, StageResultEnvelope
from .stage_policies import StagePolicy

MAX_JUDGE_CONTEXT_TOKENS = 24_000
MAX_JUDGE_SECTION_TOKENS = 2_000
RESERVED_JUDGE_OUTPUT_TOKENS = 4_000
MAX_ARTIFACT_SNIPPET_CHARS = 1_600
MAX_PRIOR_FINDINGS = 20


@dataclass(slots=True)
class ArtifactRef:
    name: str
    summary: str
    sha256: str
    content_chars: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "sha256": self.sha256,
            "content_chars": self.content_chars,
        }


@dataclass(slots=True)
class EvidenceRef:
    name: str
    kind: str
    summary: str
    artifact_path: str = ""
    command: str = ""
    exit_code: int | None = None

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
        return payload


@dataclass(slots=True)
class JudgeContextBudget:
    max_context_tokens: int = MAX_JUDGE_CONTEXT_TOKENS
    max_section_tokens: int = MAX_JUDGE_SECTION_TOKENS
    reserved_output_tokens: int = RESERVED_JUDGE_OUTPUT_TOKENS
    max_artifact_snippet_chars: int = MAX_ARTIFACT_SNIPPET_CHARS
    max_prior_findings: int = MAX_PRIOR_FINDINGS

    def to_dict(self) -> dict[str, int]:
        return {
            "max_context_tokens": self.max_context_tokens,
            "max_section_tokens": self.max_section_tokens,
            "reserved_output_tokens": self.reserved_output_tokens,
            "max_artifact_snippet_chars": self.max_artifact_snippet_chars,
            "max_prior_findings": self.max_prior_findings,
        }


@dataclass(slots=True)
class JudgeContextCompact:
    session_id: str
    stage: str
    original_request_summary: str
    approved_prd_summary: str
    stage_policy: StagePolicy
    stage_contract: StageContract
    stage_result_status: str
    acceptance_matrix: list[dict[str, Any]]
    artifact_index: list[ArtifactRef]
    evidence_index: list[EvidenceRef]
    hard_gate_result: GateResult
    previous_findings: list[Finding] = field(default_factory=list)
    budget: JudgeContextBudget = field(default_factory=JudgeContextBudget)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "stage": self.stage,
            "original_request_summary": self.original_request_summary,
            "approved_prd_summary": self.approved_prd_summary,
            "stage_policy": _policy_to_dict(self.stage_policy),
            "stage_contract": self.stage_contract.to_dict(),
            "stage_result_status": self.stage_result_status,
            "acceptance_matrix": [dict(item) for item in self.acceptance_matrix],
            "artifact_index": [item.to_dict() for item in self.artifact_index],
            "evidence_index": [item.to_dict() for item in self.evidence_index],
            "hard_gate_result": self.hard_gate_result.to_dict(),
            "previous_findings": [finding.to_dict() for finding in self.previous_findings],
            "budget": self.budget.to_dict(),
            "required_output_schema": "JudgeResult",
        }


def build_judge_context_compact(
    *,
    policy: StagePolicy,
    contract: StageContract,
    result: StageResultEnvelope,
    hard_gate_result: GateResult,
    original_request_summary: str,
    approved_prd_summary: str,
    approved_acceptance_matrix: list[dict[str, Any]],
    previous_findings: list[Finding] | None = None,
) -> JudgeContextCompact:
    return JudgeContextCompact(
        session_id=result.session_id,
        stage=result.stage,
        original_request_summary=original_request_summary,
        approved_prd_summary=approved_prd_summary,
        stage_policy=policy,
        stage_contract=contract,
        stage_result_status=result.status,
        acceptance_matrix=[dict(item) for item in approved_acceptance_matrix],
        artifact_index=[_artifact_ref(result)],
        evidence_index=[_evidence_ref(item) for item in result.evidence],
        hard_gate_result=hard_gate_result,
        previous_findings=list(previous_findings or [])[:MAX_PRIOR_FINDINGS],
    )


def _artifact_ref(result: StageResultEnvelope) -> ArtifactRef:
    content = result.artifact_content or ""
    return ArtifactRef(
        name=result.artifact_name,
        summary=_summarize(content),
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        content_chars=len(content),
    )


def _evidence_ref(item: EvidenceItem) -> EvidenceRef:
    return EvidenceRef(
        name=item.name,
        kind=item.kind,
        summary=item.summary,
        artifact_path=item.artifact_path,
        command=item.command,
        exit_code=item.exit_code,
    )


def _summarize(content: str) -> str:
    compact = content.strip()
    if len(compact) <= MAX_ARTIFACT_SNIPPET_CHARS:
        return compact
    return compact[:MAX_ARTIFACT_SNIPPET_CHARS].rstrip() + "\n...[truncated]"


def _policy_to_dict(policy: StagePolicy) -> dict[str, Any]:
    return {
        "stage": policy.stage,
        "goal": policy.goal,
        "required_outputs": list(policy.required_outputs),
        "evidence_specs": [spec.to_dict() for spec in policy.evidence_specs],
        "required_checks": list(policy.required_checks),
        "allowed_agent_statuses": list(policy.allowed_agent_statuses),
        "pass_rule": policy.pass_rule,
        "failback_targets": list(policy.failback_targets),
        "approval_rule": policy.approval_rule,
        "allow_findings": policy.allow_findings,
        "blocking_conditions": list(policy.blocking_conditions),
    }
