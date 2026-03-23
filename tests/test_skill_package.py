import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class SkillPackageTests(unittest.TestCase):
    def test_installable_skill_exists_and_declares_trigger(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        skill_path = repo_root / "codex-skill" / "ai-company-workflow" / "SKILL.md"

        self.assertTrue(skill_path.exists())
        content = skill_path.read_text()
        self.assertIn("name: ai-company-workflow", content)
        self.assertIn("/company-run", content)
        self.assertIn("python3 -m ai_company agent-run", content)

    def test_install_script_copies_skill_into_codex_home(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "scripts" / "install-codex-skill.sh"

        with TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["HOME"] = temp_dir
            env.pop("CODEX_HOME", None)
            result = subprocess.run(
                [str(script)],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            installed_skill = Path(temp_dir) / ".codex" / "skills" / "ai-company-workflow" / "SKILL.md"
            self.assertEqual(result.returncode, 0)
            self.assertTrue(installed_skill.exists())


if __name__ == "__main__":
    unittest.main()
