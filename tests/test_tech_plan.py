import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_team.alignment import AlignmentCriterion, AlignmentDraft
from agent_team.tech_plan import (
    TechPlanDraft,
    load_confirmed_tech_plan,
    parse_tech_plan_json,
    render_tech_plan_for_terminal,
    save_confirmed_tech_plan,
    tech_plan_prompt,
)


class TechPlanTests(unittest.TestCase):
    def test_parse_tech_plan_json_requires_implementation_steps(self) -> None:
        payload = {
            "approach_summary": "Add a focused feature.",
            "affected_modules": ["pages/profile/index.vue"],
            "dependencies": [],
            "implementation_steps": [],
            "risks": [],
            "testing_strategy": "Run unit tests.",
            "clarifying_questions": [],
        }

        with self.assertRaisesRegex(ValueError, "implementation_steps"):
            parse_tech_plan_json(json.dumps(payload))

    def test_parse_tech_plan_json_returns_structured_draft(self) -> None:
        payload = {
            "approach_summary": "Add a focused feature.",
            "affected_modules": ["pages/profile/index.vue"],
            "dependencies": ["existing API client"],
            "implementation_steps": ["Update page state", "Add test"],
            "risks": ["Profile API may reject long nicknames"],
            "testing_strategy": "Run profile page tests.",
            "clarifying_questions": ["Should nickname trim whitespace?"],
        }

        draft = parse_tech_plan_json(json.dumps(payload))

        self.assertEqual(draft.approach_summary, "Add a focused feature.")
        self.assertEqual(draft.affected_modules, ["pages/profile/index.vue"])
        self.assertEqual(draft.dependencies, ["existing API client"])
        self.assertEqual(draft.implementation_steps, ["Update page state", "Add test"])
        self.assertEqual(draft.risks, ["Profile API may reject long nicknames"])
        self.assertEqual(draft.testing_strategy, "Run profile page tests.")
        self.assertEqual(draft.clarifying_questions, ["Should nickname trim whitespace?"])

    def test_render_tech_plan_for_terminal_is_readable(self) -> None:
        draft = TechPlanDraft(
            approach_summary="Add a focused feature.",
            affected_modules=["pages/profile/index.vue"],
            dependencies=[],
            implementation_steps=["Update page state", "Add test"],
            risks=["Profile API may reject long nicknames"],
            testing_strategy="Run profile page tests.",
            clarifying_questions=[],
        )

        rendered = render_tech_plan_for_terminal(draft)

        self.assertIn("Technical approach", rendered)
        self.assertIn("pages/profile/index.vue", rendered)
        self.assertIn("Update page state", rendered)
        self.assertIn("Run profile page tests.", rendered)

    def test_save_and_load_confirmed_tech_plan_round_trip(self) -> None:
        draft = TechPlanDraft(
            approach_summary="Add a focused feature.",
            affected_modules=["pages/profile/index.vue"],
            dependencies=[],
            implementation_steps=["Update page state", "Add test"],
            risks=[],
            testing_strategy="Run profile page tests.",
            clarifying_questions=[],
        )

        with TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir)
            path = save_confirmed_tech_plan(session_dir, draft)

            self.assertEqual(path, session_dir / "technical_plan.json")
            self.assertEqual(load_confirmed_tech_plan(session_dir), draft)

    def test_tech_plan_prompt_includes_alignment_repo_structure_and_revision(self) -> None:
        alignment = AlignmentDraft(
            requirement_understanding=["Add a profile editor."],
            acceptance_criteria=[
                AlignmentCriterion("AC1", "Users can save a nickname.", "Run profile edit test.")
            ],
            clarifying_questions=[],
        )

        prompt = tech_plan_prompt(
            repo_root=Path("/repo"),
            confirmed_alignment=alignment,
            repo_structure="pages/profile/index.vue\napi/profile.ts",
            previous_plan='{"approach_summary": "old"}',
            user_revision="Use existing profile API.",
        )

        self.assertIn("Tech Lead role", prompt)
        self.assertIn("pages/profile/index.vue", prompt)
        self.assertIn("Use existing profile API.", prompt)
        self.assertIn("Add a profile editor.", prompt)
        self.assertIn("strict JSON", prompt)


if __name__ == "__main__":
    unittest.main()
