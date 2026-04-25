import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class ExecutionContextTests(unittest.TestCase):
    def test_build_dev_execution_context_uses_approved_prd_and_contract(self) -> None:
        from ai_company.execution_context import build_stage_execution_context
        from ai_company.models import AcceptanceContract
        from ai_company.stage_contracts import build_stage_contract
        from ai_company.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session(
                "Build a runtime-controlled Dev handoff.",
                contract=AcceptanceContract(
                    acceptance_criteria=["Dev receives approved PRD context before implementation."],
                    required_evidence=["execution_context/dev_round_1.json"],
                ),
                runtime_mode="harness",
            )
            self._record_product_artifact(store, session.session_id)
            contract = build_stage_contract(
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
                contract=contract,
            )

        self.assertEqual(context.stage, "Dev")
        self.assertEqual(context.contract_id, contract.contract_id)
        self.assertIn("Build a runtime-controlled Dev handoff.", context.original_request_summary)
        self.assertIn("Approved Product PRD", context.approved_prd_summary)
        self.assertEqual(context.required_outputs, ["implementation.md"])
        self.assertEqual(context.required_evidence, ["self_verification"])
        self.assertEqual(context.acceptance_matrix[0]["id"], "AC-001")
        self.assertEqual(
            context.acceptance_matrix[0]["criterion"],
            "Dev receives approved PRD context before implementation.",
        )
        self.assertIn("Dev/context.md", context.repo_context_summary)

    def test_build_dev_execution_context_includes_actionable_findings(self) -> None:
        from ai_company.execution_context import build_stage_execution_context
        from ai_company.models import Finding
        from ai_company.stage_contracts import build_stage_contract
        from ai_company.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("Build Dev handoff with findings.", runtime_mode="harness")
            self._record_product_artifact(store, session.session_id)
            store.record_feedback(
                session.session_id,
                Finding(
                    source_stage="QA",
                    target_stage="Dev",
                    issue="Missing empty-state verification.",
                    severity="high",
                    required_evidence=["empty-state test output"],
                    completion_signal="Dev evidence includes empty-state coverage.",
                ),
            )
            contract = build_stage_contract(
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
                contract=contract,
            )

        self.assertEqual(len(context.actionable_findings), 1)
        self.assertEqual(context.actionable_findings[0].issue, "Missing empty-state verification.")
        self.assertEqual(context.actionable_findings[0].target_stage, "Dev")

    def test_state_store_persists_execution_context_by_stage_and_round(self) -> None:
        from ai_company.execution_context import build_stage_execution_context
        from ai_company.stage_contracts import build_stage_contract
        from ai_company.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("Persist Dev handoff.", runtime_mode="harness")
            self._record_product_artifact(store, session.session_id)
            contract = build_stage_contract(
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
                contract=contract,
            )

            path = store.save_execution_context(context)
            loaded = store.load_execution_context(session.session_id, "Dev")

        self.assertEqual(path.name, "dev_round_1.json")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["context_id"], context.context_id)
        self.assertEqual(loaded["stage"], "Dev")

    def _record_product_artifact(self, store, session_id: str) -> None:
        from ai_company.models import EvidenceItem, StageResultEnvelope

        session = store.load_session(session_id)
        result = StageResultEnvelope(
            session_id=session_id,
            contract_id="product-contract",
            stage="Product",
            status="completed",
            artifact_name="prd.md",
            artifact_content=(
                "# Approved Product PRD\n\n"
                "## Summary\n"
                "Build a runtime-controlled Dev handoff.\n\n"
                "## Acceptance Criteria\n"
                "- Dev receives approved PRD context before implementation.\n"
            ),
            journal="# Product Journal\n",
            evidence=[
                EvidenceItem(
                    name="explicit_acceptance_criteria",
                    kind="report",
                    summary="Acceptance criteria documented.",
                )
            ],
            summary="Drafted PRD.",
        )
        stage_record = store.record_stage_result(session_id, result)
        summary = store.load_workflow_summary(session_id)
        summary.artifact_paths["product"] = str(stage_record.artifact_path)
        summary.artifact_paths["prd"] = str(stage_record.artifact_path)
        store.save_workflow_summary(session, summary)


if __name__ == "__main__":
    unittest.main()
