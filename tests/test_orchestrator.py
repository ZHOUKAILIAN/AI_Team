import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class OrchestratorTests(unittest.TestCase):
    def test_downstream_findings_create_learning_records(self) -> None:
        from ai_company.backend import StaticBackend
        from ai_company.orchestrator import WorkflowOrchestrator
        from ai_company.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            backend = StaticBackend.fixture(
                product_requirements="Users can create a task",
                prd="PRD v1",
                tech_spec="Tech spec v1",
                qa_report="QA found missing delete flow",
                acceptance_report="Rejected because delete flow missing",
                findings=[
                    {
                        "source_stage": "QA",
                        "target_stage": "Product",
                        "issue": "Delete flow missing from PRD",
                        "severity": "high",
                        "lesson": "Enumerate CRUD scope explicitly.",
                        "proposed_context_update": "Always expand user actions into CRUD coverage.",
                    }
                ],
            )

            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=backend,
            ).run(request="Build a task manager")

            learned_memory = (state_root / "memory" / "Product" / "lessons.md").read_text()

            self.assertEqual(result.acceptance_status, "rejected")
            self.assertIn("Enumerate CRUD scope explicitly.", learned_memory)
            self.assertTrue((state_root / "sessions" / result.session_id / "review.md").exists())

    def test_workflow_summary_reflects_progress_and_final_status(self) -> None:
        from ai_company.backend import StaticBackend
        from ai_company.orchestrator import WorkflowOrchestrator
        from ai_company.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            backend = StaticBackend.fixture(
                product_requirements="Users can create a task",
                prd="PRD v1",
                tech_spec="Tech spec v1",
                qa_report="QA found missing delete flow",
                acceptance_report="Rejected because delete flow missing",
                findings=[
                    {
                        "source_stage": "QA",
                        "target_stage": "Product",
                        "issue": "Delete flow missing from PRD",
                        "severity": "high",
                        "lesson": "Enumerate CRUD scope explicitly.",
                        "proposed_context_update": "Always expand user actions into CRUD coverage.",
                    }
                ],
            )

            result = WorkflowOrchestrator(
                repo_root=repo_root,
                state_store=StateStore(state_root),
                backend=backend,
            ).run(request="Build a task manager")

            summary_path = state_root / "artifacts" / result.session_id / "workflow_summary.md"
            summary = summary_path.read_text()

            self.assertIn("- current_state: Completed", summary)
            self.assertIn("- current_stage: Acceptance", summary)
            self.assertIn("- prd_status: completed", summary)
            self.assertIn("- dev_status: completed", summary)
            self.assertIn("- qa_status: completed", summary)
            self.assertIn("- acceptance_status: rejected", summary)


if __name__ == "__main__":
    unittest.main()
