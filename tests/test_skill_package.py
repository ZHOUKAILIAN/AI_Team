import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class SkillPackageTests(unittest.TestCase):
    @staticmethod
    def _front_matter(path: Path) -> str:
        content = path.read_text()
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise AssertionError(f"{path} is missing YAML front matter")
        return f"---{parts[1]}---\n"

    def test_installable_skill_exists_and_declares_trigger(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        skill_path = repo_root / "codex-skill" / "ai-company-workflow" / "SKILL.md"
        helper_script = repo_root / "codex-skill" / "ai-company-workflow" / "scripts" / "company-run.sh"

        self.assertTrue(skill_path.exists())
        self.assertTrue(helper_script.exists())
        content = skill_path.read_text()
        self.assertIn("name: ai-company-workflow", content)
        self.assertIn("/company-run", content)
        self.assertIn("company-run.sh", content)
        self.assertIn("miniprogram", content)
        self.assertIn("browser-use", content)
        self.assertIn("already specified the verification platform", content)

    def test_installable_skill_front_matter_is_valid_yaml(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        skill_path = repo_root / "codex-skill" / "ai-company-workflow" / "SKILL.md"
        result = subprocess.run(
            ["ruby", "-e", "require 'yaml'; Psych.safe_load(STDIN.read)"],
            input=self._front_matter(skill_path),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

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
            installed_helper = Path(temp_dir) / ".codex" / "skills" / "ai-company-workflow" / "scripts" / "company-run.sh"
            self.assertEqual(result.returncode, 0)
            self.assertTrue(installed_skill.exists())
            self.assertTrue(installed_helper.exists())

            yaml_result = subprocess.run(
                ["ruby", "-e", "require 'yaml'; Psych.safe_load(STDIN.read)"],
                input=self._front_matter(installed_skill),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(yaml_result.returncode, 0, yaml_result.stderr)

    def test_global_install_script_vendors_repo_and_skill(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "scripts" / "install-codex-ai-team.sh"

        with TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["HOME"] = temp_dir
            env["AI_TEAM_REPO_SOURCE"] = str(repo_root)
            env.pop("CODEX_HOME", None)
            result = subprocess.run(
                [str(script)],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            codex_home = Path(temp_dir) / ".codex"
            installed_skill = codex_home / "skills" / "ai-company-workflow" / "SKILL.md"
            vendored_repo = codex_home / "vendor" / "ai-team" / "ai_company" / "cli.py"
            self.assertEqual(result.returncode, 0)
            self.assertTrue(installed_skill.exists())
            self.assertTrue(vendored_repo.exists())

    def test_installed_helper_script_runs_from_vendored_runtime(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        install_script = repo_root / "scripts" / "install-codex-ai-team.sh"

        with TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["HOME"] = temp_dir
            env["AI_TEAM_REPO_SOURCE"] = str(repo_root)
            env.pop("CODEX_HOME", None)
            install_result = subprocess.run(
                [str(install_script)],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(install_result.returncode, 0)

            helper_script = (
                Path(temp_dir)
                / ".codex"
                / "skills"
                / "ai-company-workflow"
                / "scripts"
                / "company-run.sh"
            )
            run_result = subprocess.run(
                [str(helper_script), "执行这个需求：做一个全局安装后可直接触发的 AI 公司流程"],
                cwd=Path(temp_dir),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(run_result.returncode, 0)
            self.assertIn("session_id:", run_result.stdout)
            self.assertIn("acceptance_status:", run_result.stdout)


if __name__ == "__main__":
    unittest.main()
