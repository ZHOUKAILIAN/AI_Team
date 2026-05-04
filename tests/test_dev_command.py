import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_team.alignment import AlignmentCriterion, AlignmentDraft
from agent_team.interactive import DevController, DevControllerConfig, InteractivePrompter
from agent_team.skill_registry import SkillRegistry
from agent_team.tech_plan import TechPlanDraft


class FakePrompter(InteractivePrompter):
    def __init__(self, answers):
        self.answers = list(answers)
        self.messages = []

    def ask(self, message: str) -> str:
        self.messages.append(message)
        return self.answers.pop(0)

    def show(self, message: str) -> None:
        self.messages.append(message)


class FakeAlignmentRunner:
    def __init__(self) -> None:
        self.calls = []

    def align(self, raw_request, previous_alignment="", user_revision=""):
        self.calls.append((raw_request, previous_alignment, user_revision))
        return AlignmentDraft(
            requirement_understanding=["Do the thing"],
            acceptance_criteria=[AlignmentCriterion("AC1", "Thing is done", "Inspect output")],
            clarifying_questions=[],
        )


class FakeTechPlanRunner:
    def __init__(self) -> None:
        self.calls = []

    def plan(self, alignment, repo_structure, previous_plan="", user_revision=""):
        self.calls.append((alignment, repo_structure, previous_plan, user_revision))
        return TechPlanDraft(
            approach_summary="Use existing patterns.",
            affected_modules=["agent_team/example.py"],
            dependencies=[],
            implementation_steps=["Write code", "Run tests"],
            risks=["Low risk"],
            testing_strategy="Run focused tests.",
            clarifying_questions=[],
        )


class FakeStageHarness:
    def __init__(self, store) -> None:
        self.store = store
        self.stages = []

    def run_stage(self, session_id: str, stage: str):
        self.stages.append(stage)
        if stage == "Product":
            session = self.store.load_session(session_id)
            summary = self.store.load_workflow_summary(session_id)
            self.store.save_workflow_summary(
                session,
                replace(
                    summary,
                    current_state="WaitForCEOApproval",
                    current_stage="ProductDraft",
                    prd_status="drafted",
                ),
            )


class DevCommandTests(unittest.TestCase):
    def test_confirmed_y_runs_agent_chain_and_auto_approves_product(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir) / "state")
            stage_harness = FakeStageHarness(store)
            controller = DevController(
                config=DevControllerConfig(repo_root=Path(temp_dir), state_store=store),
                prompter=FakePrompter(["A real requirement", "y", "y", "y"]),
                alignment_runner=FakeAlignmentRunner(),
                tech_plan_runner=FakeTechPlanRunner(),
                stage_harness=stage_harness,
            )

            session_id = controller.run()
            summary = store.load_workflow_summary(session_id)
            session = store.load_session(session_id)

        self.assertTrue(session_id)
        self.assertEqual(session.initiator, "human")
        self.assertEqual(stage_harness.stages, ["Product", "TechPlan", "Dev", "QA", "Acceptance"])
        self.assertEqual(summary.human_decision, "go")

    def test_manual_decision_saves_session_without_running_agents(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir) / "state")
            stage_harness = FakeStageHarness(store)
            controller = DevController(
                config=DevControllerConfig(repo_root=Path(temp_dir), state_store=store),
                prompter=FakePrompter(["A real requirement", "y", "y", "m"]),
                alignment_runner=FakeAlignmentRunner(),
                tech_plan_runner=FakeTechPlanRunner(),
                stage_harness=stage_harness,
            )

            session_id = controller.run()

        self.assertTrue(session_id)
        self.assertEqual(stage_harness.stages, [])

    def test_edit_reruns_alignment_and_tech_plan(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir) / "state")
            alignment_runner = FakeAlignmentRunner()
            tech_plan_runner = FakeTechPlanRunner()
            prompter = FakePrompter(
                [
                    "Requirement",
                    "e",
                    "Add acceptance detail",
                    "y",
                    "e",
                    "Use existing module",
                    "y",
                    "m",
                ]
            )
            controller = DevController(
                config=DevControllerConfig(repo_root=Path(temp_dir), state_store=store),
                prompter=prompter,
                alignment_runner=alignment_runner,
                tech_plan_runner=tech_plan_runner,
                stage_harness=FakeStageHarness(store),
            )

            controller.run()

        self.assertEqual(len(alignment_runner.calls), 2)
        self.assertEqual(alignment_runner.calls[1][2], "Add acceptance detail")
        self.assertEqual(len(tech_plan_runner.calls), 2)
        self.assertEqual(tech_plan_runner.calls[1][3], "Use existing module")

    def test_skill_overrides_enable_stage_harness_skills(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            store = StateStore(repo_root / "state")
            stage_harness = FakeStageHarness(store)
            controller = DevController(
                config=DevControllerConfig(repo_root=repo_root, state_store=store),
                prompter=FakePrompter(["Requirement", "y", "y", "m"]),
                alignment_runner=FakeAlignmentRunner(),
                tech_plan_runner=FakeTechPlanRunner(),
                stage_harness=stage_harness,
                skill_registry=SkillRegistry(repo_root),
                skill_overrides={"Dev": ["plan"]},
            )

            controller.run()

        self.assertEqual(stage_harness.enabled_skills_by_stage["Dev"][0].name, "plan")

    def test_capture_repo_structure_excludes_generated_and_dependency_dirs(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "todo.py").write_text("")
            (repo_root / ".venv" / "lib" / "python" / "site-packages").mkdir(parents=True)
            (repo_root / ".venv" / "lib" / "python" / "site-packages" / "noise.py").write_text("")
            (repo_root / "node_modules" / "pkg").mkdir(parents=True)
            (repo_root / "node_modules" / "pkg" / "index.js").write_text("")
            (repo_root / ".agent-team").mkdir()
            (repo_root / ".agent-team" / "session.json").write_text("")
            controller = DevController(
                config=DevControllerConfig(repo_root=repo_root, state_store=StateStore(repo_root / "state")),
                prompter=FakePrompter([]),
                alignment_runner=FakeAlignmentRunner(),
                tech_plan_runner=FakeTechPlanRunner(),
                stage_harness=FakeStageHarness(StateStore(repo_root / "state")),
            )

            structure = controller._capture_repo_structure()

        self.assertIn("todo.py", structure)
        self.assertNotIn(".venv", structure)
        self.assertNotIn("node_modules", structure)
        self.assertNotIn(".agent-team", structure)


if __name__ == "__main__":
    unittest.main()
