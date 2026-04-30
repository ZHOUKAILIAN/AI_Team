import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_team.alignment import (
    AlignmentCriterion,
    AlignmentDraft,
    acceptance_criteria_strings,
    alignment_prompt,
    confirmed_request_text,
    load_confirmed_alignment,
    parse_alignment_json,
    render_alignment_for_terminal,
    save_confirmed_alignment,
)


class AlignmentTests(unittest.TestCase):
    def test_parse_alignment_json_requires_acceptance_criteria(self) -> None:
        payload = {
            "requirement_understanding": ["Add a profile editor."],
            "acceptance_criteria": [],
            "clarifying_questions": [],
        }

        with self.assertRaisesRegex(ValueError, "acceptance_criteria"):
            parse_alignment_json(json.dumps(payload))

    def test_parse_alignment_json_returns_structured_draft(self) -> None:
        payload = {
            "requirement_understanding": ["Add a profile editor."],
            "acceptance_criteria": [
                {
                    "id": "AC1",
                    "criterion": "Users can save a nickname.",
                    "verification": "Run profile edit happy-path test.",
                }
            ],
            "clarifying_questions": ["Should nickname length be limited?"],
        }

        draft = parse_alignment_json(json.dumps(payload))

        self.assertEqual(draft.requirement_understanding, ["Add a profile editor."])
        self.assertEqual(
            draft.acceptance_criteria,
            [
                AlignmentCriterion(
                    id="AC1",
                    criterion="Users can save a nickname.",
                    verification="Run profile edit happy-path test.",
                )
            ],
        )
        self.assertEqual(draft.clarifying_questions, ["Should nickname length be limited?"])

    def test_render_alignment_for_terminal_is_readable(self) -> None:
        draft = AlignmentDraft(
            requirement_understanding=["Add a profile editor."],
            acceptance_criteria=[
                AlignmentCriterion(
                    id="AC1",
                    criterion="Users can save a nickname.",
                    verification="Run profile edit happy-path test.",
                )
            ],
            clarifying_questions=[],
        )

        rendered = render_alignment_for_terminal(draft)

        self.assertIn("Requirement understanding", rendered)
        self.assertIn("Acceptance criteria", rendered)
        self.assertIn("AC1", rendered)
        self.assertIn("Users can save a nickname.", rendered)
        self.assertIn("Run profile edit happy-path test.", rendered)

    def test_save_and_load_confirmed_alignment_round_trip(self) -> None:
        draft = AlignmentDraft(
            requirement_understanding=["Add a profile editor."],
            acceptance_criteria=[
                AlignmentCriterion(
                    id="AC1",
                    criterion="Users can save a nickname.",
                    verification="Run profile edit happy-path test.",
                )
            ],
            clarifying_questions=[],
        )

        with TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir)
            path = save_confirmed_alignment(session_dir, draft)

            self.assertEqual(path, session_dir / "confirmed_alignment.json")
            self.assertEqual(load_confirmed_alignment(session_dir), draft)

    def test_alignment_prompt_focuses_on_requirement_and_acceptance(self) -> None:
        prompt = alignment_prompt(
            raw_request="执行这个需求：Add profile editor",
            previous_alignment='{"acceptance_criteria": []}',
            user_revision="Limit nickname to 20 chars.",
        )

        self.assertIn("Add profile editor", prompt)
        self.assertIn("Limit nickname to 20 chars.", prompt)
        self.assertIn("strict JSON", prompt)
        self.assertIn("acceptance_criteria", prompt)
        self.assertNotIn('"scope"', prompt)

    def test_acceptance_criteria_strings_include_verification(self) -> None:
        draft = AlignmentDraft(
            requirement_understanding=["Add a profile editor."],
            acceptance_criteria=[
                AlignmentCriterion("AC1", "Users can save a nickname.", "Run profile edit test.")
            ],
            clarifying_questions=[],
        )

        self.assertEqual(
            acceptance_criteria_strings(draft),
            ["AC1: Users can save a nickname. Verification: Run profile edit test."],
        )

    def test_confirmed_request_text_embeds_rendered_alignment(self) -> None:
        draft = AlignmentDraft(
            requirement_understanding=["Add a profile editor."],
            acceptance_criteria=[
                AlignmentCriterion("AC1", "Users can save a nickname.", "Run profile edit test.")
            ],
            clarifying_questions=[],
        )

        text = confirmed_request_text("Raw request", draft)

        self.assertIn("Raw request", text)
        self.assertIn("Confirmed alignment", text)
        self.assertIn("Users can save a nickname.", text)


if __name__ == "__main__":
    unittest.main()
