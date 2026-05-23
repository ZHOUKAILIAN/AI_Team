import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class StateTests(unittest.TestCase):
    def test_state_store_persists_acceptance_contract_and_review_templates(self) -> None:
        from agent_team.models import AcceptanceContract
        from agent_team.state import StateStore

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

            contract_path = session.session_dir / "acceptance_contract.json"
            review_completion_path = session.session_dir / "review_completion.json"
            deviation_checklist_path = session.session_dir / "deviation_checklist.md"

            self.assertTrue(contract_path.exists())
            self.assertTrue(review_completion_path.exists())
            self.assertTrue(deviation_checklist_path.exists())
            self.assertIn('"review_method": "figma-restoration-review"', contract_path.read_text())
            self.assertIn('"completed": false', review_completion_path.read_text())
            self.assertIn("Pending review execution", deviation_checklist_path.read_text())

    def test_state_store_initializes_session_and_artifacts(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("demo")

            self.assertTrue((session.session_dir / "session.json").exists())
            self.assertTrue((Path(temp_dir) / session.session_id).exists())
            self.assertFalse((Path(temp_dir) / session.session_id / "session.json").exists())
            self.assertFalse((Path(temp_dir) / "sessions").exists())
            self.assertFalse((Path(temp_dir) / "artifacts").exists())
            workflow_summary = session.session_dir / "workflow_summary.json"
            self.assertTrue(workflow_summary.exists())
            self.assertFalse((Path(temp_dir) / session.session_id / "workflow_summary.md").exists())
            summary = store.load_workflow_summary(session.session_id)
            self.assertEqual(summary.runtime_mode, "session_bootstrap")
            self.assertEqual(summary.current_state, "Intake")
            self.assertEqual(summary.current_stage, "Intake")
            self.assertEqual(summary.stage_statuses, {})
            self.assertEqual(summary.human_decision, "pending")
            self.assertIn("workflow_summary", summary.artifact_paths)

    def test_state_store_restores_route_metadata_from_workflow_summary(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("route metadata")
            summary = WorkflowSummary(
                session_id=session.session_id,
                runtime_mode="harness",
                current_state="Verification",
                current_stage="Verification",
                route_required_stages=["TechnicalDesign", "Implementation", "Verification"],
                route_stage_decisions={"ProductDefinition": {"decision": "skipped", "reason": "no_l1_delta"}},
                verification_mode="static_only",
                verification_profile="service_health",
                product_definition_outcome="no_l1_delta",
            )

            store.save_workflow_summary(session, summary)
            loaded = store.load_workflow_summary(session.session_id)

            self.assertEqual(loaded.route_required_stages, ["TechnicalDesign", "Implementation", "Verification"])
            self.assertEqual(
                loaded.route_stage_decisions,
                {"ProductDefinition": {"decision": "skipped", "reason": "no_l1_delta"}},
            )
            self.assertEqual(loaded.verification_mode, "static_only")
            self.assertEqual(loaded.verification_profile, "service_health")
            self.assertEqual(loaded.product_definition_outcome, "no_l1_delta")

    def test_state_store_persists_codex_exec_resume_state(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("resume codex")

            store.save_codex_exec_state(
                session.session_id,
                {
                    "conversation_id": "019e3d5f-2b95-7e90-9f55-62a892a01234",
                    "codex_home": str(store.codex_home_path(session.session_id)),
                },
            )
            store.save_codex_exec_state(session.session_id, {"last_stage": "Implementation"})
            state = store.load_codex_exec_state(session.session_id)

        self.assertEqual(state["conversation_id"], "019e3d5f-2b95-7e90-9f55-62a892a01234")
        self.assertEqual(state["last_stage"], "Implementation")
        self.assertTrue(str(state["codex_home"]).endswith("/codex-home"))
        self.assertIn("updated_at", state)

    def test_state_store_creates_unique_session_ids_for_same_request(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            first = store.create_session("repeatable request")
            second = store.create_session("repeatable request")

            self.assertNotEqual(first.session_id, second.session_id)

    def test_apply_learning_ignores_unknown_target_stage(self) -> None:
        from agent_team.models import Finding
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root)
            store.apply_learning(
                Finding(
                    source_stage="Verification",
                    target_stage="../../outside",
                    issue="malicious target",
                    lesson="ignore invalid targets",
                )
            )

            self.assertFalse((root / "memory" / ".." / ".." / "outside").exists())

    def test_apply_learning_ignores_ops_as_removed_default_role(self) -> None:
        from agent_team.models import Finding
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root)
            store.apply_learning(
                Finding(
                    source_stage="Acceptance",
                    target_stage="Ops",
                    issue="legacy release note follow-up",
                    lesson="legacy ops learning should not create a default role overlay",
                )
            )

            self.assertFalse((root / "memory" / "Ops").exists())

    def test_apply_learning_writes_standardized_overlay_sections(self) -> None:
        from agent_team.models import Finding
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root)
            store.apply_learning(
                Finding(
                    source_stage="SessionHandoff",
                    target_stage="Implementation",
                    issue="Acceptance found a missing empty-state flow.",
                    severity="high",
                    lesson="Preserve product-visible empty states in regression coverage.",
                    proposed_context_update="Review user-visible empty states before closing implementation.",
                    proposed_contract_update="Require user-visible empty-state evidence before reporting completion.",
                )
            )

            lessons = (root / "memory" / "Implementation" / "lessons.md").read_text()
            context_patch = (root / "memory" / "Implementation" / "context_patch.md").read_text()
            contract_patch = (root / "memory" / "Implementation" / "contract_patch.md").read_text()

            self.assertIn("- source: SessionHandoff", lessons)
            self.assertIn("- severity: high", lessons)
            self.assertIn("- issue: Acceptance found a missing empty-state flow.", lessons)
            self.assertIn("Constraint:", context_patch)
            self.assertIn("Completion signal:", context_patch)
            self.assertIn("Goal:", contract_patch)
            self.assertIn("Completion signal:", contract_patch)

    def test_record_stage_preserves_latest_artifact(self) -> None:
        from agent_team.models import SessionRecord, StageOutput
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            store = StateStore(root)
            session = SessionRecord(
                session_id="demo-session",
                request="demo",
                created_at="2026-04-10T00:00:00Z",
                session_dir=root / "demo-session",
                artifact_dir=root / "demo-session",
            )
            session.session_dir.mkdir(parents=True, exist_ok=True)
            (session.session_dir / "stages").mkdir(parents=True, exist_ok=True)
            session.artifact_dir.mkdir(parents=True, exist_ok=True)

            round_one = store.record_stage(
                session,
                StageOutput(
                    stage="Verification",
                    artifact_name="verification-report.md",
                    artifact_content="round one",
                    journal="journal one",
                ),
                round_index=1,
            )
            round_two = store.record_stage(
                session,
                StageOutput(
                    stage="Verification",
                    artifact_name="verification-report.md",
                    artifact_content="round two",
                    journal="journal two",
                    supplemental_artifacts={"review_completion.json": '{"completed": true}'},
                ),
                round_index=2,
            )

            self.assertIsNone(round_one.archive_path)
            self.assertIsNone(round_two.archive_path)
            self.assertEqual((session.artifact_dir / "verification-report.md").read_text(), "round two")
            self.assertEqual((session.artifact_dir / "review_completion.json").read_text(), '{"completed": true}')
            self.assertIn("review_completion.json", round_two.supplemental_artifact_paths)
            self.assertEqual(round_two.round_index, 2)

    def test_load_role_profiles_reads_context_and_memory(self) -> None:
        from agent_team.roles import load_role_profiles

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir)
            roles = load_role_profiles(repo_root=repo_root, state_root=state_root)

            self.assertIn("ProductDefinition", roles)
            self.assertIn("Implementation", roles)
            self.assertNotIn("TechPlan", roles)
            self.assertIn("ProductDefinition Stage Manual", roles["ProductDefinition"].effective_context_text)

    def test_load_role_profiles_uses_packaged_assets_when_repo_roles_are_missing(self) -> None:
        from agent_team.roles import load_role_profiles

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            temp_root = Path(temp_dir)
            repo_root = temp_root / "empty-repo"
            repo_root.mkdir()
            state_root = temp_root / "state"
            state_root.mkdir()

            roles = load_role_profiles(repo_root=repo_root, state_root=state_root)

            self.assertIn("ProductDefinition", roles)
            self.assertIn("Verification", roles)
            self.assertNotIn("TechPlan", roles)
            self.assertNotIn("Ops", roles)
            self.assertIn("ProductDefinition Stage Manual", roles["ProductDefinition"].effective_context_text)

    def test_artifact_name_for_stage_uses_five_layer_artifacts(self) -> None:
        from agent_team.state import artifact_name_for_stage

        self.assertEqual(artifact_name_for_stage("Implementation"), "implementation.md")
        self.assertEqual(artifact_name_for_stage("Verification"), "verification-report.md")

    def test_stage_run_lifecycle_persists_active_candidate(self) -> None:
        from agent_team.models import StageResultEnvelope
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")

            run = store.create_stage_run(
                session_id=session.session_id,
                stage="ProductDefinition",
                contract_id="contract-product-definition",
                required_outputs=["product-definition-delta.md"],
                required_evidence=["l1_classification"],
                worker="codex",
            )

            self.assertEqual(run.state, "RUNNING")
            self.assertEqual(run.attempt, 1)
            self.assertEqual(store.active_stage_run(session.session_id).run_id, run.run_id)

            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="ProductDefinition",
                status="completed",
                artifact_name="product-definition-delta.md",
                artifact_content="# Product Definition Delta\n\n## L1 Impact\n- Works.\n",
                contract_id="contract-product-definition",
                evidence=[
                    {
                        "name": "l1_classification",
                        "kind": "report",
                        "summary": "Layer 1 impact is classified.",
                    }
                ],
            )
            submitted = store.submit_stage_run_result(run.run_id, result)

            self.assertEqual(submitted.state, "SUBMITTED")
            self.assertTrue(Path(submitted.candidate_bundle_path).exists())
            self.assertEqual(store.active_stage_run(session.session_id, stage="ProductDefinition").state, "SUBMITTED")

    def test_submit_stage_run_result_uses_result_session_when_run_ids_repeat(self) -> None:
        from agent_team.models import StageResultEnvelope
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            first_session = store.create_session("first workflow")
            second_session = store.create_session("second workflow")
            first_run = store.create_stage_run(
                session_id=first_session.session_id,
                stage="ProductDefinition",
                contract_id="first-contract",
                required_outputs=["product-definition-delta.md"],
                required_evidence=["l1_classification"],
            )
            second_run = store.create_stage_run(
                session_id=second_session.session_id,
                stage="ProductDefinition",
                contract_id="second-contract",
                required_outputs=["product-definition-delta.md"],
                required_evidence=["l1_classification"],
            )

            self.assertEqual(first_run.run_id, second_run.run_id)
            submitted = store.submit_stage_run_result(
                second_run.run_id,
                StageResultEnvelope(
                    session_id=second_session.session_id,
                    stage="ProductDefinition",
                    status="completed",
                    artifact_name="product-definition-delta.md",
                    artifact_content="# Product Definition Delta\n\n## L1 Impact\n- Works.\n",
                    contract_id="second-contract",
                    evidence=[
                        {
                            "name": "l1_classification",
                            "kind": "report",
                            "summary": "Layer 1 impact is classified.",
                        }
                    ],
                ),
            )

            self.assertEqual(submitted.session_id, second_session.session_id)
            self.assertEqual(store.active_stage_run(first_session.session_id, stage="ProductDefinition").state, "RUNNING")
            self.assertEqual(store.active_stage_run(second_session.session_id, stage="ProductDefinition").state, "SUBMITTED")


    def test_create_stage_run_blocks_stale_active_run_without_stage_result(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("stale active run")
            first = store.create_stage_run(
                session_id=session.session_id,
                stage="Verification",
                contract_id="contract-1",
                required_outputs=["verification.md"],
                required_evidence=["independent_verification"],
            )

            stale = store.load_stage_run(first.run_id)
            stale_path = store.stage_result_path(session, "Verification", first.attempt)
            payload = stale.to_dict()
            payload["updated_at"] = "2000-01-01T00:00:00+00:00"
            import json
            stale_path.write_text(json.dumps(payload))

            second = store.create_stage_run(
                session_id=session.session_id,
                stage="Verification",
                contract_id="contract-2",
                required_outputs=["verification.md"],
                required_evidence=["independent_verification"],
            )
            first_reloaded = store.load_stage_run(first.run_id)

        self.assertEqual(first_reloaded.state, "BLOCKED")
        self.assertIn("Stale active stage run", first_reloaded.blocked_reason)
        self.assertEqual(second.state, "RUNNING")
        self.assertEqual(second.attempt, 2)

    def test_create_stage_run_rejects_existing_active_run(self) -> None:
        from agent_team.state import StageRunStateError, StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            store.create_stage_run(
                session_id=session.session_id,
                stage="ProductDefinition",
                contract_id="contract-product-definition",
                required_outputs=["product-definition-delta.md"],
                required_evidence=["l1_classification"],
            )

            with self.assertRaises(StageRunStateError):
                store.create_stage_run(
                    session_id=session.session_id,
                    stage="ProductDefinition",
                    contract_id="contract-product-definition",
                    required_outputs=["product-definition-delta.md"],
                    required_evidence=["l1_classification"],
                )

    def test_load_workflow_summary_falls_back_to_artifact_dir(self) -> None:
        from agent_team.models import SessionRecord, WorkflowSummary
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir) / "sessions"
            artifacts_root = Path(temp_dir) / "artifacts"
            store = StateStore(root)
            session_id = "session-with-external-artifacts"
            session_dir = root / session_id
            artifact_dir = artifacts_root / session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            artifact_dir.mkdir(parents=True, exist_ok=True)

            session = SessionRecord(
                session_id=session_id,
                request="demo",
                created_at=datetime.now(timezone.utc).isoformat(),
                session_dir=session_dir,
                artifact_dir=artifact_dir,
            )
            (session_dir / "session.json").write_text(
                """
{
  "session_id": "session-with-external-artifacts",
  "request": "demo",
  "created_at": "2026-04-20T00:00:00+00:00",
  "session_dir": "__SESSION_DIR__",
  "artifact_dir": "__ARTIFACT_DIR__"
}
                """.strip()
                .replace("__SESSION_DIR__", str(session_dir))
                .replace("__ARTIFACT_DIR__", str(artifact_dir))
            )
            store._write_json(
                artifact_dir / "workflow_summary.json",
                WorkflowSummary(
                    session_id=session_id,
                    runtime_mode="session_bootstrap",
                    current_state="WaitForHumanDecision",
                    current_stage="Acceptance",
                    acceptance_status="recommended_go",
                    artifact_paths={"workflow_summary": str(artifact_dir / "workflow_summary.json")},
                ).to_dict(),
            )

            summary = store.load_workflow_summary(session_id)

            self.assertEqual(summary.current_state, "WaitForHumanDecision")
            self.assertEqual(summary.current_stage, "Acceptance")
            self.assertEqual(summary.acceptance_status, "recommended_go")
            self.assertEqual(
                summary.artifact_paths["workflow_summary"],
                str(artifact_dir / "workflow_summary.json"),
            )


if __name__ == "__main__":
    unittest.main()
