from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .backend import DeterministicBackend, WorkflowBackend
from .models import AcceptanceContract, Finding, WorkflowResult, WorkflowSummary
from .review_gates import apply_stage_gates
from .review import build_session_review
from .roles import load_role_profiles
from .state import StateStore

DEFAULT_STAGE_ORDER = ("Product", "Dev", "QA", "Acceptance")
DETERMINISTIC_DEMO_MODE = "deterministic_demo"
MAX_REWORK_ROUNDS = 5


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

    def run(self, *, request: str, contract: AcceptanceContract | None = None) -> WorkflowResult:
        if getattr(self.backend, "supports_rework_routing", False):
            return self._run_with_rework(request=request, contract=contract)
        return self._run_linear(request=request, contract=contract)

    def _run_linear(self, *, request: str, contract: AcceptanceContract | None = None) -> WorkflowResult:
        session = self.state_store.create_session(
            request,
            contract=contract,
            runtime_mode=DETERMINISTIC_DEMO_MODE,
        )
        roles = load_role_profiles(self.repo_root, self.state_store.root)
        stage_artifacts: dict[str, str] = {}
        stage_records = []
        findings: list[Finding] = []
        acceptance_status = "pending"
        summary = WorkflowSummary(
            session_id=session.session_id,
            runtime_mode=DETERMINISTIC_DEMO_MODE,
            current_state="In Progress",
            current_stage="Intake",
            artifact_paths={
                "request": str(session.artifact_dir / "request.md"),
                "workflow_summary": str(self.state_store.workflow_summary_path(session.session_id)),
                **self.state_store.session_contract_artifact_paths(session),
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
            output = apply_stage_gates(session=session, contract=contract, output=output)
            stage_artifacts[stage] = output.artifact_content
            stage_record = self.state_store.record_stage(session, output, round_index=1)
            stage_records.append(stage_record)
            summary.artifact_paths[stage.lower()] = str(stage_record.artifact_path)
            summary.artifact_paths.update(stage_record.supplemental_artifact_paths)
            if stage == "Product":
                summary.current_state = "WaitForCEOApproval"
                summary.current_stage = "ProductDraft"
                summary.prd_status = "drafted"
            elif stage == "Dev":
                summary.current_state = "Dev"
                summary.current_stage = "Dev"
                summary.dev_status = "completed"
            elif stage == "QA":
                summary.current_state = "QA"
                summary.current_stage = "QA"
                summary.qa_status = "passed" if not output.findings else "blocked"
                if output.findings:
                    summary.qa_round += 1
            elif stage == "Acceptance" and output.acceptance_status:
                summary.current_state = "WaitForHumanDecision"
                summary.current_stage = "Acceptance"
                summary.acceptance_status = output.acceptance_status
                if output.blocked_reason:
                    summary.blocked_reason = output.blocked_reason
                elif output.acceptance_status == "blocked":
                    summary.blocked_reason = "Deterministic demo runtime surfaced unresolved downstream findings."
            self.state_store.save_workflow_summary(session, summary)

            for finding in output.findings:
                self.state_store.apply_learning(finding)
                findings.append(finding)

            if output.acceptance_status:
                acceptance_status = output.acceptance_status

        if acceptance_status == "pending":
            acceptance_status = "recommended_go" if not findings else "blocked"
        summary.current_state = "WaitForHumanDecision"
        summary.current_stage = "Acceptance"
        summary.acceptance_status = acceptance_status
        if acceptance_status == "blocked" and not summary.blocked_reason:
            summary.blocked_reason = "Deterministic demo runtime ended with unresolved findings."
        self.state_store.save_workflow_summary(session, summary)

        review = build_session_review(
            stage_artifacts=stage_artifacts,
            findings=findings,
            acceptance_status=acceptance_status,
            workflow_summary=summary,
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

    def _run_with_rework(
        self,
        *,
        request: str,
        contract: AcceptanceContract | None = None,
    ) -> WorkflowResult:
        session = self.state_store.create_session(
            request,
            contract=contract,
            runtime_mode=DETERMINISTIC_DEMO_MODE,
        )
        roles = load_role_profiles(self.repo_root, self.state_store.root)
        stage_artifacts: dict[str, str] = {}
        stage_records = []
        active_findings: list[Finding] = []
        acceptance_status = "pending"
        stage_rounds: dict[str, int] = defaultdict(int)
        rework_rounds = 0
        stage = self.stage_order[0]
        summary = WorkflowSummary(
            session_id=session.session_id,
            runtime_mode=DETERMINISTIC_DEMO_MODE,
            current_state="In Progress",
            current_stage="Intake",
            artifact_paths={
                "request": str(session.artifact_dir / "request.md"),
                "workflow_summary": str(self.state_store.workflow_summary_path(session.session_id)),
                **self.state_store.session_contract_artifact_paths(session),
            },
        )

        while stage:
            stage_rounds[stage] += 1
            role = roles[stage]
            output = self.backend.run_stage(
                stage=stage,
                request=request,
                role=role,
                stage_artifacts=stage_artifacts,
                findings=active_findings,
            )
            output = apply_stage_gates(session=session, contract=contract, output=output)
            stage_artifacts[stage] = output.artifact_content
            stage_record = self.state_store.record_stage(
                session,
                output,
                round_index=stage_rounds[stage],
            )
            stage_records.append(stage_record)
            summary.artifact_paths[stage.lower()] = str(stage_record.artifact_path)
            summary.artifact_paths.update(stage_record.supplemental_artifact_paths)

            if stage == "Product":
                summary.current_state = "WaitForCEOApproval"
                summary.current_stage = "ProductDraft"
                summary.prd_status = "drafted"
            elif stage == "Dev":
                summary.current_state = "Dev"
                summary.current_stage = "Dev"
                summary.dev_status = "completed"
            elif stage == "QA":
                summary.current_state = "QA"
                summary.current_stage = "QA"
                summary.qa_round = stage_rounds["QA"]
                summary.qa_status = "passed" if not output.findings else "blocked"
            elif stage == "Acceptance" and output.acceptance_status:
                summary.current_state = "Acceptance"
                summary.current_stage = "Acceptance"
                summary.acceptance_status = output.acceptance_status
                acceptance_status = output.acceptance_status
                if output.blocked_reason:
                    summary.blocked_reason = output.blocked_reason

            self.state_store.save_workflow_summary(session, summary)

            for finding in output.findings:
                self.state_store.apply_learning(finding)

            routed_stage = self._route_stage(output.findings)
            if stage in {"QA", "Acceptance"} and routed_stage in {"Product", "Dev"}:
                rework_rounds += 1
                if rework_rounds > MAX_REWORK_ROUNDS:
                    active_findings = output.findings
                    acceptance_status = "blocked"
                    summary.current_state = "WaitForHumanDecision"
                    summary.current_stage = stage
                    summary.acceptance_status = acceptance_status
                    summary.blocked_reason = (
                        f"Maximum automated rework rounds ({MAX_REWORK_ROUNDS}) reached."
                    )
                    self.state_store.save_workflow_summary(session, summary)
                    break

            if output.findings:
                active_findings = output.findings
            elif stage in {"QA", "Acceptance"}:
                active_findings = []

            stage = self._next_stage(stage=stage, routed_stage=routed_stage)
            if stage is None and acceptance_status == "pending":
                acceptance_status = "recommended_go" if not active_findings else "blocked"

        summary.current_state = "WaitForHumanDecision"
        if acceptance_status != "pending":
            summary.acceptance_status = acceptance_status
        if not summary.current_stage:
            summary.current_stage = "Acceptance"
        self.state_store.save_workflow_summary(session, summary)

        review = build_session_review(
            stage_artifacts=stage_artifacts,
            findings=active_findings,
            acceptance_status=acceptance_status,
            workflow_summary=summary,
        )
        review_path = self.state_store.save_review(session, review)
        self.state_store.update_session(
            session,
            stage_records=stage_records,
            findings=active_findings,
            acceptance_status=acceptance_status,
        )
        return WorkflowResult(
            session_id=session.session_id,
            acceptance_status=acceptance_status,
            review_path=review_path,
            stage_records=stage_records,
            findings=active_findings,
        )

    def _route_stage(self, findings: list[Finding]) -> str | None:
        actionable = [finding for finding in findings if finding.target_stage in self.stage_order]
        if not actionable:
            return None
        ordered = sorted(actionable, key=lambda finding: self.stage_order.index(finding.target_stage))
        return ordered[0].target_stage

    def _next_stage(self, *, stage: str, routed_stage: str | None) -> str | None:
        if stage == "Product":
            return "Dev"
        if stage == "Dev":
            return "QA"
        if stage == "QA":
            return routed_stage or "Acceptance"
        if stage == "Acceptance":
            return routed_stage
        return None
