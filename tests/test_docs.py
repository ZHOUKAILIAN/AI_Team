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

    def test_readme_documents_installable_skill_flow(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        readme = (repo_root / "README_zh.md").read_text()

        self.assertIn("install-codex-skill.sh", readme)
        self.assertIn("/company-run", readme)
        self.assertIn("~/.codex/skills", readme)


if __name__ == "__main__":
    unittest.main()
