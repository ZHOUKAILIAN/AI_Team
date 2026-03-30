from __future__ import annotations

from pathlib import Path

from .backend import DeterministicBackend, WorkflowBackend
from .models import Finding, WorkflowResult, WorkflowSummary
from .review import build_session_review
from .roles import load_role_profiles
from .state import StateStore

DEFAULT_STAGE_ORDER = ("Product", "Dev", "QA", "Acceptance")


class WorkflowOrchestrator:
    def __init__(
        self,
        *,
        repo_root: Path,
        state_store: StateStore,
        backend: WorkflowBackend | None = None,
        stage_order: tuple[str, ...] = DEFAULT_STAGE_ORDER,
    ) -> None:
        self.repo_root = repo_root
        self.state_store = state_store
        self.backend = backend or DeterministicBackend()
        self.stage_order = stage_order

    def run(self, *, request: str) -> WorkflowResult:
        session = self.state_store.create_session(request)
        roles = load_role_profiles(self.repo_root, self.state_store.root)
        stage_artifacts: dict[str, str] = {}
        stage_records = []
        findings: list[Finding] = []
        acceptance_status = "pending"
        summary = WorkflowSummary(
            session_id=session.session_id,
            current_state="In Progress",
            current_stage="Intake",
            artifact_paths={
                "request": str(session.artifact_dir / "request.md"),
                "workflow_summary": str(self.state_store.workflow_summary_path(session.session_id)),
            },
        )

        for stage in self.stage_order:
            role = roles[stage]
            output = self.backend.run_stage(
                stage=stage,
                request=request,
                role=role,
                stage_artifacts=stage_artifacts,
                findings=findings,
            )
            stage_artifacts[stage] = output.artifact_content
            stage_record = self.state_store.record_stage(session, output)
            stage_records.append(stage_record)
            summary.current_stage = stage
            summary.artifact_paths[stage.lower()] = str(stage_record.artifact_path)
            if stage == "Product":
                summary.prd_status = "completed"
            elif stage == "Dev":
                summary.dev_status = "completed"
            elif stage == "QA":
                summary.qa_status = "completed"
            elif stage == "Acceptance" and output.acceptance_status:
                summary.acceptance_status = output.acceptance_status
            self.state_store.save_workflow_summary(session, summary)

            for finding in output.findings:
                self.state_store.apply_learning(finding)
                findings.append(finding)

            if output.acceptance_status:
                acceptance_status = output.acceptance_status

        if acceptance_status == "pending":
            acceptance_status = "accepted" if not findings else "rejected"
        summary.current_state = "Completed"
        summary.acceptance_status = acceptance_status
        self.state_store.save_workflow_summary(session, summary)

        review = build_session_review(
            stage_artifacts=stage_artifacts,
            findings=findings,
            acceptance_status=acceptance_status,
        )
        review_path = self.state_store.save_review(session, review)
        self.state_store.update_session(
            session,
            stage_records=stage_records,
            findings=findings,
            acceptance_status=acceptance_status,
        )
        return WorkflowResult(
            session_id=session.session_id,
            acceptance_status=acceptance_status,
            review_path=review_path,
            stage_records=stage_records,
            findings=findings,
        )
