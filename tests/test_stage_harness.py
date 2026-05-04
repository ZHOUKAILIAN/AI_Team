import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_team.alignment import AlignmentCriterion, AlignmentDraft, save_confirmed_alignment
from agent_team.executor import ExecutorResult
from agent_team.models import StageContract
from agent_team.skill_registry import Skill
from agent_team.stage_harness import StageHarness, stage_prompt
from agent_team.tech_plan import TechPlanDraft, save_confirmed_tech_plan


class FakeExecutor:
    def __init__(self, last_message: str) -> None:
        self.last_message = last_message
        self.prompts = []

    def execute(self, *, prompt, output_dir, stage):
        self.prompts.append(prompt)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{stage.lower()}_last_message.json").write_text(self.last_message)
        return ExecutorResult(0, "", "", self.last_message)


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
                evidence_requirements=["self_code_review", "self_verification"],
            ),
            confirmed_alignment={"acceptance_criteria": [{"id": "AC1", "criterion": "It works"}]},
            tech_plan={"implementation_steps": ["Write code", "Run tests"]},
            prd_content="# PRD",
        )

        self.assertIn("Dev stage agent", prompt)
        self.assertIn("workspace-write", prompt)
        self.assertIn("Don't gold-plate", prompt)
        self.assertIn("implementation.md", prompt)
        self.assertIn("self_code_review", prompt)
        self.assertIn("self_verification", prompt)
        self.assertIn("== UNIVERSAL PROTECTION ==", prompt)
        self.assertIn("== SCOPE ==", prompt)
        self.assertIn("== SECURITY ==", prompt)
        self.assertIn("== SELF CODE REVIEW ==", prompt)
        self.assertIn("== SELF-VERIFICATION ==", prompt)
        self.assertIn("== STAGE CONTEXT ==", prompt)
        self.assertIn("== BOUNDARY ==", prompt)
        self.assertIn("OWASP top 10", prompt)
        self.assertIn("Self Code Review", prompt)
        self.assertIn("Never claim \"all tests pass\"", prompt)
        self.assertIn("Do NOT attempt to advance the workflow state machine", prompt)

    def test_techplan_prompt_includes_worker_specific_requirements(self) -> None:
        prompt = stage_prompt(
            stage="TechPlan",
            execution_context={"session_id": "s1", "stage": "TechPlan"},
            contract=StageContract(
                session_id="s1",
                stage="TechPlan",
                goal="Plan",
                contract_id="tech",
                required_outputs=["technical_plan.md"],
                evidence_requirements=["implementation_plan"],
            ),
            prd_content="# PRD\n\n## Acceptance Criteria\n- It works",
        )

        self.assertIn("TechPlan stage agent", prompt)
        self.assertIn("technical_plan.md", prompt)
        self.assertIn("implementation_plan", prompt)
        self.assertIn("Do NOT edit repository source code", prompt)
        self.assertIn("Make the plan specific enough for Dev", prompt)
        self.assertIn("=== PRD ===", prompt)

    def test_qa_prompt_includes_clean_sandbox_and_skepticism(self) -> None:
        prompt = stage_prompt(
            stage="QA",
            execution_context={"session_id": "s1", "stage": "QA"},
            contract=StageContract(session_id="s1", stage="QA", goal="Verify", contract_id="qa"),
            dev_implementation_md="# Implementation",
            dev_changed_files="agent_team/foo.py\n---\ncontent",
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

    def test_stage_prompt_injects_enabled_skills_between_role_and_context(self) -> None:
        from agent_team.skill_registry import Skill

        prompt = stage_prompt(
            stage="Dev",
            execution_context={"session_id": "s1", "stage": "Dev"},
            contract=StageContract(session_id="s1", stage="Dev", goal="Implement", contract_id="dev"),
            skills=[
                Skill(
                    name="plan",
                    description="Plan first",
                    content="# Plan\nMake a checklist.",
                    source="builtin",
                    path=Path("SKILL.md"),
                )
            ],
        )

        self.assertLess(prompt.index("== DEV ROLE =="), prompt.index("== ENABLED SKILLS =="))
        self.assertLess(prompt.index("== ENABLED SKILLS =="), prompt.index("== STAGE CONTEXT =="))
        self.assertIn("Make a checklist", prompt)

    def test_dev_prompt_includes_technical_plan_artifact_content(self) -> None:
        prompt = stage_prompt(
            stage="Dev",
            execution_context={"session_id": "s1", "stage": "Dev"},
            contract=StageContract(session_id="s1", stage="Dev", goal="Implement", contract_id="dev"),
            tech_plan={
                "artifact_name": "technical_plan.md",
                "artifact_path": "/tmp/technical_plan.md",
                "artifact_content": "# Technical Plan\n\n- Use the approved TechPlan module path.\n",
            },
        )

        self.assertIn("=== Technical Plan ===", prompt)
        self.assertIn("Use the approved TechPlan module path.", prompt)
        self.assertIn("=== Technical Plan Metadata ===", prompt)
        self.assertIn("technical_plan.md", prompt)

    def test_run_product_stage_submits_and_verifies_result(self) -> None:
        from agent_team.state import StateStore

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
                affected_modules=["agent_team/example.py"],
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
            skill_dir = Path(temp_dir) / "skill" / "cst"
            skill_dir.mkdir(parents=True)
            skill_path = skill_dir / "SKILL.md"
            skill_path.write_text("# CST")
            project_skill_dir = repo_root / "Product" / "skills" / "project-check"
            project_skill_dir.mkdir(parents=True)
            project_skill_path = project_skill_dir / "SKILL.md"
            project_skill_path.write_text("# Project Check")
            executor = FakeExecutor(json.dumps(bundle))
            harness = StageHarness(
                repo_root=repo_root,
                state_store=store,
                executor=executor,
                enabled_skills_by_stage={
                    "Product": [
                        Skill(
                            name="cst",
                            description="Troubleshoot",
                            content="# CST",
                            source="personal",
                            path=skill_path,
                            delivery="sandbox",
                        ),
                        Skill(
                            name="project-check",
                            description="Project guard",
                            content="# Project Check",
                            source="project",
                            path=project_skill_path,
                        )
                    ]
                },
            )

            record = harness.run_stage(session.session_id, "Product")
            summary = store.load_workflow_summary(session.session_id)
            installed_skill = session.session_dir / "exec" / ".agent-team" / "skills" / "cst" / "SKILL.md"
            installed_skill_exists = installed_skill.exists()
            manifest_path = session.session_dir / "stage_runs" / "product-run-1_skill_injection.json"
            manifest_path_exists = manifest_path.exists()
            manifest = json.loads(manifest_path.read_text())
            stage_run_path = session.session_dir / "stage_runs" / "product-run-1.json"
            stage_run = json.loads(stage_run_path.read_text())

        self.assertEqual(record.stage, "Product")
        self.assertEqual(record.state, "PASSED")
        self.assertEqual(summary.current_state, "WaitForCEOApproval")
        self.assertTrue(executor.prompts)
        self.assertTrue(installed_skill_exists)
        self.assertTrue(manifest_path_exists)
        self.assertEqual(summary.artifact_paths["product_skill_injection"], str(manifest_path))
        self.assertEqual(manifest["stage"], "Product")
        self.assertEqual(manifest["run_id"], "product-run-1")
        self.assertEqual(manifest["skill_count"], 2)
        self.assertEqual(
            {(item["name"], item["source"], item["scope"]) for item in manifest["skills"]},
            {("cst", "personal", "global"), ("project-check", "project", "project")},
        )
        self.assertEqual(manifest["skills"][0]["installed_path"], str(installed_skill.parent))
        self.assertEqual(stage_run["artifact_paths"]["product_skill_injection"], str(manifest_path))

    def test_run_dev_stage_uses_runtime_technical_plan_artifact(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()
            store = StateStore(Path(temp_dir) / "state")
            session = store.create_session("Do the thing", raw_message="Do the thing", initiator="human")
            prd_path = session.session_dir / "prd.md"
            tech_plan_path = session.session_dir / "technical_plan.md"
            prd_path.write_text("# Product PRD\n\n## Acceptance Criteria\n- Thing is done.\n")
            tech_plan_path.write_text("# Technical Plan\n\n- Implement via the approved TechPlan steps.\n")
            summary = store.load_workflow_summary(session.session_id)
            summary.artifact_paths["product"] = str(prd_path)
            summary.artifact_paths["prd"] = str(prd_path)
            summary.artifact_paths["techplan"] = str(tech_plan_path)
            summary.artifact_paths["technical_plan"] = str(tech_plan_path)
            store.save_workflow_summary(session, summary)
            bundle = {
                "session_id": "model-output-session-id",
                "contract_id": "model-output-contract-id",
                "stage": "Dev",
                "status": "completed",
                "artifact_name": "implementation.md",
                "artifact_content": "# Implementation\n\nImplemented the approved TechPlan steps.\n",
                "journal": "# Dev Journal\n",
                "findings": [],
                "evidence": [
                    {
                        "name": "self_code_review",
                        "kind": "report",
                        "summary": "Self-review completed.",
                    },
                    {
                        "name": "self_verification",
                        "kind": "command",
                        "summary": "Verification completed.",
                        "command": "python -m pytest",
                        "exit_code": 0,
                    },
                ],
                "summary": "Implemented Dev handoff.",
            }
            executor = FakeExecutor(json.dumps(bundle))
            harness = StageHarness(repo_root=repo_root, state_store=store, executor=executor)

            harness.run_stage(session.session_id, "Dev")

        self.assertTrue(executor.prompts)
        self.assertIn("=== Technical Plan ===", executor.prompts[0])
        self.assertIn("Implement via the approved TechPlan steps.", executor.prompts[0])


if __name__ == "__main__":
    unittest.main()
