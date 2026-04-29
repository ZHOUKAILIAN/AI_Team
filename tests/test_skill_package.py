import os
import subprocess
import tomllib
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
        testcase.assertIn("must not change the AI_Team stage order", content)
        testcase.assertNotIn("1% rule", content)
        testcase.assertNotIn("Skill Dispatch Protocol", content)
        testcase.assertNotIn("python3 -m ai_company start-session", content)
        testcase.assertIn("Goal", content)
        testcase.assertIn("When To Use", content)
        testcase.assertIn("Available assets", content)
        testcase.assertIn("Completion Signals", content)

    def test_root_skill_describes_single_session_state_machine(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        root_skill = repo_root / "SKILL.md"

        self.assertTrue(root_skill.exists())
        content = root_skill.read_text()
        self.assertIn("Intake", content)
        self.assertIn("ProductDraft", content)
        self.assertIn("WaitForCEOApproval", content)
        self.assertIn("Dev", content)
        self.assertIn("QA", content)
        self.assertIn("Acceptance", content)
        self.assertIn("WaitForHumanDecision", content)
        self.assertIn(".codex/agents/*.toml", content)
        self.assertIn(".agents/skills/ai-team-run/SKILL.md", content)
        self.assertIn("./scripts/company-init.sh", content)
        self.assertIn("./scripts/company-run.sh", content)
        self.assertIn("prd.md", content)
        self.assertIn("implementation.md", content)
        self.assertIn("qa_report.md", content)
        self.assertIn("acceptance_report.md", content)
        self.assertIn("workflow_summary.md", content)
        self.assertIn("QA must independently rerun verification", content)
        self.assertIn("missing evidence", content)
        self.assertIn("blocked", content)
        self.assertIn("Acceptance recommends", content)
        self.assertIn("human decides", content)
        self.assertIn("record-feedback", content)
        self.assertIn("completion signals", content)
        self.assertIn("runtime_screenshot", content)
        self.assertIn("overlay_diff", content)
        self.assertIn("page_root_recursive_audit", content)
        self.assertIn("acceptance_contract.json", content)
        self.assertIn("review_completion.json", content)
        self.assertIn("explicit user approval", content)
        self.assertIn("Available assets", content)
        self.assertIn("scripts/", content)
        self.assertIn("ai-team", content)
        self.assertIn(
            "deterministic runtime output is workflow metadata only, not real QA/Acceptance evidence",
            content,
        )
        self._assert_common_follow_through_contract(self, content)

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
        self.assertIn("scripts/", content)
        self.assertIn("Intake", content)
        self.assertIn("ProductDraft", content)
        self.assertIn("WaitForCEOApproval", content)
        self.assertIn("Dev", content)
        self.assertIn("QA", content)
        self.assertIn("Acceptance", content)
        self.assertIn("WaitForHumanDecision", content)
        self.assertIn("prd.md", content)
        self.assertIn("implementation.md", content)
        self.assertIn("qa_report.md", content)
        self.assertIn("acceptance_report.md", content)
        self.assertIn("workflow_summary.md", content)
        self.assertIn("QA must independently rerun verification", content)
        self.assertIn("missing evidence", content)
        self.assertIn("blocked", content)
        self.assertIn("Acceptance recommends", content)
        self.assertIn("human decides", content)
        self.assertIn("record-feedback", content)
        self.assertIn("completion signal", content)
        self.assertIn("runtime_screenshot", content)
        self.assertIn("overlay_diff", content)
        self.assertIn("page_root_recursive_audit", content)
        self.assertIn("acceptance_contract.json", content)
        self.assertIn("review_completion.json", content)
        self.assertIn("explicit user approval", content)
        self.assertIn("Available assets", content)
        self.assertIn("scripts/", content)
        self.assertIn("ai-team", content)
        self.assertIn(
            "deterministic runtime output is workflow metadata only, not real QA/Acceptance evidence",
            content,
        )
        self.assertIn("helper script only bootstraps a session", content)
        self.assertIn("continue the state machine in the current Codex session", content)
        self.assertIn("does not complete QA or Acceptance by itself", content)
        self._assert_common_follow_through_contract(self, content)

    def test_skills_stay_close_to_skill_standard(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        for path in (
            repo_root / "SKILL.md",
            repo_root / "codex-skill" / "ai-company-workflow" / "SKILL.md",
        ):
            content = path.read_text()
            self.assertIn("Goal", content)
            self.assertIn("When To Use", content)
            self.assertIn("Available assets", content)
            self.assertIn("Completion Signals", content)
            self.assertNotIn("file://", content)
            self.assertNotIn("/Users/", content)

    def test_root_and_packaged_skills_keep_follow_through_parity(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        root_content = (repo_root / "SKILL.md").read_text()
        packaged_content = (
            repo_root / "codex-skill" / "ai-company-workflow" / "SKILL.md"
        ).read_text()

        follow_through_lines = [
            "Continue after session bootstrap:",
            "- inspect and implement in the real repository",
            "- execute real verification against the runnable path when feasible",
            "- collect concrete evidence for QA and Acceptance decisions",
            "- if evidence is missing, report blocked instead of accepted",
        ]
        for line in follow_through_lines:
            self.assertIn(line, root_content)
            self.assertIn(line, packaged_content)

    def test_generated_local_run_skill_uses_goal_oriented_contract_language(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        project_scaffold = (repo_root / "ai_company" / "project_scaffold.py").read_text()

        self.assertIn("Workflow Isolation Contract", project_scaffold)
        self.assertIn("Generic methodology skills may assist inside a stage", project_scaffold)
        self.assertIn("must not change the AI_Team stage order", project_scaffold)
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
                    "ai_company",
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
            self.assertTrue((project_root / ".codex" / "agents" / "ai_team_product.toml").exists())
            self.assertTrue((project_root / ".codex" / "agents" / "ai_team_dev.toml").exists())
            self.assertTrue((project_root / ".codex" / "agents" / "ai_team_qa.toml").exists())
            self.assertTrue((project_root / ".codex" / "agents" / "ai_team_acceptance.toml").exists())
            self.assertTrue((project_root / ".agents" / "skills" / "ai-team-run" / "SKILL.md").exists())
            self.assertFalse((project_root / ".codex" / "config.toml").exists())
            self.assertFalse((project_root / ".agents" / "skills" / "ai-team-init" / "SKILL.md").exists())
            dev_agent_lines = (project_root / ".codex" / "agents" / "ai_team_dev.toml").read_text().splitlines()
            agent_names = {
                path.stem: tomllib.loads(path.read_text()).get("name")
                for path in (project_root / ".codex" / "agents").glob("ai_team_*.toml")
            }
            all_agent_text = "\n".join(
                path.read_text()
                for path in (project_root / ".codex" / "agents").glob("ai_team_*.toml")
            )
            self.assertEqual(
                agent_names,
                {
                    "ai_team_product": "ai_team_product",
                    "ai_team_dev": "ai_team_dev",
                    "ai_team_qa": "ai_team_qa",
                    "ai_team_acceptance": "ai_team_acceptance",
                },
            )
            self.assertIn('developer_instructions = """', dev_agent_lines)
            self.assertNotIn('instructions = """', dev_agent_lines)
            run_skill = (project_root / ".agents" / "skills" / "ai-team-run" / "SKILL.md").read_text()
            self.assertIn("ai-team dev", run_skill)
            self.assertIn("terminal workflows", run_skill)
            self.assertIn("packaged Dev role context", all_agent_text)
            self.assertIn("runtime stage contract", all_agent_text)
            self.assertNotIn("Read and follow `Product/context.md`", all_agent_text)
            self.assertNotIn("Read and follow `Dev/context.md`", all_agent_text)
            self.assertNotIn("Read and follow `QA/context.md`", all_agent_text)
            self.assertNotIn("Read and follow `Acceptance/context.md`", all_agent_text)

        self.assertTrue((repo_root / "scripts" / "company-init.sh").exists())
        self.assertTrue((repo_root / "scripts" / "company-run.sh").exists())

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

    def test_cli_install_codex_skill_uses_packaged_assets(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["HOME"] = temp_dir
            env.pop("CODEX_HOME", None)
            result = subprocess.run(
                [
                    os.environ.get("PYTHON", "python3"),
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "install-codex-skill",
                ],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            installed_skill = Path(temp_dir) / ".codex" / "skills" / "ai-company-workflow" / "SKILL.md"
            installed_helper = (
                Path(temp_dir)
                / ".codex"
                / "skills"
                / "ai-company-workflow"
                / "scripts"
                / "company-run.sh"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(installed_skill.exists())
            self.assertTrue(installed_helper.exists())
            self.assertTrue(os.access(installed_helper, os.X_OK))
            self.assertIn("installed_skill:", result.stdout)

    def test_packaged_company_run_helper_uses_current_workspace_repo_root(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "target-project"
            project_root.mkdir()
            fake_bin = temp_root / "bin"
            fake_bin.mkdir()
            argv_path = temp_root / "ai-team-argv.txt"
            fake_ai_team = fake_bin / "ai-team"
            fake_ai_team.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" > \"$AI_TEAM_ARGV_PATH\"\n"
                "printf '%s\\n' 'session_id: fake-session'\n"
                "printf '%s\\n' \"artifact_dir: ${PWD}/.ai-team/fake-session\"\n"
                "printf '%s\\n' \"summary_path: ${PWD}/.ai-team/fake-session/workflow_summary.md\"\n"
            )
            fake_ai_team.chmod(0o755)

            env = os.environ.copy()
            env["HOME"] = str(temp_root / "home")
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["AI_TEAM_ARGV_PATH"] = str(argv_path)
            env.pop("CODEX_HOME", None)
            install_result = subprocess.run(
                [
                    os.environ.get("PYTHON", "python3"),
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "install-codex-skill",
                ],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(install_result.returncode, 0, install_result.stderr)

            helper_script = (
                Path(env["HOME"])
                / ".codex"
                / "skills"
                / "ai-company-workflow"
                / "scripts"
                / "company-run.sh"
            )
            helper_text = helper_script.read_text()
            self.assertNotIn("-d \"${VENDOR_DIR}/Product\"", helper_text)
            self.assertNotIn("RUNTIME_DIR", helper_text)

            run_result = subprocess.run(
                [str(helper_script), "执行这个需求：验证全局 helper 使用当前项目根目录"],
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(run_result.returncode, 0, run_result.stderr)
            self.assertIn("session_id:", run_result.stdout)
            self.assertEqual(
                argv_path.read_text().splitlines(),
                [
                    "--repo-root",
                    str(project_root.resolve()),
                    "start-session",
                    "--message",
                    "执行这个需求：验证全局 helper 使用当前项目根目录",
                ],
            )

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
            self.assertIn("artifact_dir:", run_result.stdout)
            self.assertIn("summary_path:", run_result.stdout)
            self.assertNotIn("acceptance_status:", run_result.stdout)


if __name__ == "__main__":
    unittest.main()
