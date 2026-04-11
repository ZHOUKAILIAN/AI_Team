import unittest


class StageMachineTests(unittest.TestCase):
    def test_product_result_moves_to_wait_for_ceo_approval(self) -> None:
        from ai_company.models import StageResultEnvelope, WorkflowSummary
        from ai_company.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="ProductDraft",
            current_stage="Product",
        )
        result = StageResultEnvelope(
            session_id="session-1",
            stage="Product",
            status="completed",
            artifact_name="prd.md",
            artifact_content="# PRD\n\n## Acceptance Criteria\n- Verify the flow.\n",
        )

        updated = StageMachine().advance(summary=summary, stage_result=result)

        self.assertEqual(updated.current_state, "WaitForCEOApproval")
        self.assertEqual(updated.current_stage, "ProductDraft")
        self.assertEqual(updated.prd_status, "drafted")

    def test_wait_for_ceo_approval_rejects_plain_advance(self) -> None:
        from ai_company.models import StageResultEnvelope, WorkflowSummary
        from ai_company.stage_machine import StageMachine, StageTransitionError

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="WaitForCEOApproval",
            current_stage="ProductDraft",
        )
        result = StageResultEnvelope(
            session_id="session-1",
            stage="Dev",
            status="completed",
            artifact_name="implementation.md",
            artifact_content="# Implementation\n",
        )

        with self.assertRaises(StageTransitionError):
            StageMachine().advance(summary=summary, stage_result=result)

    def test_human_go_decision_moves_from_ceo_wait_to_dev(self) -> None:
        from ai_company.models import WorkflowSummary
        from ai_company.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="WaitForCEOApproval",
            current_stage="ProductDraft",
        )

        updated = StageMachine().apply_human_decision(summary=summary, decision="go")

        self.assertEqual(updated.current_state, "Dev")
        self.assertEqual(updated.current_stage, "Dev")
        self.assertEqual(updated.human_decision, "go")

    def test_human_rework_decision_routes_to_target_stage(self) -> None:
        from ai_company.models import WorkflowSummary
        from ai_company.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="WaitForHumanDecision",
            current_stage="Acceptance",
            acceptance_status="recommended_no_go",
        )

        updated = StageMachine().apply_human_decision(
            summary=summary,
            decision="rework",
            target_stage="Dev",
        )

        self.assertEqual(updated.current_state, "Dev")
        self.assertEqual(updated.current_stage, "Dev")
        self.assertEqual(updated.human_decision, "rework")


if __name__ == "__main__":
    unittest.main()
