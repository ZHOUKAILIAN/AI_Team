import os
import subprocess
import sys
import tomllib
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

    def test_cli_does_not_offer_installable_workflow_skill_command(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("install-codex-skill", result.stdout)
        self.assertIn("run-requirement", result.stdout)
        self.assertIn("dev", result.stdout)

    def test_codex_init_generates_project_local_agents_and_run_skill(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "repo"
            state_root = Path(temp_dir) / "state"
            project_root.mkdir()
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(project_root),
                    "--state-root",
                    str(state_root),
                    "codex-init",
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((project_root / ".codex" / "agents" / "agent_team_product.toml").exists())
            self.assertTrue((project_root / ".codex" / "agents" / "agent_team_dev.toml").exists())
            self.assertTrue((project_root / ".codex" / "agents" / "agent_team_qa.toml").exists())
            self.assertTrue((project_root / ".codex" / "agents" / "agent_team_acceptance.toml").exists())
            self.assertTrue((project_root / ".agents" / "skills" / "agent-team-run" / "SKILL.md").exists())
            self.assertFalse((project_root / ".codex" / "config.toml").exists())
            self.assertFalse((project_root / ".agents" / "skills" / "agent-team-init" / "SKILL.md").exists())
            self.assertIn("generated_files: 5", result.stdout)

            agent_names = {
                path.stem: tomllib.loads(path.read_text()).get("name")
                for path in (project_root / ".codex" / "agents").glob("agent_team_*.toml")
            }
            self.assertEqual(
                agent_names,
                {
                    "agent_team_product": "agent_team_product",
                    "agent_team_dev": "agent_team_dev",
                    "agent_team_qa": "agent_team_qa",
                    "agent_team_acceptance": "agent_team_acceptance",
                },
            )
            all_agent_text = "\n".join(
                path.read_text()
                for path in (project_root / ".codex" / "agents").glob("agent_team_*.toml")
            )
            run_skill = (project_root / ".agents" / "skills" / "agent-team-run" / "SKILL.md").read_text()
            self.assertIn("agent-team dev", run_skill)
            self.assertIn("terminal workflows", run_skill)
            self.assertIn("packaged Dev role context", all_agent_text)
            self.assertIn("runtime stage contract", all_agent_text)

        self.assertTrue((repo_root / "scripts" / "agent-team-init.sh").exists())
        self.assertTrue((repo_root / "scripts" / "agent-team-run.sh").exists())

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
