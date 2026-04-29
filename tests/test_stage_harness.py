import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_company.alignment import AlignmentCriterion, AlignmentDraft, save_confirmed_alignment
from ai_company.codex_exec import CodexExecResult
from ai_company.models import StageContract
from ai_company.stage_harness import StageHarness, stage_prompt
from ai_company.tech_plan import TechPlanDraft, save_confirmed_tech_plan


class FakeRunner:
    def __init__(self, last_message: str) -> None:
        self.last_message = last_message
        self.prompts = []

    def run(self, config, prompt):
        self.prompts.append(prompt)
        config.output_last_message.write_text(self.last_message)
        return CodexExecResult(0, "", "", self.last_message)


class StageHarnessTests(unittest.TestCase):
    def test_dev_prompt_includes_worker_specific_requirements(self) -> None:
        prompt = stage_prompt(
            stage="Dev",
            execution_context={"session_id": "s1", "stage": "Dev"},
            contract=StageContract(
                session_id="s1",
                stage="Dev",
                goal="Implement",
                contract_id="abc",
                required_outputs=["implementation.md"],
                evidence_requirements=["self_verification"],
            ),
            confirmed_alignment={"acceptance_criteria": [{"id": "AC1", "criterion": "It works"}]},
            tech_plan={"implementation_steps": ["Write code", "Run tests"]},
            prd_content="# PRD",
        )

        self.assertIn("Dev stage agent", prompt)
        self.assertIn("workspace-write", prompt)
        self.assertIn("Don't gold-plate", prompt)
        self.assertIn("implementation.md", prompt)
        self.assertIn("self_verification", prompt)
        self.assertIn("== SCOPE ==", prompt)
        self.assertIn("== SECURITY ==", prompt)
        self.assertIn("== SELF-VERIFICATION ==", prompt)
        self.assertIn("== BOUNDARY ==", prompt)
        self.assertIn("OWASP top 10", prompt)
        self.assertIn("Never claim \"all tests pass\"", prompt)
        self.assertIn("Do NOT attempt to advance the workflow state machine", prompt)

    def test_qa_prompt_includes_clean_sandbox_and_skepticism(self) -> None:
        prompt = stage_prompt(
            stage="QA",
            execution_context={"session_id": "s1", "stage": "QA"},
            contract=StageContract(session_id="s1", stage="QA", goal="Verify", contract_id="qa"),
            dev_implementation_md="# Implementation",
            dev_changed_files="ai_company/foo.py\n---\ncontent",
        )

        self.assertIn("CLEAN sandbox", prompt)
        self.assertIn("INDEPENDENTLY VERIFY", prompt)
        self.assertIn("Be skeptical", prompt)
        self.assertIn("qa_report.md", prompt)
        self.assertIn("== VERIFICATION PROTOCOL ==", prompt)
        self.assertIn("== INTEGRITY RULES ==", prompt)
        self.assertIn("command injection", prompt)
        self.assertIn("hardcoded secrets", prompt)
        self.assertIn("Do NOT modify the codebase", prompt)
        self.assertIn("\"Tests passed\" without evidence is not acceptable", prompt)

    def test_acceptance_prompt_uses_paper_trail_and_final_recommendation(self) -> None:
        prompt = stage_prompt(
            stage="Acceptance",
            execution_context={"session_id": "s1", "stage": "Acceptance"},
            contract=StageContract(
                session_id="s1",
                stage="Acceptance",
                goal="Accept",
                contract_id="acc",
            ),
            raw_request="Do it",
            prd_content="# PRD",
            dev_implementation_md="# Impl",
            qa_report_content="# QA",
        )

        self.assertIn("full paper trail", prompt)
        self.assertIn("FINAL recommendation", prompt)
        self.assertIn("recommended_go", prompt)
        self.assertIn("acceptance_report.md", prompt)
        self.assertIn("== ASSESSMENT DIMENSIONS ==", prompt)
        self.assertIn("== INTEGRITY RULES ==", prompt)
        self.assertIn("Do not fill the gap with assumptions", prompt)
        self.assertIn("Per-criterion pass/fail/blocked table", prompt)
        self.assertIn("the human decides", prompt)

    def test_run_product_stage_submits_and_verifies_result(self) -> None:
        from ai_company.state import StateStore

        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()
            store = StateStore(Path(temp_dir) / "state")
            alignment = AlignmentDraft(
                requirement_understanding=["Do the thing"],
                acceptance_criteria=[
                    AlignmentCriterion("AC1", "Thing is done", "Inspect PRD")
                ],
                clarifying_questions=[],
            )
            tech_plan = TechPlanDraft(
                approach_summary="Do the thing with minimal changes.",
                affected_modules=["ai_company/example.py"],
                dependencies=[],
                implementation_steps=["Write the PRD"],
                risks=[],
                testing_strategy="Inspect generated PRD.",
                clarifying_questions=[],
            )
            session = store.create_session("Do the thing", raw_message="Do the thing", initiator="human")
            save_confirmed_alignment(session.session_dir, alignment)
            save_confirmed_tech_plan(session.session_dir, tech_plan)
            bundle = {
                "session_id": "model-output-session-id",
                "contract_id": "model-output-contract-id",
                "stage": "Product",
                "status": "completed",
                "artifact_name": "prd.md",
                "artifact_content": "# Product PRD\n\n## Acceptance Criteria\n- Thing is done\n",
                "journal": "# Product Journal\n",
                "findings": [],
                "evidence": [
                    {
                        "name": "explicit_acceptance_criteria",
                        "kind": "report",
                        "summary": "Criteria documented.",
                    }
                ],
                "summary": "Drafted PRD",
            }
            runner = FakeRunner(json.dumps(bundle))
            harness = StageHarness(repo_root=repo_root, state_store=store, codex_runner=runner)

            record = harness.run_stage(session.session_id, "Product")
            summary = store.load_workflow_summary(session.session_id)

        self.assertEqual(record.stage, "Product")
        self.assertEqual(record.state, "PASSED")
        self.assertEqual(summary.current_state, "WaitForCEOApproval")
        self.assertTrue(runner.prompts)


if __name__ == "__main__":
    unittest.main()
