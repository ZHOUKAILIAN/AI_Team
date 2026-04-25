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
from .status import render_status_markdown
from .workflow_summary import render_workflow_summary

VALID_ROLE_NAMES = {"Product", "Dev", "QA", "Acceptance", "Ops"}
ACTIVE_STAGE_RUN_STATES = {"READY", "RUNNING", "SUBMITTED", "VERIFYING"}
TERMINAL_STAGE_RUN_STATES = {"PASSED", "FAILED", "BLOCKED"}


class StageRunStateError(ValueError):
    pass


class StateStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure_layout(self) -> None:
        for directory in (
            self.root,
            self.root / "memory",
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        request: str,
        raw_message: str | None = None,
        contract: AcceptanceContract | None = None,
        *,
        runtime_mode: str = "session_bootstrap",
    ) -> SessionRecord:
        self.ensure_layout()
        session_id = self._next_session_id(request)
        session_dir = self.root / session_id
        artifact_dir = session_dir
        stages_dir = session_dir / "stages"

        session_dir.mkdir(parents=True, exist_ok=True)
        stages_dir.mkdir(parents=True, exist_ok=True)

        session = SessionRecord(
            session_id=session_id,
            request=request,
            created_at=datetime.now(timezone.utc).isoformat(),
            session_dir=session_dir,
            artifact_dir=artifact_dir,
            raw_message=raw_message,
        )
        self._write_json(session_dir / "session.json", session.to_dict())
        request_path = artifact_dir / "request.md"
        if raw_message is None:
            request_path.write_text(f"# Workflow Request\n\n{request.strip()}\n")
        else:
            request_path.write_text(
                "# Workflow Request\n\n"
                "## Normalized Request\n\n"
                f"{request.strip()}\n\n"
                "## Raw Intake Message\n\n"
                f"{raw_message}\n"
            )
        artifact_paths = {
            "request": str(request_path),
            "workflow_summary": str(session.artifact_dir / "workflow_summary.md"),
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
        stage_slug = output.stage.lower()
        stages_dir = session.session_dir / "stages"
        artifact_path = session.artifact_dir / output.artifact_name
        archive_path = stages_dir / f"{stage_slug}_round_{round_index}_{output.artifact_name}"
        journal_path = stages_dir / f"{stage_slug}_round_{round_index}_journal.md"
        findings_path = stages_dir / f"{stage_slug}_round_{round_index}_findings.json"
        metadata_path = stages_dir / f"{stage_slug}_round_{round_index}.json"
        supplemental_artifact_paths: dict[str, str] = {}

        artifact_path.write_text(output.artifact_content)
        archive_path.write_text(output.artifact_content)
        journal_path.write_text(output.journal)
        self._write_json(findings_path, [finding.to_dict() for finding in output.findings])
        for artifact_name, artifact_content in output.supplemental_artifacts.items():
            safe_name = Path(artifact_name).name
            supplemental_path = session.artifact_dir / safe_name
            supplemental_archive = stages_dir / f"{stage_slug}_round_{round_index}_{safe_name}"
            supplemental_path.write_text(artifact_content)
            supplemental_archive.write_text(artifact_content)
            supplemental_artifact_paths[safe_name] = str(supplemental_path)

        stage_record = StageRecord(
            stage=output.stage,
            artifact_name=output.artifact_name,
            artifact_path=artifact_path,
            journal_path=journal_path,
            findings_path=findings_path,
            acceptance_status=output.acceptance_status,
            round_index=round_index,
            archive_path=archive_path,
            supplemental_artifact_paths=supplemental_artifact_paths,
        )
        self._write_json(metadata_path, stage_record.to_dict())
        return stage_record

    def save_review(self, session: SessionRecord, content: str) -> Path:
        review_path = session.session_dir / "review.md"
        review_path.write_text(content)
        return review_path

    def workflow_summary_path(self, session_id: str) -> Path:
        return self.root / session_id / "workflow_summary.md"

    def save_workflow_summary(self, session: SessionRecord, summary: WorkflowSummary) -> Path:
        summary_path = self.workflow_summary_path(session.session_id)
        rendered = render_workflow_summary(summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered)
        artifact_summary_path = session.artifact_dir / "workflow_summary.md"
        if artifact_summary_path != summary_path:
            artifact_summary_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_summary_path.write_text(rendered)
        self._write_status_markdown(summary)
        return summary_path

    def load_session(self, session_id: str) -> SessionRecord:
        session_path = self.root / session_id / "session.json"
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
        )

    def load_workflow_summary(self, session_id: str) -> WorkflowSummary:
        summary_path = self.workflow_summary_path(session_id)
        if not summary_path.exists():
            session_path = self.root / session_id / "session.json"
            if session_path.exists():
                payload = json.loads(session_path.read_text())
                fallback_path = Path(payload.get("artifact_dir", "")) / "workflow_summary.md"
                if fallback_path.exists():
                    summary_path = fallback_path
            if not summary_path.exists():
                raise FileNotFoundError(f"Workflow summary not found for session {session_id}.")

        payload: dict[str, str] = {}
        artifact_paths: dict[str, str] = {}
        in_artifacts = False
        for raw_line in summary_path.read_text().splitlines():
            if raw_line.strip() == "## Artifact Paths":
                in_artifacts = True
                continue
            if not raw_line.startswith("- "):
                continue
            key, _, value = raw_line[2:].partition(": ")
            if in_artifacts:
                artifact_paths[key] = value
            else:
                payload[key] = value

        return WorkflowSummary(
            session_id=payload.get("session_id", session_id),
            runtime_mode=payload.get("runtime_mode", "session_bootstrap"),
            current_state=payload.get("current_state", "Intake"),
            current_stage=payload.get("current_stage", "Intake"),
            prd_status=payload.get("prd_status", "pending"),
            dev_status=payload.get("dev_status", "pending"),
            qa_status=payload.get("qa_status", "pending"),
            acceptance_status=payload.get("acceptance_status", "pending"),
            human_decision=payload.get("human_decision", "pending"),
            qa_round=int(payload.get("qa_round", "0") or 0),
            blocked_reason=payload.get("blocked_reason", ""),
            artifact_paths=artifact_paths,
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
        run = self.load_stage_run(run_id)
        if run.state != "RUNNING":
            raise StageRunStateError(f"Stage run {run.run_id} is {run.state}; expected RUNNING.")
        if run.session_id != result.session_id:
            raise StageRunStateError("Stage result session_id does not match active run.")
        if run.stage != result.stage:
            raise StageRunStateError("Stage result stage does not match active run.")
        if run.contract_id != result.contract_id:
            raise StageRunStateError("Stage result contract_id does not match active run.")

        session = self.load_session(run.session_id)
        candidate_path = self._stage_runs_dir(session) / f"{run.run_id}_candidate.json"
        self._write_json(candidate_path, result.to_dict())
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
            candidate_bundle_path=str(candidate_path),
            gate_result=run.gate_result,
            blocked_reason=run.blocked_reason,
            artifact_paths=dict(run.artifact_paths),
        )
        self._save_stage_run(session, updated)
        return updated

    def update_stage_run(
        self,
        run: StageRunRecord,
        *,
        state: str | None = None,
        gate_result: GateResult | None = None,
        blocked_reason: str | None = None,
        artifact_paths: dict[str, str] | None = None,
    ) -> StageRunRecord:
        session = self.load_session(run.session_id)
        updated = StageRunRecord(
            run_id=run.run_id,
            session_id=run.session_id,
            stage=run.stage,
            state=state or run.state,
            contract_id=run.contract_id,
            attempt=run.attempt,
            required_outputs=list(run.required_outputs),
            required_evidence=list(run.required_evidence),
            worker=run.worker,
            created_at=run.created_at,
            updated_at=self._timestamp(),
            candidate_bundle_path=run.candidate_bundle_path,
            gate_result=gate_result if gate_result is not None else run.gate_result,
            blocked_reason=blocked_reason if blocked_reason is not None else run.blocked_reason,
            artifact_paths=artifact_paths if artifact_paths is not None else dict(run.artifact_paths),
        )
        self._save_stage_run(session, updated)
        return updated

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
        session_dirs = list((self.root / "sessions").glob("*")) + [
            path
            for path in self.root.glob("*")
            if path.is_dir() and (path / "session.json").exists()
        ]
        for session_dir in sorted(session_dirs):
            path = session_dir / "stage_runs" / f"{run_id}.json"
            if path.exists():
                return StageRunRecord.from_dict(json.loads(path.read_text()))
        raise FileNotFoundError(f"Stage run not found: {run_id}")

    def stage_runs(self, session_id: str) -> list[StageRunRecord]:
        session = self.load_session(session_id)
        runs_dir = self._stage_runs_dir(session)
        if not runs_dir.exists():
            return []
        records = [
            StageRunRecord.from_dict(json.loads(path.read_text()))
            for path in sorted(runs_dir.glob("*.json"))
            if not path.name.endswith("_candidate.json")
        ]
        return sorted(records, key=lambda run: (run.created_at, run.run_id))

    def save_execution_context(self, context) -> Path:
        session = self.load_session(context.session_id)
        context_dir = session.session_dir / "execution_context"
        context_dir.mkdir(parents=True, exist_ok=True)
        path = context_dir / f"{context.stage.lower()}_round_{context.round_index}.json"
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
        context_dir = session.session_dir / "execution_context"
        if not context_dir.exists():
            return None
        prefix = f"{stage.lower()}_round_"
        candidates = [
            path
            for path in context_dir.glob(f"{prefix}*.json")
            if path.name.startswith(prefix)
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda path: (_round_index_from_context_path(path), path.name))[-1]

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
        session_dir = self.root / session_id
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
            proposed_skill_update=finding.proposed_skill_update,
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

        if finding.lesson:
            self._append_unique_section(
                learning_dir / "lessons.md",
                "Learned Lessons",
                (
                    f"## {self._timestamp()}\n"
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
                    f"## {self._timestamp()}\n"
                    f"Constraint: {finding.proposed_context_update}\n"
                    f"Completion signal: {_completion_signal_for_finding(finding)}\n"
                ),
                finding.proposed_context_update,
            )

        if finding.proposed_skill_update:
            self._append_unique_section(
                learning_dir / "skill_patch.md",
                "Skill Patches",
                (
                    f"## {self._timestamp()}\n"
                    f"Goal: {finding.proposed_skill_update}\n"
                    f"Completion signal: {_completion_signal_for_finding(finding)}\n"
                ),
                finding.proposed_skill_update,
            )

        findings_log = learning_dir / "findings.jsonl"
        with findings_log.open("a") as handle:
            handle.write(json.dumps({"applied_at": self._timestamp(), **finding.to_dict()}) + "\n")

    def latest_session_id(self) -> str | None:
        if not self.root.exists():
            return None

        candidates = sorted(
            path.name
            for path in self.root.iterdir()
            if path.is_dir() and (path / "session.json").exists()
        )
        return candidates[-1] if candidates else None

    def read_review(self, session_id: str | None = None) -> str:
        target_session = session_id or self.latest_session_id()
        if not target_session:
            raise FileNotFoundError("No workflow session exists yet.")

        review_path = self.root / target_session / "review.md"
        if not review_path.exists():
            raise FileNotFoundError(f"Review not found for session {target_session}.")
        return review_path.read_text()

    def session_events_path(self, session_id: str) -> Path:
        return self.root / session_id / "events.jsonl"

    def status_path(self, session_id: str) -> Path:
        return self.root / session_id / "status.md"

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
        try:
            summary = self.load_workflow_summary(session_id)
        except FileNotFoundError:
            return event
        self._write_status_markdown(summary)
        return event

    def read_session_events(self, session_id: str) -> list[dict[str, object]]:
        events_path = self.session_events_path(session_id)
        if not events_path.exists():
            return []
        return [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]

    def _write_status_markdown(self, summary: WorkflowSummary) -> Path:
        status_path = self.status_path(summary.session_id)
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(
            render_status_markdown(
                summary=summary,
                state_root=self.root,
                events=self.read_session_events(summary.session_id),
            )
        )
        return status_path

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

    def _stage_runs_dir(self, session: SessionRecord) -> Path:
        return session.session_dir / "stage_runs"

    def _save_stage_run(self, session: SessionRecord, run: StageRunRecord) -> None:
        runs_dir = self._stage_runs_dir(session)
        runs_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(runs_dir / f"{run.run_id}.json", run.to_dict())

        session_path = session.session_dir / "session.json"
        payload = json.loads(session_path.read_text()) if session_path.exists() else session.to_dict()
        records = [item for item in payload.get("stage_runs", []) if item.get("run_id") != run.run_id]
        records.append(run.to_dict())
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
            path = session.artifact_dir / filename
            if path.exists():
                paths[key] = str(path)
        return paths

    def _next_session_id(self, request: str) -> str:
        base = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{_slugify(request)}"
        candidate = base
        suffix = 1

        while (self.root / candidate).exists():
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
        contract_path = session.artifact_dir / "acceptance_contract.json"
        self._write_json(contract_path, contract.to_dict())
        artifact_paths["acceptance_contract"] = str(contract_path)

        if contract.review_method:
            review_completion_path = session.artifact_dir / "review_completion.json"
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

            deviation_checklist_path = session.artifact_dir / "deviation_checklist.md"
            deviation_checklist_path.write_text("# Deviation Checklist\n\nPending review execution.\n")
            artifact_paths["deviation_checklist"] = str(deviation_checklist_path)

        return artifact_paths


def artifact_name_for_stage(stage: str) -> str:
    return {
        "Product": "prd.md",
        "Dev": "implementation.md",
        "QA": "qa_report.md",
        "Acceptance": "acceptance_report.md",
        "Ops": "release_notes.md",
    }.get(stage, f"{stage.lower()}.md")


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned[:40] or "session"


def _round_index_from_context_path(path: Path) -> int:
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
