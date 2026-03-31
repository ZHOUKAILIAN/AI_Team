import unittest


class ReviewTests(unittest.TestCase):
    def test_review_includes_artifact_diff_and_improvement_proposals(self) -> None:
        from ai_company.review import build_session_review

        review = build_session_review(
            stage_artifacts={
                "Product": "scope: create, edit",
                "QA": "scope missing: delete",
            },
            findings=[
                {
                    "source_stage": "QA",
                    "target_stage": "Product",
                    "issue": "Delete flow missing",
                    "severity": "high",
                    "proposed_context_update": "Always expand user actions into CRUD coverage.",
                }
            ],
        )

        self.assertIn("Delete flow missing", review)
        self.assertIn("--- Product", review)
        self.assertIn("proposed_context_update", review)

    def test_review_includes_workflow_status_when_summary_provided(self) -> None:
        from ai_company.models import WorkflowSummary
        from ai_company.review import build_session_review

        review = build_session_review(
            stage_artifacts={
                "Product": "scope: create, edit",
                "QA": "scope missing: delete",
            },
            findings=[],
            workflow_summary=WorkflowSummary(
                session_id="s1",
                current_state="In Progress",
                current_stage="QA",
                prd_status="completed",
                dev_status="completed",
                qa_status="in_progress",
                acceptance_status="pending",
                human_decision="pending",
                qa_round=2,
            ),
        )

        self.assertIn("## Workflow Status", review)
        self.assertIn("current_state: In Progress", review)
        self.assertIn("current_stage: QA", review)
        self.assertIn("prd_status: completed", review)
        self.assertIn("dev_status: completed", review)
        self.assertIn("qa_status: in_progress", review)
        self.assertIn("acceptance_status: pending", review)
        self.assertIn("human_decision: pending", review)
        self.assertIn("qa_round: 2", review)


if __name__ == "__main__":
    unittest.main()
