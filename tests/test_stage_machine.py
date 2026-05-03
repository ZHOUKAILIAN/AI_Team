import unittest


class StageMachineTests(unittest.TestCase):
    def test_product_result_moves_to_wait_for_ceo_approval(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

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
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine, StageTransitionError

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
        from agent_team.models import WorkflowSummary
        from agent_team.stage_machine import StageMachine

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

    def test_interactive_runtime_walks_through_tech_plan_dev_qa_and_acceptance(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        machine = StageMachine()
        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="runtime_driver_interactive",
            current_state="WaitForCEOApproval",
            current_stage="ProductDraft",
        )

        summary = machine.apply_human_decision(summary=summary, decision="go")
        self.assertEqual(summary.current_state, "TechPlan")
        self.assertEqual(summary.current_stage, "TechPlan")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="TechPlan",
                status="completed",
                artifact_name="technical_plan.md",
                artifact_content="# Technical Plan\n",
            ),
        )
        self.assertEqual(summary.current_state, "WaitForTechPlanApproval")

        summary = machine.apply_human_decision(summary=summary, decision="go")
        self.assertEqual(summary.current_state, "Dev")
        self.assertEqual(summary.current_stage, "Dev")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="Dev",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
            ),
        )
        self.assertEqual(summary.current_state, "WaitForDevApproval")

        summary = machine.apply_human_decision(summary=summary, decision="go")
        self.assertEqual(summary.current_state, "QA")
        self.assertEqual(summary.current_stage, "QA")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="QA",
                status="completed",
                artifact_name="qa_report.md",
                artifact_content="# QA Report\n",
            ),
        )
        self.assertEqual(summary.current_state, "WaitForQAApproval")

        summary = machine.apply_human_decision(summary=summary, decision="go")
        self.assertEqual(summary.current_state, "Acceptance")
        self.assertEqual(summary.current_stage, "Acceptance")

    def test_human_rework_decision_routes_to_target_stage(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.stage_machine import StageMachine

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

    def test_acceptance_result_resets_human_decision_for_final_go_no_go(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="Acceptance",
            current_stage="Acceptance",
            prd_status="drafted",
            dev_status="completed",
            qa_status="passed",
            acceptance_status="pending",
            human_decision="go",
            qa_round=1,
        )
        result = StageResultEnvelope(
            session_id="session-1",
            stage="Acceptance",
            status="completed",
            artifact_name="acceptance_report.md",
            artifact_content="# Acceptance Report\n\nRecommend go.\n",
            acceptance_status="recommended_go",
        )

        updated = StageMachine().advance(summary=summary, stage_result=result)

        self.assertEqual(updated.current_state, "WaitForHumanDecision")
        self.assertEqual(updated.current_stage, "Acceptance")
        self.assertEqual(updated.acceptance_status, "recommended_go")
        self.assertEqual(updated.human_decision, "pending")


if __name__ == "__main__":
    unittest.main()
