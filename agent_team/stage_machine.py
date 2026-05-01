from __future__ import annotations

from dataclasses import replace

from .models import StageResultEnvelope, WorkflowSummary


VALID_REWORK_TARGETS = {"Product", "Dev"}


class StageTransitionError(ValueError):
    pass


class StageMachine:
    def advance(self, *, summary: WorkflowSummary, stage_result: StageResultEnvelope) -> WorkflowSummary:
        if summary.session_id != stage_result.session_id:
            raise StageTransitionError("Stage result session_id does not match workflow summary.")
        if summary.current_state in {"WaitForCEOApproval", "WaitForHumanDecision"}:
            raise StageTransitionError(
                f"Cannot advance from {summary.current_state} without an explicit human decision."
            )
        if stage_result.status == "blocked":
            return replace(
                summary,
                current_state="Blocked",
                current_stage=stage_result.stage,
                blocked_reason=stage_result.summary or stage_result.blocked_reason or "Stage result is blocked.",
            )

        if stage_result.stage == "Product":
            return replace(
                summary,
                current_state="WaitForCEOApproval",
                current_stage="ProductDraft",
                prd_status="drafted",
            )
        if stage_result.stage == "Dev":
            return replace(
                summary,
                current_state="QA",
                current_stage="QA",
                dev_status="completed",
            )
        if stage_result.stage == "QA":
            next_qa_round = summary.qa_round + 1
            if stage_result.status == "failed" or stage_result.findings:
                return replace(
                    summary,
                    current_state="Dev",
                    current_stage="Dev",
                    qa_status="failed",
                    qa_round=next_qa_round,
                )
            return replace(
                summary,
                current_state="Acceptance",
                current_stage="Acceptance",
                qa_status="passed",
                qa_round=next_qa_round,
            )
        if stage_result.stage == "Acceptance":
            acceptance_status = stage_result.acceptance_status or (
                "blocked" if stage_result.findings else "recommended_go"
            )
            if acceptance_status == "blocked":
                return replace(
                    summary,
                    current_state="Blocked",
                    current_stage="Acceptance",
                    acceptance_status=acceptance_status,
                    blocked_reason=stage_result.summary or "Acceptance result is blocked.",
                )
            return replace(
                summary,
                current_state="WaitForHumanDecision",
                current_stage="Acceptance",
                acceptance_status=acceptance_status,
                human_decision="pending",
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

        if summary.current_state == "WaitForCEOApproval":
            if normalized == "go":
                return replace(
                    summary,
                    current_state="Dev",
                    current_stage="Dev",
                    human_decision=normalized,
                )
            if normalized == "rework":
                return replace(
                    summary,
                    current_state="ProductDraft",
                    current_stage="Product",
                    human_decision=normalized,
                )
            return replace(
                summary,
                current_state="Done",
                current_stage="ProductDraft",
                human_decision=normalized,
            )

        if summary.current_state == "WaitForHumanDecision":
            if normalized in {"go", "no-go"}:
                return replace(
                    summary,
                    current_state="Done",
                    current_stage="Acceptance",
                    human_decision=normalized,
                )
            target = target_stage or ""
            if target not in VALID_REWORK_TARGETS:
                raise StageTransitionError("Rework decisions require target_stage Product or Dev.")
            return replace(
                summary,
                current_state=target,
                current_stage=target,
                human_decision=normalized,
            )

        raise StageTransitionError(
            f"Human decisions are only valid from wait states, not {summary.current_state}."
        )
