from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .judge_context import ArtifactRef
from .models import AcceptanceContract, Finding, StageContract
from .project_structure import detect_project_structure, resolve_role_context_paths
from .state import StateStore

MAX_EXECUTION_CONTEXT_TOKENS = 24_000
MAX_EXECUTION_ARTIFACT_SNIPPET_CHARS = 4_000
MAX_EXECUTION_FINDINGS = 20


@dataclass(slots=True)
class ExecutionContextBudget:
    max_context_tokens: int = MAX_EXECUTION_CONTEXT_TOKENS
    max_artifact_snippet_chars: int = MAX_EXECUTION_ARTIFACT_SNIPPET_CHARS
    max_findings: int = MAX_EXECUTION_FINDINGS

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(slots=True)
class StageExecutionContext:
    session_id: str
    stage: str
    round_index: int
    context_id: str
    contract_id: str
    original_request_summary: str
    approved_prd_summary: str
    acceptance_matrix: list[dict[str, Any]]
    constraints: list[str]
    required_outputs: list[str]
    required_evidence: list[str]
    relevant_artifacts: list[ArtifactRef]
    actionable_findings: list[Finding] = field(default_factory=list)
    repo_context_summary: str = ""
    role_context_digest: str = ""
    budget: ExecutionContextBudget = field(default_factory=ExecutionContextBudget)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "stage": self.stage,
            "round_index": self.round_index,
            "context_id": self.context_id,
            "contract_id": self.contract_id,
            "original_request_summary": self.original_request_summary,
            "approved_prd_summary": self.approved_prd_summary,
            "acceptance_matrix": [dict(item) for item in self.acceptance_matrix],
            "constraints": list(self.constraints),
            "required_outputs": list(self.required_outputs),
            "required_evidence": list(self.required_evidence),
            "relevant_artifacts": [item.to_dict() for item in self.relevant_artifacts],
            "actionable_findings": [finding.to_dict() for finding in self.actionable_findings],
            "repo_context_summary": self.repo_context_summary,
            "role_context_digest": self.role_context_digest,
            "budget": self.budget.to_dict(),
        }


def build_stage_execution_context(
    *,
    repo_root: Path,
    state_store: StateStore,
    session_id: str,
    stage: str,
    contract: StageContract,
) -> StageExecutionContext:
    session = state_store.load_session(session_id)
    summary = state_store.load_workflow_summary(session_id)
    acceptance_contract = state_store.load_acceptance_contract(session_id)
    prd_path = _approved_prd_path(summary.artifact_paths)
    approved_prd = _read_text(prd_path)
    actionable_findings = _load_actionable_findings(session.session_dir / "session.json", stage)
    round_index = _next_context_round(state_store, session_id, stage)
    artifact_refs = _artifact_refs(
        {
            "prd": prd_path,
            **{key: Path(value) for key, value in summary.artifact_paths.items() if Path(value).exists()},
        }
    )
    acceptance_matrix = _acceptance_matrix(
        contract=acceptance_contract,
        approved_prd=approved_prd,
    )
    role_context_digest = _digest_text(contract.role_context)
    context_id = _context_id(
        session_id=session_id,
        stage=stage,
        round_index=round_index,
        contract_id=contract.contract_id,
        approved_prd=approved_prd,
        findings=actionable_findings,
    )

    return StageExecutionContext(
        session_id=session_id,
        stage=stage,
        round_index=round_index,
        context_id=context_id,
        contract_id=contract.contract_id,
        original_request_summary=session.request,
        approved_prd_summary=_summarize(approved_prd),
        acceptance_matrix=acceptance_matrix,
        constraints=_constraints_from_contract(acceptance_contract),
        required_outputs=list(contract.required_outputs),
        required_evidence=list(contract.evidence_requirements),
        relevant_artifacts=artifact_refs,
        actionable_findings=actionable_findings[:MAX_EXECUTION_FINDINGS],
        repo_context_summary=_repo_context_summary(repo_root=repo_root, stage=stage),
        role_context_digest=role_context_digest,
    )


def _approved_prd_path(artifact_paths: dict[str, str]) -> Path | None:
    for key in ("product", "prd"):
        value = artifact_paths.get(key)
        if value and Path(value).exists():
            return Path(value)
    return None


def _read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text()


def _load_actionable_findings(session_path: Path, stage: str) -> list[Finding]:
    if not session_path.exists():
        return []
    payload = json.loads(session_path.read_text())
    findings = [Finding.from_dict(item) for item in payload.get("findings", [])]
    for feedback_path in payload.get("feedback_records", []):
        path = Path(feedback_path)
        if path.exists():
            findings.append(Finding.from_dict(json.loads(path.read_text())))
    return [finding for finding in findings if finding.target_stage == stage][:MAX_EXECUTION_FINDINGS]


def _next_context_round(state_store: StateStore, session_id: str, stage: str) -> int:
    latest = state_store.latest_execution_context_path(session_id, stage)
    if latest is None:
        return 1
    match = re.search(r"_round_(\d+)\.json$", latest.name)
    if not match:
        return 1
    return int(match.group(1)) + 1


def _artifact_refs(paths: dict[str, Path | None]) -> list[ArtifactRef]:
    refs: list[ArtifactRef] = []
    seen: set[Path] = set()
    for name, path in paths.items():
        if path is None or not path.exists() or path in seen:
            continue
        seen.add(path)
        content = path.read_text()
        refs.append(
            ArtifactRef(
                name=name,
                summary=_summarize(content),
                sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                content_chars=len(content),
            )
        )
    return refs


def _acceptance_matrix(*, contract: AcceptanceContract | None, approved_prd: str) -> list[dict[str, Any]]:
    if contract is not None and contract.acceptance_criteria:
        return [
            {
                "id": f"AC-{index:03d}",
                "criterion": criterion,
                "source": "acceptance_contract",
            }
            for index, criterion in enumerate(contract.acceptance_criteria, start=1)
        ]

    criteria = _extract_prd_acceptance_criteria(approved_prd)
    return [
        {
            "id": f"AC-{index:03d}",
            "criterion": criterion,
            "source": "prd",
        }
        for index, criterion in enumerate(criteria, start=1)
    ]


def _extract_prd_acceptance_criteria(content: str) -> list[str]:
    criteria: list[str] = []
    in_section = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            in_section = "acceptance" in line.lower() or "验收" in line
            continue
        if in_section and line.startswith(("- ", "* ")):
            criteria.append(line[2:].strip())
    return criteria


def _constraints_from_contract(contract: AcceptanceContract | None) -> list[str]:
    if contract is None:
        return []
    constraints: list[str] = []
    if contract.review_method:
        constraints.append(f"review_method: {contract.review_method}")
    if contract.boundary:
        constraints.append(f"boundary: {contract.boundary}")
    if contract.tolerance_px is not None:
        constraints.append(f"tolerance_px: {contract.tolerance_px}")
    if contract.required_artifacts:
        constraints.append("required_artifacts: " + ", ".join(contract.required_artifacts))
    if contract.required_evidence:
        constraints.append("required_evidence: " + ", ".join(contract.required_evidence))
    if contract.native_node_policy:
        constraints.append(f"native_node_policy: {contract.native_node_policy}")
    if contract.read_only_review:
        constraints.append("read_only_review: true")
    return constraints


def _repo_context_summary(*, repo_root: Path, stage: str) -> str:
    structure = detect_project_structure(repo_root)
    role_paths = resolve_role_context_paths(repo_root, stage)
    files = [role_paths.context_path, role_paths.memory_path, role_paths.guidance_path]
    present = [str(path.relative_to(repo_root)) for path in files if path.exists()]
    details = []
    if structure.doc_map:
        details.append(
            "doc map: "
            + ", ".join(f"{key}={value}" for key, value in sorted(structure.doc_map.items()))
        )
    if present:
        details.append(f"{role_paths.source} role files: " + ", ".join(present))
    if not details:
        return f"No repo-local Agent Team context files found for {stage}."
    return " | ".join(details)


def _digest_text(value: str) -> str:
    if not value.strip():
        return ""
    sha = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"sha256:{sha}; chars:{len(value)}"


def _context_id(
    *,
    session_id: str,
    stage: str,
    round_index: int,
    contract_id: str,
    approved_prd: str,
    findings: list[Finding],
) -> str:
    payload = json.dumps(
        {
            "session_id": session_id,
            "stage": stage,
            "round_index": round_index,
            "contract_id": contract_id,
            "approved_prd_sha256": hashlib.sha256(approved_prd.encode("utf-8")).hexdigest(),
            "findings": [finding.to_dict() for finding in findings],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _summarize(content: str) -> str:
    compact = content.strip()
    if len(compact) <= MAX_EXECUTION_ARTIFACT_SNIPPET_CHARS:
        return compact
    return compact[:MAX_EXECUTION_ARTIFACT_SNIPPET_CHARS].rstrip() + "\n...[truncated]"
