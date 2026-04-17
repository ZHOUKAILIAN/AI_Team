import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class StateTests(unittest.TestCase):
    def test_state_store_persists_acceptance_contract_and_review_templates(self) -> None:
        from ai_company.models import AcceptanceContract
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root)
            session = store.create_session(
                "review a page",
                contract=AcceptanceContract(
                    review_method="figma-restoration-review",
                    boundary="page_root",
                    recursive=True,
                    tolerance_px=0.5,
                    required_dimensions=["Structure", "Geometry", "Style", "Content", "State"],
                    required_artifacts=["deviation_checklist.md", "review_completion.json"],
                    required_evidence=["runtime_screenshot", "overlay_diff", "page_root_recursive_audit"],
                    native_node_policy="miniprogram",
                    allow_host_environment_changes=False,
                    read_only_review=True,
                    acceptance_criteria=[
                        "page-root recursive audit",
                        "geometry deviation <= 0.5px",
                    ],
                ),
            )

            contract_path = root / "artifacts" / session.session_id / "acceptance_contract.json"
            review_completion_path = root / "artifacts" / session.session_id / "review_completion.json"
            deviation_checklist_path = root / "artifacts" / session.session_id / "deviation_checklist.md"

            self.assertTrue(contract_path.exists())
            self.assertTrue(review_completion_path.exists())
            self.assertTrue(deviation_checklist_path.exists())
            self.assertIn('"review_method": "figma-restoration-review"', contract_path.read_text())
            self.assertIn('"completed": false', review_completion_path.read_text())
            self.assertIn("Pending review execution", deviation_checklist_path.read_text())

    def test_state_store_initializes_session_and_artifacts(self) -> None:
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("demo")

            self.assertTrue((Path(temp_dir) / "sessions" / session.session_id / "session.json").exists())
            self.assertTrue((Path(temp_dir) / "artifacts" / session.session_id).exists())
            workflow_summary = Path(temp_dir) / "artifacts" / session.session_id / "workflow_summary.md"
            self.assertTrue(workflow_summary.exists())
            summary_text = workflow_summary.read_text()
            self.assertIn("- runtime_mode: session_bootstrap", summary_text)
            self.assertIn("- current_state: Intake", summary_text)
            self.assertIn("- current_stage: Intake", summary_text)
            self.assertIn("- prd_status: pending", summary_text)
            self.assertIn("- human_decision: pending", summary_text)
            self.assertIn("- request:", summary_text)
            self.assertIn("- workflow_summary:", summary_text)

    def test_state_store_creates_unique_session_ids_for_same_request(self) -> None:
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            first = store.create_session("repeatable request")
            second = store.create_session("repeatable request")

            self.assertNotEqual(first.session_id, second.session_id)

    def test_apply_learning_ignores_unknown_target_stage(self) -> None:
        from ai_company.models import Finding
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root)
            store.apply_learning(
                Finding(
                    source_stage="QA",
                    target_stage="../../outside",
                    issue="malicious target",
                    lesson="ignore invalid targets",
                )
            )

            self.assertFalse((root / "memory" / ".." / ".." / "outside").exists())

    def test_apply_learning_writes_standardized_overlay_sections(self) -> None:
        from ai_company.models import Finding
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root)
            store.apply_learning(
                Finding(
                    source_stage="Acceptance",
                    target_stage="Dev",
                    issue="Acceptance found a missing empty-state flow.",
                    severity="high",
                    lesson="Preserve product-visible empty states in regression coverage.",
                    proposed_context_update="Review user-visible empty states before closing implementation.",
                    proposed_skill_update="Require user-visible empty-state evidence before reporting completion.",
                )
            )

            lessons = (root / "memory" / "Dev" / "lessons.md").read_text()
            context_patch = (root / "memory" / "Dev" / "context_patch.md").read_text()
            skill_patch = (root / "memory" / "Dev" / "skill_patch.md").read_text()

            self.assertIn("- source: Acceptance", lessons)
            self.assertIn("- severity: high", lessons)
            self.assertIn("- issue: Acceptance found a missing empty-state flow.", lessons)
            self.assertIn("Constraint:", context_patch)
            self.assertIn("Completion signal:", context_patch)
            self.assertIn("Goal:", skill_patch)
            self.assertIn("Completion signal:", skill_patch)

    def test_record_stage_preserves_round_archives_and_latest_artifact(self) -> None:
        from ai_company.models import SessionRecord, StageOutput
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root)
            session = SessionRecord(
                session_id="demo-session",
                request="demo",
                created_at="2026-04-10T00:00:00Z",
                session_dir=root / "sessions" / "demo-session",
                artifact_dir=root / "artifacts" / "demo-session",
            )
            session.session_dir.mkdir(parents=True, exist_ok=True)
            (session.session_dir / "stages").mkdir(parents=True, exist_ok=True)
            session.artifact_dir.mkdir(parents=True, exist_ok=True)

            round_one = store.record_stage(
                session,
                StageOutput(
                    stage="QA",
                    artifact_name="qa_report.md",
                    artifact_content="round one",
                    journal="journal one",
                ),
                round_index=1,
            )
            round_two = store.record_stage(
                session,
                StageOutput(
                    stage="QA",
                    artifact_name="qa_report.md",
                    artifact_content="round two",
                    journal="journal two",
                    supplemental_artifacts={"review_completion.json": '{"completed": true}'},
                ),
                round_index=2,
            )

            self.assertTrue(round_one.archive_path.exists())
            self.assertTrue(round_two.archive_path.exists())
            self.assertNotEqual(round_one.archive_path, round_two.archive_path)
            self.assertEqual((session.artifact_dir / "qa_report.md").read_text(), "round two")
            self.assertEqual((session.artifact_dir / "review_completion.json").read_text(), '{"completed": true}')
            self.assertIn("review_completion.json", round_two.supplemental_artifact_paths)
            self.assertEqual(round_two.round_index, 2)

    def test_load_role_profiles_reads_context_and_memory(self) -> None:
        from ai_company.roles import load_role_profiles

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            roles = load_role_profiles(repo_root=repo_root, state_root=state_root)

            self.assertIn("Product", roles)
            self.assertIn("Dev", roles)
            self.assertIn("Product Manager Onboarding Manual", roles["Product"].effective_context_text)
            self.assertIn("Initialized memory system", roles["Product"].effective_memory_text)

    def test_artifact_name_for_dev_stage_is_implementation(self) -> None:
        from ai_company.state import artifact_name_for_stage

        self.assertEqual(artifact_name_for_stage("Dev"), "implementation.md")

    def test_stage_run_lifecycle_persists_active_candidate(self) -> None:
        from ai_company.models import StageResultEnvelope
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")

            run = store.create_stage_run(
                session_id=session.session_id,
                stage="Product",
                contract_id="contract-product",
                required_outputs=["prd.md"],
                required_evidence=["explicit_acceptance_criteria"],
                worker="codex",
            )

            self.assertEqual(run.state, "RUNNING")
            self.assertEqual(run.attempt, 1)
            self.assertEqual(store.active_stage_run(session.session_id).run_id, run.run_id)

            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Product",
                status="completed",
                artifact_name="prd.md",
                artifact_content="# PRD\n\n## Acceptance Criteria\n- Works.\n",
                contract_id="contract-product",
                evidence=[
                    {
                        "name": "explicit_acceptance_criteria",
                        "kind": "report",
                        "summary": "PRD includes explicit acceptance criteria.",
                    }
                ],
            )
            submitted = store.submit_stage_run_result(run.run_id, result)

            self.assertEqual(submitted.state, "SUBMITTED")
            self.assertTrue(Path(submitted.candidate_bundle_path).exists())
            self.assertEqual(store.active_stage_run(session.session_id, stage="Product").state, "SUBMITTED")

    def test_create_stage_run_rejects_existing_active_run(self) -> None:
        from ai_company.state import StageRunStateError, StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            store.create_stage_run(
                session_id=session.session_id,
                stage="Product",
                contract_id="contract-product",
                required_outputs=["prd.md"],
                required_evidence=["explicit_acceptance_criteria"],
            )

            with self.assertRaises(StageRunStateError):
                store.create_stage_run(
                    session_id=session.session_id,
                    stage="Product",
                    contract_id="contract-product",
                    required_outputs=["prd.md"],
                    required_evidence=["explicit_acceptance_criteria"],
                )


if __name__ == "__main__":
    unittest.main()
