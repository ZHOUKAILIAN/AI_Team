from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    AcceptanceContract,
    FeedbackRecord,
    Finding,
    SessionRecord,
    StageResultEnvelope,
    StageOutput,
    StageRecord,
    WorkflowSummary,
)
from .workflow_summary import render_workflow_summary

VALID_ROLE_NAMES = {"Product", "Dev", "QA", "Acceptance", "Ops"}


class StateStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure_layout(self) -> None:
        for directory in (
            self.root,
            self.root / "artifacts",
            self.root / "memory",
            self.root / "sessions",
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
        artifact_dir = self.root / "artifacts" / session_id
        session_dir = self.root / "sessions" / session_id
        stages_dir = session_dir / "stages"

        artifact_dir.mkdir(parents=True, exist_ok=True)
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
        return self.root / "artifacts" / session_id / "workflow_summary.md"

    def save_workflow_summary(self, session: SessionRecord, summary: WorkflowSummary) -> Path:
        summary_path = self.workflow_summary_path(session.session_id)
        summary_path.write_text(render_workflow_summary(summary))
        return summary_path

    def load_session(self, session_id: str) -> SessionRecord:
        session_path = self.root / "sessions" / session_id / "session.json"
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
        return stage_record

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
        session_dir = self.root / "sessions" / session_id
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
        sessions_dir = self.root / "sessions"
        if not sessions_dir.exists():
            return None

        candidates = sorted(path.name for path in sessions_dir.iterdir() if path.is_dir())
        return candidates[-1] if candidates else None

    def read_review(self, session_id: str | None = None) -> str:
        target_session = session_id or self.latest_session_id()
        if not target_session:
            raise FileNotFoundError("No workflow session exists yet.")

        review_path = self.root / "sessions" / target_session / "review.md"
        if not review_path.exists():
            raise FileNotFoundError(f"Review not found for session {target_session}.")
        return review_path.read_text()

    def _append_unique_section(self, path: Path, title: str, content: str, marker: str) -> None:
        existing = path.read_text() if path.exists() else f"# {title}\n\n"
        if marker in existing:
            return

        updated = existing.rstrip() + "\n\n" + content.strip() + "\n"
        path.write_text(updated)

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _write_json(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload, indent=2))

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

        while (self.root / "sessions" / candidate).exists() or (self.root / "artifacts" / candidate).exists():
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
