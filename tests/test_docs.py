import unittest
from pathlib import Path


class DocsTests(unittest.TestCase):
    def test_readme_documents_run_and_review_commands(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        readme = (repo_root / "README_zh.md").read_text()

        self.assertIn("python3 -m ai_company run", readme)
        self.assertIn("学习闭环", readme)
        self.assertIn("agent-run", readme)
        self.assertIn("执行这个需求：", readme)

    def test_skill_documents_agent_friendly_triggers(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        skill = (repo_root / "SKILL.md").read_text()

        self.assertIn("agent-friendly", skill)
        self.assertIn("执行这个需求：", skill)
        self.assertIn("python3 -m ai_company agent-run", skill)
        self.assertIn("/company-run", skill)

    def test_skill_documents_platform_verification_rules(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        root_skill = (repo_root / "SKILL.md").read_text()
        qa_skill = (repo_root / "QA" / "SKILL.md").read_text()
        acceptance_skill = (repo_root / "Acceptance" / "SKILL.md").read_text()

        self.assertIn("miniprogram", root_skill)
        self.assertIn("browser-use", root_skill)
        self.assertIn("already specified the verification platform", root_skill)
        self.assertNotIn("gstack browse", root_skill)
        self.assertNotIn("`minipro`", root_skill)
        self.assertIn("already specified the verification platform", qa_skill)
        self.assertIn("miniprogram", qa_skill)
        self.assertIn("browser-use", qa_skill)
        self.assertIn("already specified the verification platform", acceptance_skill)
        self.assertIn("miniprogram", acceptance_skill)
        self.assertIn("browser-use", acceptance_skill)

    def test_readme_documents_installable_skill_flow(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        readme = (repo_root / "README_zh.md").read_text()

        self.assertIn("install-codex-skill.sh", readme)
        self.assertIn("install-codex-ai-team.sh", readme)
        self.assertIn("/company-run", readme)
        self.assertIn("~/.codex/skills", readme)
        self.assertIn("~/.codex/vendor/ai-team", readme)


if __name__ == "__main__":
    unittest.main()
