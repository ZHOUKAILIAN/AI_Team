import unittest


class StageMachineTests(unittest.TestCase):
    def test_route_result_uses_required_stage_order(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="Intake",
            current_stage="Intake",
        )
        result = StageResultEnvelope(
            session_id="session-1",
            stage="Route",
            status="completed",
            artifact_name="route-packet.json",
            artifact_content=(
                '{"affected_layers":["L2"],'
                '"required_stages":["TechnicalDesign","Implementation","Verification","GovernanceReview","Acceptance","SessionHandoff"],'
                '"stage_decisions":{"ProductDefinition":{"decision":"skipped","reason":"no_l1_delta"}},'
                '"verification_mode":"static_only","baseline_sources":[],"red_lines":[],"unresolved_questions":[]}'
            ),
        )

        updated = StageMachine().advance(summary=summary, stage_result=result)

        self.assertEqual(updated.current_state, "TechnicalDesign")
        self.assertEqual(updated.current_stage, "TechnicalDesign")
        self.assertEqual(updated.stage_statuses["ProductDefinition"], "skipped")
        self.assertEqual(updated.verification_mode, "static_only")

    def test_product_definition_result_waits_for_human_approval(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="ProductDefinition",
            current_stage="ProductDefinition",
        )
        result = StageResultEnvelope(
            session_id="session-1",
            stage="ProductDefinition",
            status="completed",
            artifact_name="product-definition-delta.md",
            artifact_content="# Product Definition Delta\n",
        )

        updated = StageMachine().advance(summary=summary, stage_result=result)

        self.assertEqual(updated.current_state, "WaitForProductDefinitionApproval")
        self.assertEqual(updated.current_stage, "ProductDefinition")
        self.assertEqual(updated.stage_statuses["ProductDefinition"], "drafted")
        self.assertEqual(updated.human_decision, "pending")

    def test_product_definition_no_l1_delta_skips_wait_state(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="ProductDefinition",
            current_stage="ProductDefinition",
            route_required_stages=["TechnicalDesign", "Implementation", "Verification"],
        )
        result = StageResultEnvelope(
            session_id="session-1",
            stage="ProductDefinition",
            status="completed",
            artifact_name="product-definition-delta.md",
            artifact_content="# Product Definition Delta\n\n## 非 L1 内容\n- 当前需求没有稳定语义变化。\n",
            product_definition_outcome="no_l1_delta",
        )

        updated = StageMachine().advance(summary=summary, stage_result=result)

        self.assertEqual(updated.current_state, "TechnicalDesign")
        self.assertEqual(updated.current_stage, "TechnicalDesign")
        self.assertEqual(updated.stage_statuses["ProductDefinition"], "skipped")
        self.assertEqual(updated.product_definition_outcome, "no_l1_delta")

    def test_wait_for_product_definition_approval_rejects_plain_advance(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine, StageTransitionError

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="WaitForProductDefinitionApproval",
            current_stage="ProductDefinition",
        )
        result = StageResultEnvelope(
            session_id="session-1",
            stage="ProjectRuntime",
            status="completed",
            artifact_name="project-landing-delta.md",
            artifact_content="# Project Landing Delta\n",
        )

        with self.assertRaises(StageTransitionError):
            StageMachine().advance(summary=summary, stage_result=result)

    def test_human_go_decision_uses_next_required_stage_after_product_definition(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="WaitForProductDefinitionApproval",
            current_stage="ProductDefinition",
            route_required_stages=["ProductDefinition", "TechnicalDesign", "Implementation"],
        )

        updated = StageMachine().apply_human_decision(summary=summary, decision="go")

        self.assertEqual(updated.current_state, "TechnicalDesign")
        self.assertEqual(updated.current_stage, "TechnicalDesign")
        self.assertEqual(updated.stage_statuses["ProductDefinition"], "approved")
        self.assertEqual(updated.human_decision, "go")

    def test_human_go_decision_uses_next_required_stage_after_technical_design(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="WaitForTechnicalDesignApproval",
            current_stage="TechnicalDesign",
            route_required_stages=["TechnicalDesign", "Verification", "Acceptance"],
        )

        updated = StageMachine().apply_human_decision(summary=summary, decision="go")

        self.assertEqual(updated.current_state, "Verification")
        self.assertEqual(updated.current_stage, "Verification")
        self.assertEqual(updated.stage_statuses["TechnicalDesign"], "approved")
        self.assertEqual(updated.human_decision, "go")

    def test_technical_design_omitted_from_route_skips_approval_wait(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="TechnicalDesign",
            current_stage="TechnicalDesign",
            route_required_stages=["Verification"],
        )

        updated = StageMachine().advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="TechnicalDesign",
                status="completed",
                artifact_name="technical-design.md",
                artifact_content="# Technical Design\n",
            ),
        )

        self.assertEqual(updated.current_state, "Verification")
        self.assertEqual(updated.current_stage, "Verification")
        self.assertEqual(updated.stage_statuses["TechnicalDesign"], "completed")

    def test_runtime_walks_through_five_layer_stages(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        machine = StageMachine()
        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="runtime_driver_interactive",
            current_state="WaitForProductDefinitionApproval",
            current_stage="ProductDefinition",
        )

        summary = machine.apply_human_decision(summary=summary, decision="go")
        self.assertEqual(summary.current_state, "ProjectRuntime")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="ProjectRuntime",
                status="completed",
                artifact_name="project-landing-delta.md",
                artifact_content="# Project Landing Delta\n",
            ),
        )
        self.assertEqual(summary.current_state, "TechnicalDesign")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="TechnicalDesign",
                status="completed",
                artifact_name="technical-design.md",
                artifact_content="# Technical Design\n",
            ),
        )
        self.assertEqual(summary.current_state, "WaitForTechnicalDesignApproval")

        summary = machine.apply_human_decision(summary=summary, decision="go")
        self.assertEqual(summary.current_state, "Implementation")
        self.assertEqual(summary.stage_statuses["TechnicalDesign"], "approved")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="Implementation",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
            ),
        )
        self.assertEqual(summary.current_state, "Verification")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="Verification",
                status="completed",
                artifact_name="verification-report.md",
                artifact_content="# Verification Report\n",
            ),
        )
        self.assertEqual(summary.current_state, "GovernanceReview")
        self.assertEqual(summary.stage_statuses["Verification"], "passed")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="GovernanceReview",
                status="completed",
                artifact_name="governance-review.md",
                artifact_content="# Governance Review\n",
            ),
        )
        self.assertEqual(summary.current_state, "Acceptance")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="Acceptance",
                status="completed",
                artifact_name="acceptance-report.md",
                artifact_content="# Acceptance Report\n",
                acceptance_status="recommended_go",
            ),
        )
        self.assertEqual(summary.current_state, "SessionHandoff")
        self.assertEqual(summary.acceptance_status, "recommended_go")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="SessionHandoff",
                status="completed",
                artifact_name="session-handoff.md",
                artifact_content="# Session Handoff\n",
            ),
        )
        self.assertEqual(summary.current_state, "WaitForHumanDecision")
        self.assertEqual(summary.current_stage, "SessionHandoff")
        self.assertEqual(summary.human_decision, "pending")

    def test_governance_review_medium_finding_continues_with_cautions(self) -> None:
        from agent_team.models import Finding, StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="GovernanceReview",
            current_stage="GovernanceReview",
            route_required_stages=["GovernanceReview", "Acceptance"],
        )

        updated = StageMachine().advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="GovernanceReview",
                status="completed",
                artifact_name="governance-review.md",
                artifact_content="# Governance Review\n\n## Non-blocking Findings / Cautions\n- [medium] 记录给后续对齐。\n",
                findings=[
                    Finding(
                        source_stage="GovernanceReview",
                        target_stage="GovernanceReview",
                        issue="记录给后续对齐。",
                        severity="medium",
                        required_evidence=["layer_governance_review"],
                        completion_signal="note_recorded",
                    )
                ],
            ),
        )

        self.assertEqual(updated.current_state, "Acceptance")
        self.assertEqual(updated.stage_statuses["GovernanceReview"], "passed_with_cautions")
        self.assertEqual(updated.blocked_reason, "")

    def test_governance_review_blocking_finding_still_blocks(self) -> None:
        from agent_team.models import Finding, StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="GovernanceReview",
            current_stage="GovernanceReview",
            route_required_stages=["GovernanceReview", "Acceptance"],
        )

        updated = StageMachine().advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="GovernanceReview",
                status="completed",
                artifact_name="governance-review.md",
                artifact_content="# Governance Review\n",
                summary="发现阻塞治理问题。",
                findings=[
                    Finding(
                        source_stage="GovernanceReview",
                        target_stage="Implementation",
                        issue="Implementation 超出当前需求范围。",
                        severity="high",
                        required_evidence=["scope_cleanup"],
                        completion_signal="remove_out_of_scope_files",
                    )
                ],
            ),
        )

        self.assertEqual(updated.current_state, "Blocked")
        self.assertEqual(updated.stage_statuses["GovernanceReview"], "blocked")
        self.assertEqual(updated.blocked_reason, "发现阻塞治理问题。")

    def test_route_required_stages_drive_remaining_runtime_successors(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        machine = StageMachine()
        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="ProjectRuntime",
            current_stage="ProjectRuntime",
            route_required_stages=["ProjectRuntime", "Implementation", "GovernanceReview", "SessionHandoff"],
        )

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="ProjectRuntime",
                status="completed",
                artifact_name="project-landing-delta.md",
                artifact_content="# Project Landing Delta\n",
            ),
        )
        self.assertEqual(summary.current_state, "Implementation")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="Implementation",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
            ),
        )
        self.assertEqual(summary.current_state, "GovernanceReview")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="GovernanceReview",
                status="completed",
                artifact_name="governance-review.md",
                artifact_content="# Governance Review\n",
            ),
        )
        self.assertEqual(summary.current_state, "SessionHandoff")

        summary = machine.advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="SessionHandoff",
                status="completed",
                artifact_name="session-handoff.md",
                artifact_content="# Session Handoff\n",
            ),
        )
        self.assertEqual(summary.current_state, "WaitForHumanDecision")
        self.assertEqual(summary.current_stage, "SessionHandoff")

    def test_verification_pass_uses_next_required_stage_order(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="Verification",
            current_stage="Verification",
            route_required_stages=["Verification", "Acceptance"],
        )

        updated = StageMachine().advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="Verification",
                status="completed",
                artifact_name="verification-report.md",
                artifact_content="# Verification Report\n",
            ),
        )

        self.assertEqual(updated.current_state, "Acceptance")
        self.assertEqual(updated.current_stage, "Acceptance")
        self.assertEqual(updated.stage_statuses["Verification"], "passed")

    def test_acceptance_result_finishes_when_session_handoff_not_required(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="Acceptance",
            current_stage="Acceptance",
            route_required_stages=["Acceptance"],
            acceptance_status="pending",
        )

        updated = StageMachine().advance(
            summary=summary,
            stage_result=StageResultEnvelope(
                session_id="session-1",
                stage="Acceptance",
                status="completed",
                artifact_name="acceptance-report.md",
                artifact_content="# Acceptance Report\n",
                acceptance_status="recommended_go",
            ),
        )

        self.assertEqual(updated.current_state, "Done")
        self.assertEqual(updated.current_stage, "Acceptance")
        self.assertEqual(updated.acceptance_status, "recommended_go")

    def test_verification_findings_route_back_to_implementation(self) -> None:
        from agent_team.models import Finding, StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="Verification",
            current_stage="Verification",
        )
        result = StageResultEnvelope(
            session_id="session-1",
            stage="Verification",
            status="completed",
            artifact_name="verification-report.md",
            artifact_content="# Verification Report\n",
            findings=[Finding(source_stage="Verification", target_stage="Implementation", issue="Regression found.")],
        )

        updated = StageMachine().advance(summary=summary, stage_result=result)

        self.assertEqual(updated.current_state, "Implementation")
        self.assertEqual(updated.current_stage, "Implementation")
        self.assertEqual(updated.stage_statuses["Verification"], "failed")

    def test_human_rework_decision_routes_to_five_layer_target_stage(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="WaitForHumanDecision",
            current_stage="SessionHandoff",
            acceptance_status="recommended_no_go",
        )

        updated = StageMachine().apply_human_decision(
            summary=summary,
            decision="rework",
            target_stage="Implementation",
        )

        self.assertEqual(updated.current_state, "Implementation")
        self.assertEqual(updated.current_stage, "Implementation")
        self.assertEqual(updated.human_decision, "rework")

    def test_acceptance_result_moves_to_session_handoff_before_final_gate(self) -> None:
        from agent_team.models import StageResultEnvelope, WorkflowSummary
        from agent_team.stage_machine import StageMachine

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="Acceptance",
            current_stage="Acceptance",
            human_decision="go",
            acceptance_status="pending",
        )
        result = StageResultEnvelope(
            session_id="session-1",
            stage="Acceptance",
            status="completed",
            artifact_name="acceptance-report.md",
            artifact_content="# Acceptance Report\n\nRecommend go.\n",
            acceptance_status="recommended_go",
        )

        updated = StageMachine().advance(summary=summary, stage_result=result)

        self.assertEqual(updated.current_state, "SessionHandoff")
        self.assertEqual(updated.current_stage, "SessionHandoff")
        self.assertEqual(updated.acceptance_status, "recommended_go")


if __name__ == "__main__":
    unittest.main()
