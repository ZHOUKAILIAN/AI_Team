import os
import subprocess
import tomllib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class SkillPackageTests(unittest.TestCase):
    @staticmethod
    def _assert_common_follow_through_contract(testcase: unittest.TestCase, content: str) -> None:
        testcase.assertIn("Continue after session bootstrap", content)
        testcase.assertIn("inspect and implement in the real repository", content)
        testcase.assertIn("execute real verification against the runnable path when feasible", content)
        testcase.assertIn("collect concrete evidence for QA and Acceptance decisions", content)
        testcase.assertIn("route actionable", content)
        testcase.assertIn("if evidence is missing, report blocked instead of accepted", content)
        testcase.assertIn("acceptance_contract.json", content)
        testcase.assertIn("review_completion.json", content)
        testcase.assertIn("explicit user approval", content)
        testcase.assertIn("Workflow Isolation Contract", content)
        testcase.assertIn("Generic methodology skills may assist inside a stage", content)
        testcase.assertIn("must not change the Agent Team stage order", content)
        testcase.assertNotIn("1% rule", content)
        testcase.assertNotIn("Skill Dispatch Protocol", content)
        testcase.assertNotIn("python3 -m agent_team start-session", content)
        testcase.assertIn("Goal", content)
        testcase.assertIn("When To Use", content)
        testcase.assertIn("Available assets", content)
        testcase.assertIn("Completion Signals", content)

    def test_root_skill_retained_for_codex_trigger(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        root_skill = repo_root / "SKILL.md"

        self.assertTrue(root_skill.exists())
        content = root_skill.read_text()

    def test_skills_stay_close_to_skill_standard(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        for path in (
            repo_root / "SKILL.md",
        ):
            content = path.read_text()
            self.assertIn("Goal", content)
            self.assertIn("When To Use", content)
            self.assertIn("Available assets", content)
            self.assertIn("Completion Signals", content)
            self.assertNotIn("file://", content)
            self.assertNotIn("/Users/", content)

    def test_generated_local_run_skill_uses_goal_oriented_contract_language(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        project_scaffold = (repo_root / "agent_team" / "project_scaffold.py").read_text()

        self.assertIn("Workflow Isolation Contract", project_scaffold)
        self.assertIn("Generic methodology skills may assist inside a stage", project_scaffold)
        self.assertIn("must not change the Agent Team stage order", project_scaffold)
        self.assertNotIn("## Bootstrap", project_scaffold)

    def test_codex_init_generates_project_local_agents_and_run_skill(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "repo"
            state_root = Path(temp_dir) / "state"
            project_root.mkdir()
            result = subprocess.run(
                [
                    os.environ.get("PYTHON", "python3"),
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
            dev_agent_lines = (project_root / ".codex" / "agents" / "agent_team_dev.toml").read_text().splitlines()
            agent_names = {
                path.stem: tomllib.loads(path.read_text()).get("name")
                for path in (project_root / ".codex" / "agents").glob("agent_team_*.toml")
            }
            all_agent_text = "\n".join(
                path.read_text()
                for path in (project_root / ".codex" / "agents").glob("agent_team_*.toml")
            )
            self.assertEqual(
                agent_names,
                {
                    "agent_team_product": "agent_team_product",
                    "agent_team_dev": "agent_team_dev",
                    "agent_team_qa": "agent_team_qa",
                    "agent_team_acceptance": "agent_team_acceptance",
                },
            )
            self.assertIn('developer_instructions = """', dev_agent_lines)
            self.assertNotIn('instructions = """', dev_agent_lines)
            self.assertIn("packaged Dev role context", all_agent_text)
            self.assertIn("runtime stage contract", all_agent_text)
            self.assertNotIn("Read and follow `Product/context.md`", all_agent_text)
            self.assertNotIn("Read and follow `Dev/context.md`", all_agent_text)
            self.assertNotIn("Read and follow `QA/context.md`", all_agent_text)
            self.assertNotIn("Read and follow `Acceptance/context.md`", all_agent_text)

        self.assertTrue((repo_root / "scripts" / "agent-team-init.sh").exists())
        self.assertTrue((repo_root / "scripts" / "agent-team-run.sh").exists())


if __name__ == "__main__":
    unittest.main()
