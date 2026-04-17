import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class StageContractTests(unittest.TestCase):
    def test_product_contract_contains_required_outputs_and_forbidden_actions(self) -> None:
        from ai_company.stage_contracts import build_stage_contract
        from ai_company.state import StateStore

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

    def test_qa_contract_requires_independent_evidence(self) -> None:
        from ai_company.stage_contracts import build_stage_contract
        from ai_company.state import StateStore

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
        from ai_company.models import Finding
        from ai_company.stage_contracts import build_stage_contract
        from ai_company.state import StateStore

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


if __name__ == "__main__":
    unittest.main()
