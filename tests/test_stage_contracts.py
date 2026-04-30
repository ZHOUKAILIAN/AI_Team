import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class StageContractTests(unittest.TestCase):
    def test_product_contract_contains_required_outputs_and_forbidden_actions(self) -> None:
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session(
                "Build a harness-first workflow",
                runtime_mode="harness",
            )

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="Product",
            )

        self.assertEqual(contract.stage, "Product")
        self.assertIn("prd.md", contract.required_outputs)
        self.assertIn("must_not_change_stage_order", contract.forbidden_actions)
        self.assertIn("request", contract.input_artifacts)

    def test_product_contract_uses_requirements_approval_language(self) -> None:
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session(
                "Build a harness-first workflow",
                runtime_mode="harness",
            )

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="Product",
            )

        self.assertIn("requirements approval", contract.goal)
        self.assertNotIn("CEO approval", contract.goal)

    def test_qa_contract_requires_independent_evidence(self) -> None:
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session(
                "Build a harness-first workflow",
                runtime_mode="harness",
            )

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="QA",
            )

        self.assertIn("qa_report.md", contract.required_outputs)
        self.assertIn("independent_verification", contract.evidence_requirements)
        self.assertEqual(contract.evidence_specs[0].name, "independent_verification")
        self.assertIn("summary", contract.evidence_specs[0].required_fields)
        self.assertIn("command", contract.evidence_specs[0].allowed_kinds)

    def test_contract_role_context_includes_learned_context_memory_and_skill(self) -> None:
        from agent_team.models import Finding
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session(
                "Build a harness-first workflow",
                runtime_mode="harness",
            )
            store.apply_learning(
                Finding(
                    source_stage="Acceptance",
                    target_stage="Dev",
                    issue="Missing empty-state evidence.",
                    lesson="Preserve empty-state validation in follow-up rounds.",
                    proposed_context_update="Review empty-state behavior before handoff.",
                    proposed_skill_update="Require visible empty-state evidence before reporting success.",
                )
            )

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="Dev",
            )

        self.assertIn("Review empty-state behavior before handoff.", contract.role_context)
        self.assertIn("Preserve empty-state validation in follow-up rounds.", contract.role_context)
        self.assertIn("Require visible empty-state evidence before reporting success.", contract.role_context)

    def test_dev_contract_references_latest_execution_context(self) -> None:
        from agent_team.execution_context import build_stage_execution_context
        from agent_team.models import EvidenceItem, StageResultEnvelope
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session(
                "Build a harness-first workflow",
                runtime_mode="harness",
            )
            product_result = StageResultEnvelope(
                session_id=session.session_id,
                contract_id="product-contract",
                stage="Product",
                status="completed",
                artifact_name="prd.md",
                artifact_content="# Product PRD\n\n## Acceptance Criteria\n- Verify gate.\n",
                journal="# Product Journal\n",
                evidence=[
                    EvidenceItem(
                        name="explicit_acceptance_criteria",
                        kind="report",
                        summary="Acceptance criteria documented.",
                    )
                ],
                summary="Drafted PRD",
            )
            stage_record = store.record_stage_result(session.session_id, product_result)
            summary = store.load_workflow_summary(session.session_id)
            summary.artifact_paths["product"] = str(stage_record.artifact_path)
            store.save_workflow_summary(session, summary)

            initial_contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="Dev",
            )
            context = build_stage_execution_context(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="Dev",
                contract=initial_contract,
            )
            context_path = store.save_execution_context(context)

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="Dev",
            )

        self.assertEqual(contract.input_artifacts["execution_context"], str(context_path))


if __name__ == "__main__":
    unittest.main()
