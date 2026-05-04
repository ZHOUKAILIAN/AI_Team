import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class RuntimePackagingTests(unittest.TestCase):
    def test_workflow_is_not_exposed_as_root_or_installable_codex_skill(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        self.assertFalse((repo_root / "SKILL.md").exists())
        self.assertFalse((repo_root / "codex-skill" / "agent-team-workflow").exists())
        self.assertFalse((repo_root / "agent_team" / "assets" / "codex_skill").exists())
        self.assertFalse((repo_root / "scripts" / "install-codex-skill.sh").exists())
        self.assertFalse((repo_root / "scripts" / "agent-team-init.sh").exists())
        self.assertTrue((repo_root / "scripts" / "agent-team-run.sh").exists())

    def test_cli_does_not_offer_installable_workflow_skill_command(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("install-codex-skill", result.stdout)
        self.assertNotIn("codex-init", result.stdout)
        self.assertIn("run", result.stdout)
        self.assertIn("dev", result.stdout)

    def test_global_install_script_vendors_runtime_without_installing_workflow_skill(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "scripts" / "install-codex-agent-team.sh"

        with TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["HOME"] = temp_dir
            env["AGENT_TEAM_REPO_SOURCE"] = str(repo_root)
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
            vendored_repo = codex_home / "vendor" / "agent-team" / "agent_team" / "cli.py"
            old_skill = codex_home / "skills" / "agent-team-workflow" / "SKILL.md"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(vendored_repo.exists())
            self.assertFalse(old_skill.exists())
            self.assertNotIn("agent-team-workflow skill", result.stdout)


if __name__ == "__main__":
    unittest.main()
