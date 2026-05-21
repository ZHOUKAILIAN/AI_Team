from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    AcceptanceContract,
    FeedbackRecord,
    Finding,
    GateResult,
    SessionRecord,
    StageResultEnvelope,
    StageOutput,
    StageRecord,
    StageRunRecord,
    WorkflowSummary,
)
from .memory_layers import record_learning_layers
from .workflow import STAGE_SLUGS, STAGES, artifact_name_for, stage_slug

VALID_ROLE_NAMES = set(STAGES)
ACTIVE_STAGE_RUN_STATES = {"READY", "RUNNING", "SUBMITTED", "VERIFYING"}
TERMINAL_STAGE_RUN_STATES = {"PASSED", "FAILED", "BLOCKED"}

_LEGACY_SLUGS = {
    "Product": "product",
    "Acceptance": "acceptance",
    "Dev": "development",
    "QA": "quality-assurance",
}


def _resolve_stage_dir(session_dir: Path, stage: str) -> Path | None:
    """Return the existing roles/{slug} dir for *stage*, trying the current slug first then legacy."""
    slug = _stage_slug(stage)
    candidate = session_dir / "roles" / slug
    if candidate.exists():
        return candidate
    legacy = _LEGACY_SLUGS.get(stage, "")
    if legacy:
        legacy_candidate = session_dir / "roles" / legacy
        if legacy_candidate.exists():
            return legacy_candidate
    return candidate


class StageRunStateError(ValueError):
    pass


class StateStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure_layout(self) -> None:
        for directory in (
            self.root,
            self.root / "memory",
            self.root / "_runtime" / "sessions",
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        request: str,
        raw_message: str | None = None,
        contract: AcceptanceContract | None = None,
        *,
        runtime_mode: str = "session_bootstrap",
        initiator: str = "agent",
    ) -> SessionRecord:
        self.ensure_layout()
        session_id = self._next_session_id(request)
        session_dir = self._runtime_session_dir(session_id)
        artifact_dir = self._public_session_dir(session_id)

        session_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        session = SessionRecord(
            session_id=session_id,
            request=request,
            created_at=datetime.now(timezone.utc).isoformat(),
            session_dir=session_dir,
            artifact_dir=artifact_dir,
            raw_message=raw_message,
            initiator=initiator,
        )
        self._write_json(session_dir / "session.json", session.to_dict())
        artifact_paths = {
            "workflow_summary": str(self.workflow_summary_path(session.session_id)),
        }
        artifact_paths.update(self._write_acceptance_contract_artifacts(session, contract))
        self.save_workflow_summary(
            session,
            WorkflowSummary(
                session_id=session.session_id,
                runtime_mode=runtime_mode,
                current_state="Intake",
                current_stage="Intake",
                artifact_paths=artifact_paths,
            ),
        )
        session_path = session_dir / "session.json"
        payload = json.loads(session_path.read_text())
        if contract is not None and contract.has_constraints():
            payload["acceptance_contract"] = contract.to_dict()
        self._write_json(session_path, payload)
        self.record_event(
            session.session_id,
            kind="session_created",
            stage="Intake",
            state="Intake",
            actor="runtime",
            status="ready",
            message=f"Session created for request: {request.strip()}",
        )
        return session

    def record_stage(
        self,
        session: SessionRecord,
        output: StageOutput,
        *,
        round_index: int = 1,
    ) -> StageRecord:
        artifact_path = session.artifact_dir / output.artifact_name
        supplemental_artifact_paths: dict[str, str] = {}

        artifact_path.write_text(output.artifact_content)
        for artifact_name, artifact_content in output.supplemental_artifacts.items():
            safe_name = Path(artifact_name).name
            supplemental_path = session.artifact_dir / safe_name
            supplemental_path.write_text(artifact_content)
            supplemental_artifact_paths[safe_name] = str(supplemental_path)
            supplemental_artifact_paths[Path(safe_name).stem] = str(supplemental_path)

        stage_record = StageRecord(
            stage=output.stage,
            artifact_name=output.artifact_name,
            artifact_path=artifact_path,
            acceptance_status=output.acceptance_status,
            round_index=round_index,
            supplemental_artifact_paths=supplemental_artifact_paths,
        )
        return stage_record

    def save_review(self, session: SessionRecord, content: str) -> Path:
        review_path = session.artifact_dir / "review.md"
        review_path.write_text(content)
        return review_path

    def workflow_summary_path(self, session_id: str) -> Path:
        return self._runtime_session_dir(session_id) / "workflow_summary.json"

    def save_workflow_summary(self, session: SessionRecord, summary: WorkflowSummary) -> Path:
        summary_path = self.workflow_summary_path(session.session_id)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(summary_path, summary.to_dict())
        return summary_path

    def load_session(self, session_id: str) -> SessionRecord:
        session_path = self._session_json_path(session_id)
        if not session_path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        payload = json.loads(session_path.read_text())
        return SessionRecord(
            session_id=payload["session_id"],
            request=payload["request"],
            created_at=payload["created_at"],
            session_dir=Path(payload["session_dir"]),
            artifact_dir=Path(payload["artifact_dir"]),
            raw_message=payload.get("raw_message"),
            initiator=payload.get("initiator", "agent"),
        )

    def load_workflow_summary(self, session_id: str) -> WorkflowSummary:
        summary_path = self.workflow_summary_path(session_id)
        if not summary_path.exists():
            session_path = self._legacy_session_dir(session_id) / "session.json"
            if session_path.exists():
                payload = json.loads(session_path.read_text())
                artifact_paths = payload.get("artifact_paths", {})
                summary_ref = artifact_paths.get("workflow_summary", "") if isinstance(artifact_paths, dict) else ""
                fallback_candidates = []
                if summary_ref:
                    fallback_candidates.append(Path(str(summary_ref)))
                if payload.get("artifact_dir"):
                    fallback_candidates.append(Path(str(payload["artifact_dir"])) / "workflow_summary.json")
                for fallback_path in fallback_candidates:
                    if fallback_path.exists():
                        summary_path = fallback_path
                        break
            if not summary_path.exists():
                raise FileNotFoundError(f"Workflow summary not found for session {session_id}.")

        return self._workflow_summary_from_dict(json.loads(summary_path.read_text()), session_id=session_id)

    def _workflow_summary_from_dict(self, payload: dict[str, object], *, session_id: str) -> WorkflowSummary:
        artifact_paths_value = payload.get("artifact_paths", {})
        artifact_paths = artifact_paths_value if isinstance(artifact_paths_value, dict) else {}
        raw_stage_statuses = payload.get("stage_statuses", {})
        raw_route_required_stages = payload.get("route_required_stages", [])
        raw_route_stage_decisions = payload.get("route_stage_decisions", {})
        raw_model_output_format_stats = payload.get("model_output_format_stats", {})
        raw_provider_model_metadata = payload.get("provider_model_metadata", {})
        stage_statuses = (
            {str(key): str(value) for key, value in raw_stage_statuses.items()}
            if isinstance(raw_stage_statuses, dict)
            else {}
        )
        route_required_stages = (
            [str(stage) for stage in raw_route_required_stages]
            if isinstance(raw_route_required_stages, list)
            else []
        )
        route_stage_decisions = (
            {
                str(stage): {str(key): str(value) for key, value in dict(item).items()}
                for stage, item in raw_route_stage_decisions.items()
                if isinstance(item, dict)
            }
            if isinstance(raw_route_stage_decisions, dict)
            else {}
        )
        model_output_format_stats = (
            {str(key): int(value or 0) for key, value in raw_model_output_format_stats.items()}
            if isinstance(raw_model_output_format_stats, dict)
            else {}
        )
        legacy_status_map = {
            "ProductDefinition": payload.get("prd_status"),
            "Implementation": payload.get("dev_status"),
            "Verification": payload.get("qa_status"),
        }
        for stage, status in legacy_status_map.items():
            if status is not None and stage not in stage_statuses:
                stage_statuses[stage] = str(status)
        return WorkflowSummary(
            session_id=str(payload.get("session_id", session_id)),
            runtime_mode=str(payload.get("runtime_mode", "session_bootstrap")),
            current_state=str(payload.get("current_state", "Intake")),
            current_stage=str(payload.get("current_stage", "Intake")),
            stage_statuses=stage_statuses,
            acceptance_status=str(payload.get("acceptance_status", "pending")),
            human_decision=str(payload.get("human_decision", "pending")),
            verification_round=int(payload.get("verification_round", payload.get("qa_round", 0)) or 0),
            blocked_reason=str(payload.get("blocked_reason", "")),
            artifact_paths={str(key): str(value) for key, value in artifact_paths.items()},
            route_required_stages=route_required_stages,
            route_stage_decisions=route_stage_decisions,
            verification_mode=str(payload.get("verification_mode", "")),
            product_definition_outcome=str(payload.get("product_definition_outcome", "")),
            model_output_format_stats=model_output_format_stats,
            provider_model_metadata=(
                dict(raw_provider_model_metadata) if isinstance(raw_provider_model_metadata, dict) else {}
            ),
        )

    def load_acceptance_contract(self, session_id: str) -> AcceptanceContract | None:
        session = self.load_session(session_id)
        session_path = session.session_dir / "session.json"
        if not session_path.exists():
            return None
        payload = json.loads(session_path.read_text())
        contract_payload = payload.get("acceptance_contract")
        if not isinstance(contract_payload, dict):
            return None
        return AcceptanceContract.from_dict(contract_payload)

    def codex_home_path(self, session_id: str) -> Path:
        return self.load_session(session_id).session_dir / "codex-home"

    def load_codex_exec_state(self, session_id: str) -> dict[str, object]:
        session_path = self._session_json_path(session_id)
        if not session_path.exists():
            return {}
        payload = json.loads(session_path.read_text())
        state = payload.get("codex_exec", {})
        return dict(state) if isinstance(state, dict) else {}

    def save_codex_exec_state(self, session_id: str, state: dict[str, object]) -> None:
        session = self.load_session(session_id)
        session_path = session.session_dir / "session.json"
        payload = json.loads(session_path.read_text()) if session_path.exists() else session.to_dict()
        existing = payload.get("codex_exec", {})
        merged = dict(existing) if isinstance(existing, dict) else {}
        merged.update(state)
        merged["updated_at"] = self._timestamp()
        payload["codex_exec"] = merged
        payload["updated_at"] = merged["updated_at"]
        self._write_json(session_path, payload)

    def record_stage_result(self, session_id: str, result: StageResultEnvelope) -> StageRecord:
        session = self.load_session(session_id)
        round_index = self._next_round_index(session, result.stage)
        output = StageOutput(
            stage=result.stage,
            artifact_name=result.artifact_name,
            artifact_content=result.artifact_content,
            journal=result.journal,
            findings=list(result.findings),
            acceptance_status=result.acceptance_status or None,
            supplemental_artifacts=dict(result.supplemental_artifacts),
            blocked_reason=result.blocked_reason,
        )
        stage_record = self.record_stage(session, output, round_index=round_index)
        self.append_stage_record(
            session=session,
            stage_record=stage_record,
            findings=result.findings,
            acceptance_status=result.acceptance_status or self._current_acceptance_status(session),
        )
        self.record_event(
            session_id,
            kind="stage_result_recorded",
            stage=result.stage,
            state=result.stage,
            actor=result.stage,
            status=result.status or "recorded",
            message=f"{result.stage} bundle recorded with artifact {result.artifact_name}.",
            details={
                "artifact_name": result.artifact_name,
                "acceptance_status": result.acceptance_status,
                "findings_count": len(result.findings),
            },
        )
        return stage_record

    def _cleanup_incomplete_attempts(self, session: SessionRecord, stage: str) -> None:
        """Remove stale attempt dirs that have no stage-results (incomplete execution)."""
        roles_dir = session.session_dir / "roles"
        if not roles_dir.exists():
            return
        stage_dir = _resolve_stage_dir(session.session_dir, stage)
        if stage_dir is None or not stage_dir.exists():
            return
        for attempt_dir in sorted(stage_dir.glob("attempt-*")):
            if not attempt_dir.is_dir():
                continue
            stage_results = attempt_dir / "stage-results"
            if not stage_results.exists() or not list(stage_results.glob("*")):
                import shutil
                shutil.rmtree(attempt_dir, ignore_errors=True)

    def create_stage_run(
        self,
        *,
        session_id: str,
        stage: str,
        contract_id: str,
        required_outputs: list[str],
        required_evidence: list[str],
        worker: str = "",
    ) -> StageRunRecord:
        session = self.load_session(session_id)
        active = self.active_stage_run(session_id, stage=stage)
        if active is not None:
            raise StageRunStateError(
                f"Active stage run already exists for {stage}: {active.run_id} ({active.state})."
            )

        self._cleanup_incomplete_attempts(session, stage)
        attempt = 1 + sum(1 for item in self.stage_runs(session_id) if item.stage == stage)
        timestamp = self._timestamp()
        run = StageRunRecord(
            run_id=f"{stage.lower()}-run-{attempt}",
            session_id=session_id,
            stage=stage,
            state="RUNNING",
            contract_id=contract_id,
            attempt=attempt,
            required_outputs=list(required_outputs),
            required_evidence=list(required_evidence),
            worker=worker,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._save_stage_run(session, run)
        return run

    def submit_stage_run_result(self, run_id: str, result: StageResultEnvelope) -> StageRunRecord:
        run = self._load_stage_run_for_session(result.session_id, run_id)
        if run.state != "RUNNING":
            raise StageRunStateError(f"Stage run {run.run_id} is {run.state}; expected RUNNING.")
        if run.session_id != result.session_id:
            raise StageRunStateError(
                f"Stage result session_id {result.session_id!r} does not match active run session_id {run.session_id!r}."
            )
        if run.stage != result.stage:
            raise StageRunStateError(
                f"Stage result stage {result.stage!r} does not match active run stage {run.stage!r}."
            )
        if run.contract_id != result.contract_id:
            raise StageRunStateError(
                f"Stage result contract_id {result.contract_id!r} does not match active run contract_id {run.contract_id!r}."
            )

        session = self.load_session(run.session_id)
        candidate_artifact_path = self.stage_output_archive_path(
            session,
            run.stage,
            run.attempt,
            result.artifact_name,
        )
        candidate_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_artifact_path.write_text(result.artifact_content)
        supplemental_archive_dir = candidate_artifact_path.parent / "supplemental-artifacts"
        supplemental_artifact_paths: dict[str, str] = {}
        for artifact_name, artifact_content in result.supplemental_artifacts.items():
            safe_name = Path(artifact_name).name
            supplemental_archive = supplemental_archive_dir / safe_name
            supplemental_archive.parent.mkdir(parents=True, exist_ok=True)
            supplemental_archive.write_text(artifact_content)
            supplemental_artifact_paths[safe_name] = str(supplemental_archive)
            supplemental_artifact_paths[Path(safe_name).stem] = str(supplemental_archive)
        stage_result = result.to_dict(include_artifact_content=False, include_supplemental_artifacts=False)
        stage_result["artifact_path"] = str(candidate_artifact_path)
        if supplemental_artifact_paths:
            stage_result["supplemental_artifact_paths"] = supplemental_artifact_paths
        stage_result_path = self.stage_result_path(session, run.stage, run.attempt)
        updated = StageRunRecord(
            run_id=run.run_id,
            session_id=run.session_id,
            stage=run.stage,
            state="SUBMITTED",
            contract_id=run.contract_id,
            attempt=run.attempt,
            required_outputs=list(run.required_outputs),
            required_evidence=list(run.required_evidence),
            worker=run.worker,
            created_at=run.created_at,
            updated_at=self._timestamp(),
            candidate_bundle_path=str(stage_result_path),
            gate_result=run.gate_result,
            blocked_reason=run.blocked_reason,
            artifact_paths=dict(run.artifact_paths),
            stage_result=stage_result,
            required_pass_steps=list(run.required_pass_steps),
            steps=[dict(item) for item in run.steps],
        )
        self._save_stage_run(session, updated)
        return updated

    def load_stage_run_result(self, run: StageRunRecord) -> StageResultEnvelope:
        if run.stage_result:
            return StageResultEnvelope.from_dict(run.stage_result)
        if not run.candidate_bundle_path:
            raise FileNotFoundError(f"Stage run {run.run_id} has no submitted candidate result.")
        payload = json.loads(Path(run.candidate_bundle_path).read_text())
        if isinstance(payload.get("stage_result"), dict):
            payload = payload["stage_result"]
        return StageResultEnvelope.from_dict(payload)

    def _load_stage_run_for_session(self, session_id: str, run_id: str) -> StageRunRecord:
        for run in self.stage_runs(session_id):
            if run.run_id == run_id:
                return run
        raise FileNotFoundError(f"Stage run not found for session {session_id}: {run_id}")

    def update_stage_run(
        self,
        run: StageRunRecord,
        *,
        state: str | None = None,
        gate_result: GateResult | None = None,
        blocked_reason: str | None = None,
        artifact_paths: dict[str, str] | None = None,
        stage_result: dict[str, object] | None = None,
        required_pass_steps: list[str] | None = None,
        steps: list[dict[str, object]] | None = None,
    ) -> StageRunRecord:
        session = self.load_session(run.session_id)
        try:
            base = self._load_stage_run_for_session(run.session_id, run.run_id)
        except FileNotFoundError:
            base = run
        updated = StageRunRecord(
            run_id=base.run_id,
            session_id=base.session_id,
            stage=base.stage,
            state=state or base.state,
            contract_id=base.contract_id,
            attempt=base.attempt,
            required_outputs=list(base.required_outputs),
            required_evidence=list(base.required_evidence),
            worker=base.worker,
            created_at=base.created_at,
            updated_at=self._timestamp(),
            candidate_bundle_path=base.candidate_bundle_path,
            gate_result=gate_result if gate_result is not None else base.gate_result,
            blocked_reason=blocked_reason if blocked_reason is not None else base.blocked_reason,
            artifact_paths=artifact_paths if artifact_paths is not None else dict(base.artifact_paths),
            stage_result=dict(stage_result) if stage_result is not None else dict(base.stage_result),
            required_pass_steps=(
                list(required_pass_steps) if required_pass_steps is not None else list(base.required_pass_steps)
            ),
            steps=[dict(item) for item in steps] if steps is not None else [dict(item) for item in base.steps],
        )
        self._save_stage_run(session, updated)
        return updated

    def update_stage_run_trace(
        self,
        *,
        session_id: str,
        run_id: str,
        required_pass_steps: list[str],
        steps: list[dict[str, object]],
    ) -> StageRunRecord:
        current = self._load_stage_run_for_session(session_id, run_id)
        return self.update_stage_run(
            current,
            required_pass_steps=list(required_pass_steps),
            steps=[dict(item) for item in steps],
        )

    def active_stage_run(self, session_id: str, stage: str | None = None) -> StageRunRecord | None:
        active_runs = [
            run
            for run in self.stage_runs(session_id)
            if run.state in ACTIVE_STAGE_RUN_STATES and (stage is None or run.stage == stage)
        ]
        return active_runs[-1] if active_runs else None

    def latest_stage_run(self, session_id: str, stage: str | None = None) -> StageRunRecord | None:
        runs = [run for run in self.stage_runs(session_id) if stage is None or run.stage == stage]
        return runs[-1] if runs else None

    def load_stage_run(self, run_id: str) -> StageRunRecord:
        session_dirs = list((self.root / "_runtime" / "sessions").glob("*")) + list((self.root / "sessions").glob("*")) + [
            path
            for path in self.root.glob("*")
            if path.is_dir() and (path / "session.json").exists()
        ]
        for session_dir in sorted(session_dirs):
            for run in self._stage_run_records(session_dir):
                if run.run_id == run_id:
                    return run
        raise FileNotFoundError(f"Stage run not found: {run_id}")

    def stage_runs(self, session_id: str) -> list[StageRunRecord]:
        session = self.load_session(session_id)
        records = self._stage_run_records(session.session_dir)
        return sorted(records, key=lambda run: (run.created_at, run.run_id))

    def save_execution_context(self, context) -> Path:
        session = self.load_session(context.session_id)
        context_dir = self._stage_attempt_dir(session, context.stage, context.round_index, "execution-contexts")
        context_dir.mkdir(parents=True, exist_ok=True)
        stage_slug = _stage_slug(context.stage)
        path = context_dir / f"{stage_slug}-input-context.json"
        self._write_json(path, context.to_dict())
        self.record_event(
            context.session_id,
            kind="execution_context_saved",
            stage=context.stage,
            state=context.stage,
            actor="runtime",
            status="saved",
            message=f"Execution context saved for {context.stage}.",
            details={
                "context_id": context.context_id,
                "contract_id": context.contract_id,
                "path": str(path),
            },
        )
        return path

    def latest_execution_context_path(self, session_id: str, stage: str) -> Path | None:
        session = self.load_session(session_id)
        stage_slug = _stage_slug(stage)
        candidates: list[Path] = []
        for slug_candidate in {stage_slug, _LEGACY_SLUGS.get(stage, "")}:
            if not slug_candidate:
                continue
            context_root = session.session_dir / "roles" / slug_candidate
            if context_root.exists():
                candidates.extend(
                    path
                    for path in context_root.glob("attempt-*/execution-contexts/*-input-context.json")
                )
                candidates.extend(
                    path
                    for path in context_root.glob("attempt-*/execution-contexts/*-task-contract.json")
                )
        legacy_context_root = session.session_dir / "execution-contexts" / stage_slug
        candidates.extend(
            path
            for path in legacy_context_root.glob("attempt-*/*-input-context.json")
        )
        legacy_context_dir = session.session_dir / "execution_context"
        prefix = f"{stage.lower()}_round_"
        if legacy_context_dir.exists():
            candidates.extend(
                path
                for path in legacy_context_dir.glob(f"{prefix}*.json")
                if path.name.startswith(prefix)
            )
        if not candidates:
            return None
        return sorted(candidates, key=lambda path: (_round_index_from_context_path(path), str(path)))[-1]

    def load_execution_context(self, session_id: str, stage: str) -> dict[str, object] | None:
        path = self.latest_execution_context_path(session_id, stage)
        if path is None:
            return None
        return json.loads(path.read_text())

    def append_stage_record(
        self,
        *,
        session: SessionRecord,
        stage_record: StageRecord,
        findings: list[Finding],
        acceptance_status: str,
    ) -> None:
        session_path = session.session_dir / "session.json"
        payload = json.loads(session_path.read_text()) if session_path.exists() else session.to_dict()
        existing_records = list(payload.get("stage_records", []))
        existing_findings = list(payload.get("findings", []))
        existing_records.append(stage_record.to_dict())
        existing_findings.extend(finding.to_dict() for finding in findings)
        payload["stage_records"] = existing_records
        payload["findings"] = existing_findings
        payload["acceptance_status"] = acceptance_status
        payload["updated_at"] = self._timestamp()
        self._write_json(session_path, payload)

    def set_human_decision(self, session_id: str, decision: str) -> None:
        session = self.load_session(session_id)
        session_path = session.session_dir / "session.json"
        payload = json.loads(session_path.read_text())
        payload["human_decision"] = decision
        payload["updated_at"] = self._timestamp()
        self._write_json(session_path, payload)
        try:
            summary = self.load_workflow_summary(session_id)
            stage = summary.current_stage
            state = summary.current_state
        except FileNotFoundError:
            stage = ""
            state = ""
        self.record_event(
            session_id,
            kind="human_decision_recorded",
            stage=stage,
            state=state,
            actor="human",
            status=decision,
            message=f"Human decision recorded: {decision}.",
        )

    def update_session(
        self,
        session: SessionRecord,
        *,
        stage_records: list[StageRecord],
        findings: list[Finding],
        acceptance_status: str,
    ) -> None:
        session_path = session.session_dir / "session.json"
        payload = json.loads(session_path.read_text()) if session_path.exists() else session.to_dict()
        payload.update(session.to_dict())
        payload["acceptance_status"] = acceptance_status
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload["stage_records"] = [record.to_dict() for record in stage_records]
        payload["findings"] = [finding.to_dict() for finding in findings]
        self._write_json(session_path, payload)

    def record_feedback(self, session_id: str, finding: Finding) -> Path:
        session_dir = self.load_session(session_id).session_dir
        session_path = session_dir / "session.json"
        if not session_path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        payload = json.loads(session_path.read_text())
        recorded_at = self._timestamp()
        feedback_record = FeedbackRecord(
            session_id=session_id,
            source_stage=finding.source_stage,
            target_stage=finding.target_stage,
            issue=finding.issue,
            severity=finding.severity,
            created_at=recorded_at,
            lesson=finding.lesson,
            proposed_context_update=finding.proposed_context_update,
            proposed_contract_update=finding.proposed_contract_update,
            evidence=finding.evidence,
            evidence_kind=finding.evidence_kind,
            required_evidence=list(finding.required_evidence),
            completion_signal=finding.completion_signal,
        )
        feedback_dir = session_dir / "feedback"
        feedback_dir.mkdir(parents=True, exist_ok=True)
        feedback_path = feedback_dir / f"{recorded_at.replace(':', '-')}.json"
        self._write_json(feedback_path, feedback_record.to_dict())

        payload.setdefault("feedback_records", [])
        payload["feedback_records"].append(str(feedback_path))
        payload["updated_at"] = recorded_at
        self._write_json(session_path, payload)

        self.record_event(
            session_id,
            kind="feedback_recorded",
            stage=finding.source_stage,
            state="Feedback",
            actor="human",
            status=finding.severity,
            message=f"Feedback recorded for {finding.target_stage}: {finding.issue}",
            details={
                "target_stage": finding.target_stage,
                "required_evidence": list(finding.required_evidence),
                "completion_signal": finding.completion_signal,
            },
        )

        self.apply_learning(finding)
        return feedback_path

    def apply_learning(self, finding: Finding) -> None:
        if finding.target_stage not in VALID_ROLE_NAMES:
            return

        learning_dir = self.root / "memory" / finding.target_stage
        learning_dir.mkdir(parents=True, exist_ok=True)
        recorded_at = self._timestamp()
        record_learning_layers(learning_dir=learning_dir, finding=finding, recorded_at=recorded_at)

        if finding.lesson:
            self._append_unique_section(
                learning_dir / "lessons.md",
                "Learned Lessons",
                (
                    f"## {recorded_at}\n"
                    f"- issue: {finding.issue}\n"
                    f"- source: {finding.source_stage}\n"
                    f"- severity: {finding.severity}\n"
                    f"- lesson: {finding.lesson}\n"
                ),
                finding.lesson,
            )

        if finding.proposed_context_update:
            self._append_unique_section(
                learning_dir / "context_patch.md",
                "Context Patches",
                (
                    f"## {recorded_at}\n"
                    f"Constraint: {finding.proposed_context_update}\n"
                    f"Completion signal: {_completion_signal_for_finding(finding)}\n"
                ),
                finding.proposed_context_update,
            )

        if finding.proposed_contract_update:
            self._append_unique_section(
                learning_dir / "contract_patch.md",
                "Contract Patches",
                (
                    f"## {recorded_at}\n"
                    f"Goal: {finding.proposed_contract_update}\n"
                    f"Completion signal: {_completion_signal_for_finding(finding)}\n"
                ),
                finding.proposed_contract_update,
            )

        findings_log = learning_dir / "findings.jsonl"
        with findings_log.open("a") as handle:
            handle.write(json.dumps({"applied_at": recorded_at, **finding.to_dict()}) + "\n")

    def latest_session_id(self) -> str | None:
        candidates = self.session_ids()
        return candidates[-1] if candidates else None

    def session_ids(self) -> list[str]:
        if not self.root.exists():
            return []

        candidates: set[str] = set()
        session_roots = (
            self.root / "_runtime" / "sessions",
            self.root / "sessions",
            self.root,
        )
        for session_root in session_roots:
            if not session_root.exists():
                continue
            for path in session_root.iterdir():
                if path.is_dir() and (path / "session.json").exists():
                    candidates.add(self._session_id_from_session_dir(path))
        return sorted(candidates)

    def read_review(self, session_id: str | None = None) -> str:
        target_session = session_id or self.latest_session_id()
        if not target_session:
            raise FileNotFoundError("No workflow session exists yet.")

        session = self.load_session(target_session)
        review_path = session.artifact_dir / "review.md"
        if not review_path.exists():
            review_path = session.session_dir / "review.md"
        if not review_path.exists():
            raise FileNotFoundError(f"Review not found for session {target_session}.")
        return review_path.read_text()

    def session_events_path(self, session_id: str) -> Path:
        runtime_events_path = self._runtime_session_dir(session_id) / "events.jsonl"
        if runtime_events_path.exists() or not (self._legacy_session_dir(session_id) / "events.jsonl").exists():
            return runtime_events_path
        return self._legacy_session_dir(session_id) / "events.jsonl"

    def record_event(
        self,
        session_id: str,
        *,
        kind: str,
        stage: str,
        state: str,
        actor: str,
        status: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        event = {
            "at": self._timestamp(),
            "session_id": session_id,
            "kind": kind,
            "stage": stage,
            "state": state,
            "actor": actor,
            "status": status,
            "message": message,
            "details": details or {},
        }
        events_path = self.session_events_path(session_id)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("a") as handle:
            handle.write(json.dumps(event) + "\n")
        return event

    def read_session_events(self, session_id: str) -> list[dict[str, object]]:
        events_path = self.session_events_path(session_id)
        if not events_path.exists():
            return []
        return [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]

    def stage_attempt_dir(self, session_id: str, stage: str, attempt: int, category: str) -> Path:
        return self._stage_attempt_dir(self.load_session(session_id), stage, attempt, category)

    def stage_run_state_path(self, session: SessionRecord, stage: str, attempt: int) -> Path:
        stage_slug = _stage_slug(stage)
        return self._stage_attempt_dir(session, stage, attempt, "stage-results") / f"{stage_slug}-run-state.json"

    def stage_result_path(self, session: SessionRecord, stage: str, attempt: int) -> Path:
        stage_slug = _stage_slug(stage)
        return self._stage_attempt_dir(session, stage, attempt, "stage-results") / f"{stage_slug}-stage-result.json"

    def stage_output_archive_path(self, session: SessionRecord, stage: str, attempt: int, artifact_name: str) -> Path:
        stage_slug = _stage_slug(stage)
        return (
            self._stage_attempt_dir(session, stage, attempt, "stage-results")
            / f"{stage_slug}-output-{Path(artifact_name).name}"
        )

    def stage_contract_path(self, session: SessionRecord, stage: str, attempt: int) -> Path:
        stage_slug = _stage_slug(stage)
        return self._stage_attempt_dir(session, stage, attempt, "execution-contexts") / f"{stage_slug}-task-contract.json"

    def stage_prompt_bundle_path(self, session: SessionRecord, stage: str, attempt: int) -> Path:
        stage_slug = _stage_slug(stage)
        return self._stage_attempt_dir(session, stage, attempt, "execution-contexts") / f"{stage_slug}-agent-prompt-bundle.md"

    def stage_output_schema_path(self, session: SessionRecord, stage: str, attempt: int) -> Path:
        """Per-attempt output schema path (legacy). Prefer session_output_schema_path()."""
        stage_slug = _stage_slug(stage)
        return self._stage_attempt_dir(session, stage, attempt, "execution-contexts") / f"{stage_slug}-output-schema.json"

    def session_output_schema_path(self, session: SessionRecord) -> Path:
        """Repo-level output schema path — identical for all sessions, shared across the project."""
        return self.root / "output-schema.json"

    def runtime_trace_path(self, session: SessionRecord, stage: str, attempt: int) -> Path:
        stage_slug = _stage_slug(stage)
        return self._stage_attempt_dir(session, stage, attempt, "stage-results") / f"{stage_slug}-runtime-trace.json"

    def command_stdout_path(self, session: SessionRecord, stage: str, attempt: int) -> Path:
        stage_slug = _stage_slug(stage)
        return self._stage_attempt_dir(session, stage, attempt, "command-outputs") / f"{stage_slug}-command-stdout.txt"

    def command_stderr_path(self, session: SessionRecord, stage: str, attempt: int) -> Path:
        stage_slug = _stage_slug(stage)
        return self._stage_attempt_dir(session, stage, attempt, "command-outputs") / f"{stage_slug}-command-stderr.txt"

    def skill_asset_root(self, session: SessionRecord, stage: str, attempt: int) -> Path:
        return self._stage_attempt_dir(session, stage, attempt, "execution-contexts") / "skills" / ".agent-team" / "skills"

    def _public_session_dir(self, session_id: str) -> Path:
        return self.root / session_id

    def _runtime_session_dir(self, session_id: str) -> Path:
        return self.root / "_runtime" / "sessions" / session_id

    def _legacy_session_dir(self, session_id: str) -> Path:
        return self.root / session_id

    def _session_json_path(self, session_id: str) -> Path:
        runtime_path = self._runtime_session_dir(session_id) / "session.json"
        if runtime_path.exists():
            return runtime_path
        return self._legacy_session_dir(session_id) / "session.json"

    def _stage_attempt_dir(self, session: SessionRecord, stage: str, attempt: int, category: str) -> Path:
        return session.session_dir / "roles" / _stage_slug(stage) / _attempt_dir_name(attempt) / category

    def _stage_run_state_path_for_run_id(self, session: SessionRecord, run_id: str) -> Path:
        path = self._find_stage_run_state_path(session.session_dir, run_id)
        if path is not None:
            return path
        return session.session_dir / "stage_runs" / f"{run_id}.json"

    def _find_stage_run_state_path(self, session_dir: Path, run_id: str) -> Path | None:
        for path in sorted((session_dir / "roles").glob("*/attempt-*/stage-results/*-stage-result.json")):
            try:
                payload = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            if payload.get("run_id") == run_id:
                return path
        for path in sorted((session_dir / "roles").glob("*/attempt-*/stage-results/*-run-state.json")):
            try:
                payload = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            if payload.get("run_id") == run_id:
                return path
        for path in sorted((session_dir / "stage-results").glob("*/attempt-*/*-run-state.json")):
            try:
                payload = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            if payload.get("run_id") == run_id:
                return path
        legacy_path = session_dir / "stage_runs" / f"{run_id}.json"
        if legacy_path.exists():
            return legacy_path
        return None

    def _stage_run_records(self, session_dir: Path) -> list[StageRunRecord]:
        records_by_id: dict[str, StageRunRecord] = {}
        # Per-role files are authoritative; read them first
        for pattern in [
            "*/attempt-*/stage-results/*-stage-result.json",
            "*/attempt-*/stage-results/*-run-state.json",
        ]:
            roles_dir = session_dir / "roles"
            if roles_dir.exists():
                for path in sorted(roles_dir.glob(pattern)):
                    try:
                        run = StageRunRecord.from_dict(json.loads(path.read_text()))
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
                    records_by_id[run.run_id] = run
        # Legacy stage-results dir
        legacy_results = session_dir / "stage-results"
        if legacy_results.exists():
            for path in sorted(legacy_results.glob("*/attempt-*/*-run-state.json")):
                try:
                    run = StageRunRecord.from_dict(json.loads(path.read_text()))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                records_by_id.setdefault(run.run_id, run)
        # Legacy stage_runs dir
        legacy_runs_dir = session_dir / "stage_runs"
        if legacy_runs_dir.exists():
            for path in sorted(legacy_runs_dir.glob("*.json")):
                if "_" in path.stem:
                    continue
                try:
                    run = StageRunRecord.from_dict(json.loads(path.read_text()))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                records_by_id.setdefault(run.run_id, run)
        # session.json refs fill in any remaining gaps (backward compat with old full records)
        session_path = session_dir / "session.json"
        if session_path.exists():
            payload = json.loads(session_path.read_text())
            for item in payload.get("stage_runs", []):
                try:
                    run = StageRunRecord.from_dict(item)
                except (TypeError, ValueError):
                    continue
                records_by_id.setdefault(run.run_id, run)
        return list(records_by_id.values())

    def _session_id_from_session_dir(self, path: Path) -> str:
        return path.name

    def _append_unique_section(self, path: Path, title: str, content: str, marker: str) -> None:
        existing = path.read_text() if path.exists() else f"# {title}\n\n"
        if marker in existing:
            return

        updated = existing.rstrip() + "\n\n" + content.strip() + "\n"
        path.write_text(updated)

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))

    def _save_stage_run(self, session: SessionRecord, run: StageRunRecord) -> None:
        result_path = self.stage_result_path(session, run.stage, run.attempt)
        self._write_json(result_path, run.to_dict())
        legacy_run_state_path = self.stage_run_state_path(session, run.stage, run.attempt)
        if legacy_run_state_path.exists():
            legacy_run_state_path.unlink()

        session_path = session.session_dir / "session.json"
        payload = json.loads(session_path.read_text()) if session_path.exists() else session.to_dict()
        records = [item for item in payload.get("stage_runs", []) if item.get("run_id") != run.run_id]
        records.append({
            "run_id": run.run_id,
            "stage": run.stage,
            "attempt": run.attempt,
            "state": run.state,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "result_path": str(result_path),
        })
        payload["stage_runs"] = records
        payload["updated_at"] = run.updated_at
        self._write_json(session_path, payload)

    def _next_round_index(self, session: SessionRecord, stage: str) -> int:
        session_path = session.session_dir / "session.json"
        if not session_path.exists():
            return 1
        payload = json.loads(session_path.read_text())
        records = payload.get("stage_records", [])
        return 1 + sum(1 for item in records if item.get("stage") == stage)

    def _current_acceptance_status(self, session: SessionRecord) -> str:
        session_path = session.session_dir / "session.json"
        if not session_path.exists():
            return "pending"
        payload = json.loads(session_path.read_text())
        return payload.get("acceptance_status", "pending")

    def session_contract_artifact_paths(self, session: SessionRecord) -> dict[str, str]:
        paths: dict[str, str] = {}
        for key, filename in (
            ("acceptance_contract", "acceptance_contract.json"),
            ("review_completion", "review_completion.json"),
            ("deviation_checklist", "deviation_checklist.md"),
        ):
            path = session.session_dir / filename
            if path.exists():
                paths[key] = str(path)
        return paths

    def _next_session_id(self, request: str) -> str:
        base = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{_slugify(request)}"
        candidate = base
        suffix = 1

        while self._public_session_dir(candidate).exists() or self._runtime_session_dir(candidate).exists():
            suffix += 1
            candidate = f"{base}-{suffix}"

        return candidate

    def _write_acceptance_contract_artifacts(
        self,
        session: SessionRecord,
        contract: AcceptanceContract | None,
    ) -> dict[str, str]:
        if contract is None or not contract.has_constraints():
            return {}

        artifact_paths: dict[str, str] = {}
        contract_path = session.session_dir / "acceptance_contract.json"
        self._write_json(contract_path, contract.to_dict())
        artifact_paths["acceptance_contract"] = str(contract_path)

        if contract.review_method:
            review_completion_path = session.session_dir / "review_completion.json"
            self._write_json(
                review_completion_path,
                {
                    "review_method": contract.review_method,
                    "boundary": contract.boundary,
                    "recursive": contract.recursive,
                    "tolerance_px": contract.tolerance_px,
                    "required_dimensions": contract.required_dimensions,
                    "required_artifacts": contract.required_artifacts,
                    "required_evidence": contract.required_evidence,
                    "acceptance_criteria": contract.acceptance_criteria,
                    "criteria_covered": [],
                    "dimensions_evaluated": [],
                    "evidence_provided": [],
                    "produced_artifacts": [],
                    "unresolved_items": ["Pending review execution."],
                    "completed": False,
                },
            )
            artifact_paths["review_completion"] = str(review_completion_path)

            deviation_checklist_path = session.session_dir / "deviation_checklist.md"
            deviation_checklist_path.write_text("# Deviation Checklist\n\nPending review execution.\n")
            artifact_paths["deviation_checklist"] = str(deviation_checklist_path)

        return artifact_paths

def artifact_name_for_stage(stage: str) -> str:
    return artifact_name_for(stage)


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned[:40] or "session"


def _stage_slug(stage: str) -> str:
    return STAGE_SLUGS.get(stage, stage_slug(stage))


def _attempt_dir_name(attempt: int) -> str:
    return f"attempt-{attempt:03d}"


def _round_index_from_context_path(path: Path) -> int:
    match = re.search(r"attempt-(\d+)", str(path.parent))
    if match:
        return int(match.group(1))
    match = re.search(r"_round_(\d+)\.json$", path.name)
    return int(match.group(1)) if match else 0


def _completion_signal_for_finding(finding: Finding) -> str:
    if finding.completion_signal:
        return finding.completion_signal
    if finding.required_evidence:
        return (
            "Attach "
            + ", ".join(finding.required_evidence)
            + f" evidence showing '{finding.issue}' is closed on the target surface."
        )
    return (
        "The next handoff includes explicit evidence that "
        f"'{finding.issue}' is addressed on the user-visible or verification surface."
    )
