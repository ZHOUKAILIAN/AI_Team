import unittest


class WorkflowSummaryTests(unittest.TestCase):
    def test_render_workflow_summary_includes_ordered_core_fields_and_paths(self) -> None:
        from agent_team.workflow_summary import WorkflowSummary, render_workflow_summary

        summary = WorkflowSummary(
            session_id="session-123",
            runtime_mode="session_bootstrap",
            current_state="Intake",
            current_stage="Product",
            prd_status="completed",
            artifact_paths={
                "request": "/tmp/request.md",
                "workflow_summary": "/tmp/workflow_summary.md",
                "prd": "/tmp/prd.md",
            },
        )

        rendered = render_workflow_summary(summary)

        self.assertIn("- session_id: session-123", rendered)
        self.assertIn("- runtime_mode: session_bootstrap", rendered)
        self.assertIn("- current_state: Intake", rendered)
        self.assertIn("- prd_status: completed", rendered)
        self.assertIn("## Artifact Paths", rendered)
        self.assertIn("- request: /tmp/request.md", rendered)
        self.assertIn("- workflow_summary: /tmp/workflow_summary.md", rendered)
        self.assertLess(rendered.index("- session_id: session-123"), rendered.index("- current_state: Intake"))
        self.assertLess(rendered.index("- runtime_mode: session_bootstrap"), rendered.index("- current_state: Intake"))
        self.assertLess(rendered.index("- current_state: Intake"), rendered.index("- prd_status: completed"))


if __name__ == "__main__":
    unittest.main()
