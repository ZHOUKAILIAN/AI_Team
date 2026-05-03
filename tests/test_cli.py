import io
import os
import subprocess
import sys
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


def evidence(name: str, *, kind: str = "report", summary: str = "Evidence provided.") -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "kind": kind,
        "summary": summary,
    }
    if kind == "command":
        payload["command"] = "python -m unittest"
        payload["exit_code"] = 0
    return payload


class CliTests(unittest.TestCase):
    def test_cli_without_command_exits_with_argparse_error_instead_of_traceback(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("the following arguments are required: command", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_help_exits_successfully(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("review", result.stdout)
        self.assertIn("init", result.stdout)
        self.assertNotIn("init-state", result.stdout)
        self.assertNotIn("init-project-structure", result.stdout)
        self.assertIn("start-session", result.stdout)
        self.assertIn("run-requirement", result.stdout)
        self.assertNotIn("agent-run", result.stdout)
        self.assertNotIn("Demo command: execute the deterministic workflow session", result.stdout)
        self.assertNotIn("codex-init", result.stdout)
        self.assertIn("panel", result.stdout)
        self.assertIn("panel-snapshot", result.stdout)
        self.assertIn("status", result.stdout)

    def test_init_bootstraps_state_and_project_structure(self) -> None:
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "init",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("state_root:", result.stdout)
            self.assertIn("project_root:", result.stdout)
            self.assertTrue((repo_root / ".agent-team" / "memory").is_dir())
            self.assertTrue((repo_root / "agent-team" / "project" / "doc-map.json").is_file())

    def test_cli_help_lists_readonly_board_commands(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("board-snapshot", result.stdout)
        self.assertIn("serve-board", result.stdout)

    def test_cli_help_lists_dev_command(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("dev", result.stdout)

    def test_dev_help_exits_successfully(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "dev", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("--message", result.stdout)
        self.assertIn("--session-id", result.stdout)
        self.assertIn("--executor", result.stdout)
        self.assertIn("--claude-bin", result.stdout)
        self.assertIn("--codex-bin", result.stdout)
        self.assertIn("--with-skills", result.stdout)

    def test_skill_commands_list_builtin_skills(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_team",
                "--repo-root",
                str(repo_root),
                "skill",
                "list",
                "--stage",
                "Dev",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("plan", result.stdout)
        self.assertIn("built-in", result.stdout)

    def test_skill_preferences_reset_creates_empty_preference_file(self) -> None:
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "skill",
                    "preferences",
                    "--reset",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("dev:", result.stdout)
            self.assertTrue((repo_root / ".agent-team" / "skill-preferences.yaml").exists())

    def test_demo_run_commands_are_not_registered(self) -> None:
        run_help = subprocess.run(
            [sys.executable, "-m", "agent_team", "run", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        agent_run_help = subprocess.run(
            [sys.executable, "-m", "agent_team", "agent-run", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(run_help.returncode, 2)
        self.assertEqual(agent_run_help.returncode, 2)
        self.assertIn("invalid choice: 'run'", run_help.stderr)
        self.assertIn("invalid choice: 'agent-run'", agent_run_help.stderr)

    def test_start_session_bootstraps_session_from_raw_message(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        raw_message = "执行这个需求：做一个支持验收回写学习记录的任务系统"

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    raw_message,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("session_id:", result.stdout)
            self.assertIn("artifact_dir:", result.stdout)
            self.assertIn("summary_path:", result.stdout)

            output_lines = [line for line in result.stdout.splitlines() if ":" in line]
            output_map = dict(line.split(": ", 1) for line in output_lines)

            session_id = output_map["session_id"]
            artifact_dir = Path(output_map["artifact_dir"])
            summary_path = Path(output_map["summary_path"])
            request_path = artifact_dir / "request.md"
            session_json_path = Path(temp_dir) / session_id / "session.json"

            self.assertTrue(artifact_dir.exists())
            self.assertTrue(summary_path.exists())
            self.assertTrue(request_path.exists())
            self.assertTrue(session_json_path.exists())
            self.assertIn("做一个支持验收回写学习记录的任务系统", request_path.read_text())
            self.assertIn(raw_message, request_path.read_text())
            session_payload = json.loads(session_json_path.read_text())
            self.assertEqual(session_payload["raw_message"], raw_message)

    def test_start_session_help_describes_session_scaffold_command(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "start-session", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "Create a session scaffold for the single-session Agent Team workflow.",
            result.stdout,
        )

    def test_run_requirement_dry_run_stops_at_product_approval_gate(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run-requirement",
                    "--message",
                    "执行这个需求：做一个 runtime 强制驱动流程",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("runtime_driver_status: waiting_human", result.stdout)
            self.assertIn("current_state: WaitForCEOApproval", result.stdout)
            self.assertIn("next_action: record-human-decision --decision go", result.stdout)
            output_lines = [line for line in result.stdout.splitlines() if ": " in line]
            output_map = dict(line.split(": ", 1) for line in output_lines)
            session_id = output_map["session_id"]
            session_dir = Path(temp_dir) / session_id
            self.assertTrue((session_dir / "prd.md").exists())
            self.assertFalse((session_dir / "implementation.md").exists())
            self.assertTrue((session_dir / "stage_runs" / "product-run-1.json").exists())

    def test_run_requirement_without_message_or_session_id_in_non_tty_fails_cleanly(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_team",
                "--repo-root",
                str(repo_root),
                "run-requirement",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "run-requirement requires --message or --session-id when stdin/stdout are not interactive.",
            result.stderr + result.stdout,
        )
        self.assertNotIn("Traceback", result.stderr + result.stdout)

    def test_run_requirement_interactive_tty_walks_through_all_gates(self) -> None:
        from agent_team.cli import main

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            stdin = TtyStringIO("写个js文件，并打印hello world\ny\ny\ny\ny\ny\n")
            stdout = TtyStringIO()
            with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
                exit_code = main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--state-root",
                        temp_dir,
                        "run-requirement",
                        "--executor",
                        "dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("[1/5 Product] 生成需求方案中", output)
            self.assertIn("文档:", output)
            self.assertIn("PRD:", output)
            self.assertIn("Technical Plan:", output)
            self.assertIn("Session completed.", output)
            session_line = next(line for line in output.splitlines() if line.startswith("session_id: "))
            session_id = session_line.split(": ", 1)[1]
            session_dir = Path(temp_dir) / session_id
            self.assertTrue((session_dir / "prd.md").exists())
            self.assertTrue((session_dir / "technical_plan.md").exists())

    def test_run_requirement_interactive_auto_skips_intermediate_prompts_only(self) -> None:
        from agent_team.cli import main

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            stdin = TtyStringIO("写个js文件，并打印hello world\ny\nq\n")
            stdout = TtyStringIO()
            with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
                exit_code = main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--state-root",
                        temp_dir,
                        "run-requirement",
                        "--executor",
                        "dry-run",
                        "--auto",
                    ]
                )

            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("[1/5 Product] 生成需求方案中", output)
            self.assertIn("--auto 已启用，将自动通过 TechPlan 并进入 Dev。", output)
            self.assertIn("--auto 已启用，将自动通过 Dev 并进入 QA。", output)
            self.assertIn("--auto 已启用，将自动通过 QA 并进入 Acceptance。", output)
            self.assertIn("--auto 已启用，将自动通过 Acceptance 并完成交付。", output)
            self.assertIn("--auto 将自动记录最终通过", output)
            self.assertIn("--auto: 已自动通过 TechPlan，进入 Dev。", output)
            self.assertIn("--auto: 已自动通过 Dev，进入 QA。", output)
            self.assertIn("--auto: 已自动通过 QA，进入 Acceptance。", output)
            self.assertIn("--auto: 已自动通过 Acceptance，进入 完成交付。", output)
            self.assertIn("Session completed.", output)
            self.assertNotIn("[y] 通过，进入开发实现", output)
            self.assertNotIn("请打开技术方案文档确认实现路径和验证方式是否通过。", output)
            self.assertNotIn("请打开实现文档确认代码改动和自检结果是否通过。", output)
            self.assertNotIn("请打开 QA 报告确认验证结果是否通过。", output)
            self.assertNotIn("[y] 通过，完成交付", output)
            self.assertNotIn("等待最终人工决策", output)
            self.assertLess(output.index("--auto: 已自动通过 TechPlan，进入 Dev。"), output.index("[3/5 Dev]"))
            self.assertLess(output.index("--auto: 已自动通过 Dev，进入 QA。"), output.index("[4/5 QA]"))
            self.assertLess(output.index("--auto: 已自动通过 QA，进入 Acceptance。"), output.index("[5/5 Acceptance]"))
            session_line = next(line for line in output.splitlines() if line.startswith("session_id: "))
            session_id = session_line.split(": ", 1)[1]
            session_dir = Path(temp_dir) / session_id
            self.assertTrue((session_dir / "technical_plan.md").exists())
            self.assertTrue((session_dir / "implementation.md").exists())
            self.assertTrue((session_dir / "qa_report.md").exists())
            self.assertTrue((session_dir / "acceptance_report.md").exists())

    def test_run_requirement_acceptance_prompt_does_not_reprint_menu_after_invalid_input(self) -> None:
        from agent_team.cli import main

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            stdin = TtyStringIO("写个js文件，并打印hello world\ny\ny\ny\ny\n\nbad\nq\n")
            stdout = TtyStringIO()
            with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
                exit_code = main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--state-root",
                        temp_dir,
                        "run-requirement",
                        "--executor",
                        "dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertEqual(output.count("[y] 通过，完成交付"), 1)
            self.assertEqual(output.count("[n] 不通过"), 1)
            self.assertEqual(output.count("请输入 y / n / e / p / q。"), 2)
            self.assertIn("Session saved.", output)

    def test_run_requirement_interactive_tty_waits_on_blocked_stage_instead_of_exiting(self) -> None:
        from agent_team.cli import main

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            worker_path = Path(temp_dir) / "blocked_worker.py"
            worker_path.write_text(
                "import sys\n"
                "print('blocked stdout')\n"
                "print('blocked stderr', file=sys.stderr)\n"
                "sys.exit(1)\n"
            )
            stdin = TtyStringIO("p\nq\n")
            stdout = TtyStringIO()
            with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
                exit_code = main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--state-root",
                        temp_dir,
                        "run-requirement",
                        "--message",
                        "写个js文件，并打印hello world",
                        "--executor",
                        "command",
                        "--executor-command",
                        f"{sys.executable} {worker_path}",
                    ]
                )

            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("当前阶段执行被阻塞", output)
            self.assertIn("诊断信息:", output)
            self.assertIn("Session saved.", output)

    def test_run_requirement_dry_run_can_drive_to_acceptance_human_gate(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run-requirement",
                    "--message",
                    "执行这个需求：做一个 runtime 强制驱动流程",
                    "--executor",
                    "dry-run",
                    "--auto-approve-product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("runtime_driver_status: waiting_human", result.stdout)
            self.assertIn("current_state: WaitForHumanDecision", result.stdout)
            self.assertIn("acceptance_status: recommended_go", result.stdout)
            output_lines = [line for line in result.stdout.splitlines() if ": " in line]
            output_map = dict(line.split(": ", 1) for line in output_lines)
            session_id = output_map["session_id"]
            session_dir = Path(temp_dir) / session_id
            self.assertTrue((session_dir / "prd.md").exists())
            self.assertTrue((session_dir / "implementation.md").exists())
            self.assertTrue((session_dir / "qa_report.md").exists())
            self.assertTrue((session_dir / "acceptance_report.md").exists())
            self.assertTrue((session_dir / "stage_runs" / "acceptance-run-1.json").exists())

    def test_run_requirement_dry_run_can_record_final_human_decision(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run-requirement",
                    "--message",
                    "执行这个需求：做一个 runtime 强制驱动流程",
                    "--executor",
                    "dry-run",
                    "--auto-approve-product",
                    "--auto-final-decision",
                    "go",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("runtime_driver_status: done", result.stdout)
            self.assertIn("current_state: Done", result.stdout)
            self.assertIn("human_decision: go", result.stdout)

    def test_run_requirement_command_executor_receives_stage_environment(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            worker_path = Path(temp_dir) / "stage_worker.py"
            worker_path.write_text(
                "import json, os, sys\n"
                "print('worker stdout')\n"
                "print('worker stderr', file=sys.stderr)\n"
                "contract = json.loads(open(os.environ['AGENT_TEAM_CONTRACT_PATH']).read())\n"
                "payload = {\n"
                "  'session_id': os.environ['AGENT_TEAM_SESSION_ID'],\n"
                "  'stage': os.environ['AGENT_TEAM_STAGE'],\n"
                "  'status': 'completed',\n"
                "  'artifact_name': contract['required_outputs'][0],\n"
                "  'artifact_content': '# PRD\\n\\n## Acceptance Criteria\\n- Command executor ran.\\n',\n"
                "  'contract_id': contract['contract_id'],\n"
                "  'journal': 'command executor wrote the product bundle',\n"
                "  'evidence': [{'name': 'explicit_acceptance_criteria', 'kind': 'report', 'summary': 'criteria present'}],\n"
                "  'summary': 'command executor completed Product'\n"
                "}\n"
                "open(os.environ['AGENT_TEAM_RESULT_BUNDLE'], 'w').write(json.dumps(payload))\n"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run-requirement",
                    "--message",
                    "执行这个需求：验证 command executor",
                    "--executor",
                    "command",
                    "--executor-command",
                    f"{sys.executable} {worker_path}",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("runtime_driver_status: waiting_human", result.stdout)
            output_lines = [line for line in result.stdout.splitlines() if ": " in line]
            session_id = dict(line.split(": ", 1) for line in output_lines)["session_id"]
            session_dir = Path(temp_dir) / session_id
            self.assertIn("Command executor ran.", (session_dir / "prd.md").read_text())
            self.assertIn("worker stdout", (session_dir / "stage_runs" / "product-run-1_stdout.txt").read_text())
            self.assertIn("worker stderr", (session_dir / "stage_runs" / "product-run-1_stderr.txt").read_text())

    def test_start_session_uses_repo_local_agent_team_state_root_by_default(self) -> None:
        raw_message = "执行这个需求：做一个 harness-first workflow"

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "start-session",
                    "--message",
                    raw_message,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            output_lines = [line for line in result.stdout.splitlines() if ":" in line]
            artifact_dir = Path(dict(line.split(": ", 1) for line in output_lines)["artifact_dir"])
            self.assertEqual(artifact_dir.parent, repo_root / ".agent-team")
            self.assertTrue(artifact_dir.exists())

    def test_current_stage_prints_session_summary_fields(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        raw_message = "执行这个需求：做一个 harness-first workflow"

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    raw_message,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            output_lines = [line for line in bootstrap.stdout.splitlines() if ":" in line]
            session_id = dict(line.split(": ", 1) for line in output_lines)["session_id"]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "current-stage",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("current_state: Intake", result.stdout)
            self.assertIn("current_stage: Intake", result.stdout)
            self.assertIn("human_decision: pending", result.stdout)

    def test_board_snapshot_outputs_all_workspace_board_json(self) -> None:
        from agent_team.workspace_metadata import refresh_workspace_metadata

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as codex_home:
            env = os.environ.copy()
            env["CODEX_HOME"] = codex_home
            state_root = Path(codex_home) / "agent-team" / "workspaces" / "cli-board-test"
            start_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    str(state_root),
                    "start-session",
                    "--message",
                    "执行这个需求：做一个只读看板",
                ],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(start_result.returncode, 0)
            refresh_workspace_metadata(state_root=state_root, repo_root=repo_root)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "board-snapshot",
                    "--all-workspaces",
                ],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["stats"]["projects"], 1)
            self.assertEqual(payload["stats"]["sessions"], 1)
            self.assertEqual(payload["projects"][0]["project_name"], repo_root.name)

    def test_panel_snapshot_prints_json_for_latest_session(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        raw_message = "执行这个需求：做一个带面板的 workflow"

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    raw_message,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            output_lines = [line for line in bootstrap.stdout.splitlines() if ":" in line]
            session_id = dict(line.split(": ", 1) for line in output_lines)["session_id"]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "panel-snapshot",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["session"]["session_id"], session_id)
            self.assertEqual(payload["state"]["current_state"], "Intake")
            self.assertEqual(payload["events"][0]["kind"], "session_created")

    def test_status_prints_user_friendly_project_role_and_status(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        raw_message = "执行这个需求：做一个可查询状态的 workflow"

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir) / ".agent-team"
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    str(state_root),
                    "start-session",
                    "--message",
                    raw_message,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            output_lines = [line for line in bootstrap.stdout.splitlines() if ":" in line]
            session_id = dict(line.split(": ", 1) for line in output_lines)["session_id"]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    str(state_root),
                    "status",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn(f"project: {repo_root.name}", result.stdout)
            self.assertIn("role: Intake", result.stdout)
            self.assertIn("status: in_progress", result.stdout)
            self.assertIn("status_path:", result.stdout)

    def test_build_stage_contract_outputs_machine_readable_json(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        raw_message = "执行这个需求：做一个 harness-first workflow"

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    raw_message,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            output_lines = [line for line in bootstrap.stdout.splitlines() if ":" in line]
            session_id = dict(line.split(": ", 1) for line in output_lines)["session_id"]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "build-stage-contract",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["stage"], "Product")
            self.assertIn("prd.md", payload["required_outputs"])
            self.assertIn("must_not_change_stage_order", payload["forbidden_actions"])
            self.assertIn("contract_id", payload)

    def test_build_execution_context_outputs_dev_context_json(self) -> None:
        from agent_team.models import EvidenceItem, StageResultEnvelope
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session(
                "Build a runtime-controlled Dev handoff.",
                runtime_mode="harness",
            )
            stage_record = store.record_stage_result(
                session.session_id,
                StageResultEnvelope(
                    session_id=session.session_id,
                    contract_id="product-contract",
                    stage="Product",
                    status="completed",
                    artifact_name="prd.md",
                    artifact_content="# Product PRD\n\n## Acceptance Criteria\n- Verify the handoff.\n",
                    journal="# Product Journal\n",
                    evidence=[
                        EvidenceItem(
                            name="explicit_acceptance_criteria",
                            kind="report",
                            summary="Acceptance criteria documented.",
                        )
                    ],
                    summary="Drafted PRD",
                ),
            )
            summary = store.load_workflow_summary(session.session_id)
            summary.artifact_paths["product"] = str(stage_record.artifact_path)
            store.save_workflow_summary(session, summary)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "build-execution-context",
                    "--session-id",
                    session.session_id,
                    "--stage",
                    "Dev",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["stage"], "Dev")
            self.assertEqual(payload["required_outputs"], ["implementation.md"])
            self.assertIn("contract_id", payload)

    def test_submit_stage_result_requires_active_stage_run(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个带阶段门禁的流程",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            session_id = dict(
                line.split(": ", 1) for line in bootstrap.stdout.splitlines() if ":" in line
            )["session_id"]

            contract_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "build-stage-contract",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(contract_result.returncode, 0)
            contract_payload = json.loads(contract_result.stdout)

            bundle = Path(temp_dir) / "product_bundle_without_run.json"
            bundle.write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "contract_id": contract_payload["contract_id"],
                        "stage": "Product",
                        "status": "completed",
                        "artifact_name": "prd.md",
                        "artifact_content": "# Product PRD\n\n## Acceptance Criteria\n- Verify gate.\n",
                        "journal": "# Product Journal\n",
                        "findings": [],
                        "evidence": [evidence("explicit_acceptance_criteria", summary="Acceptance criteria documented.")],
                        "summary": "Drafted PRD",
                    }
                )
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "submit-stage-result",
                    "--session-id",
                    session_id,
                    "--bundle",
                    str(bundle),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No active stage run", result.stderr + result.stdout)

    def test_acquire_submit_verify_product_moves_to_ceo_wait(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个带阶段门禁的流程",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            session_id = dict(
                line.split(": ", 1) for line in bootstrap.stdout.splitlines() if ":" in line
            )["session_id"]

            contract_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "build-stage-contract",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(contract_result.returncode, 0)
            contract_payload = json.loads(contract_result.stdout)

            acquire_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "acquire-stage-run",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(acquire_result.returncode, 0)
            self.assertIn("run_state: RUNNING", acquire_result.stdout)

            bundle = Path(temp_dir) / "product_bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "contract_id": contract_payload["contract_id"],
                        "stage": "Product",
                        "status": "completed",
                        "artifact_name": "prd.md",
                        "artifact_content": "# Product PRD\n\n## Acceptance Criteria\n- Verify gate.\n",
                        "journal": "# Product Journal\n",
                        "findings": [],
                        "evidence": [evidence("explicit_acceptance_criteria", summary="Acceptance criteria documented.")],
                        "summary": "Drafted PRD",
                    }
                )
            )

            submit_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "submit-stage-result",
                    "--session-id",
                    session_id,
                    "--bundle",
                    str(bundle),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(submit_result.returncode, 0)
            self.assertIn("run_state: SUBMITTED", submit_result.stdout)
            self.assertNotIn("current_state: WaitForCEOApproval", submit_result.stdout)

            verify_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "verify-stage-result",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify_result.returncode, 0)
            self.assertIn("gate_status: PASSED", verify_result.stdout)
            self.assertIn("current_state: WaitForCEOApproval", verify_result.stdout)

    def test_step_reports_verify_when_candidate_is_submitted(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个带阶段门禁的流程",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            session_id = dict(
                line.split(": ", 1) for line in bootstrap.stdout.splitlines() if ":" in line
            )["session_id"]

            acquire_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "acquire-stage-run",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(acquire_result.returncode, 0)

            contract_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "build-stage-contract",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            contract_payload = json.loads(contract_result.stdout)

            bundle = Path(temp_dir) / "submitted_product_bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "contract_id": contract_payload["contract_id"],
                        "stage": "Product",
                        "status": "completed",
                        "artifact_name": "prd.md",
                        "artifact_content": "# Product PRD\n\n## Acceptance Criteria\n- Verify gate.\n",
                        "journal": "# Product Journal\n",
                        "findings": [],
                        "evidence": [evidence("explicit_acceptance_criteria", summary="Acceptance criteria documented.")],
                        "summary": "Drafted PRD",
                    }
                )
            )

            submit_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "submit-stage-result",
                    "--session-id",
                    session_id,
                    "--bundle",
                    str(bundle),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(submit_result.returncode, 0)

            step_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "step",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(step_result.returncode, 0)
            self.assertIn("next_action: verify-stage-result", step_result.stdout)

    def test_step_reports_contract_requirements_before_acquire(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个带阶段门禁的流程",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            session_id = dict(
                line.split(": ", 1) for line in bootstrap.stdout.splitlines() if ":" in line
            )["session_id"]

            step_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "step",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(step_result.returncode, 0)
            self.assertIn("next_stage: Product", step_result.stdout)
            self.assertIn("required_outputs: prd.md", step_result.stdout)
            self.assertIn("required_evidence: explicit_acceptance_criteria", step_result.stdout)
            self.assertIn("contract_id:", step_result.stdout)

    def test_step_reports_running_run_requirements_after_acquire(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个带阶段门禁的流程",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            session_id = dict(
                line.split(": ", 1) for line in bootstrap.stdout.splitlines() if ":" in line
            )["session_id"]

            acquire_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "acquire-stage-run",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(acquire_result.returncode, 0)

            step_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "step",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(step_result.returncode, 0)
            self.assertIn("run_state: RUNNING", step_result.stdout)
            self.assertIn("required_outputs: prd.md", step_result.stdout)
            self.assertIn("required_evidence: explicit_acceptance_criteria", step_result.stdout)

    def test_submit_stage_result_rejects_bundle_for_unexpected_stage(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个带阶段门禁的流程",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            session_id = dict(
                line.split(": ", 1) for line in bootstrap.stdout.splitlines() if ":" in line
            )["session_id"]

            acquire_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "acquire-stage-run",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(acquire_result.returncode, 0)

            wrong_bundle = Path(temp_dir) / "wrong_dev_bundle.json"
            wrong_bundle.write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "contract_id": "contract-wrong",
                        "stage": "Dev",
                        "status": "completed",
                        "artifact_name": "implementation.md",
                        "artifact_content": "# Implementation\n",
                        "journal": "# Dev Journal\n",
                        "findings": [],
                        "evidence": [evidence("self_verification", kind="command", summary="Self verification completed.")],
                        "summary": "Dev attempted to skip Product",
                    }
                )
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "submit-stage-result",
                    "--session-id",
                    session_id,
                    "--bundle",
                    str(wrong_bundle),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Expected active stage Product", result.stderr + result.stdout)

    def test_submit_stage_result_requires_matching_contract_id(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个带 contract guard 的流程",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            session_id = dict(
                line.split(": ", 1) for line in bootstrap.stdout.splitlines() if ":" in line
            )["session_id"]

            contract_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "build-stage-contract",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(contract_result.returncode, 0)
            contract_payload = json.loads(contract_result.stdout)

            acquire_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "acquire-stage-run",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(acquire_result.returncode, 0)

            wrong_contract_bundle = Path(temp_dir) / "product_bundle_wrong_contract.json"
            wrong_contract_bundle.write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "contract_id": "contract-wrong",
                        "stage": "Product",
                        "status": "completed",
                        "artifact_name": "prd.md",
                        "artifact_content": "# Product PRD\n\n## Acceptance Criteria\n- Verify gate.\n",
                        "journal": "# Product Journal\n",
                        "findings": [],
                        "evidence": [evidence("explicit_acceptance_criteria", summary="Acceptance criteria documented.")],
                        "summary": "Drafted PRD",
                    }
                )
            )

            wrong_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "submit-stage-result",
                    "--session-id",
                    session_id,
                    "--bundle",
                    str(wrong_contract_bundle),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(wrong_result.returncode, 0)
            self.assertIn("contract_id", wrong_result.stderr + wrong_result.stdout)

            correct_bundle = Path(temp_dir) / "product_bundle_correct_contract.json"
            correct_bundle.write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "contract_id": contract_payload["contract_id"],
                        "stage": "Product",
                        "status": "completed",
                        "artifact_name": "prd.md",
                        "artifact_content": "# Product PRD\n\n## Acceptance Criteria\n- Verify gate.\n",
                        "journal": "# Product Journal\n",
                        "findings": [],
                        "evidence": [evidence("explicit_acceptance_criteria", summary="Acceptance criteria documented.")],
                        "summary": "Drafted PRD",
                    }
                )
            )

            correct_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "submit-stage-result",
                    "--session-id",
                    session_id,
                    "--bundle",
                    str(correct_bundle),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(correct_result.returncode, 0)
            self.assertIn("run_state: SUBMITTED", correct_result.stdout)

            verify_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "verify-stage-result",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(verify_result.returncode, 0)
            self.assertIn("current_state: WaitForCEOApproval", verify_result.stdout)

    def test_record_human_decision_routes_wait_state_to_dev(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            start_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个 harness-first workflow",
                    "--initiator",
                    "human",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(start_result.returncode, 0)
            output_lines = [line for line in start_result.stdout.splitlines() if ":" in line]
            session_id = dict(line.split(": ", 1) for line in output_lines)["session_id"]

            contract_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "build-stage-contract",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(contract_result.returncode, 0)
            contract_payload = json.loads(contract_result.stdout)

            acquire_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "acquire-stage-run",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(acquire_result.returncode, 0)

            product_bundle = Path(temp_dir) / "product_bundle.json"
            product_bundle.write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "contract_id": contract_payload["contract_id"],
                        "stage": "Product",
                        "status": "completed",
                        "artifact_name": "prd.md",
                        "artifact_content": "# Product PRD\n\n## Acceptance Criteria\n- Verify the harness.\n",
                        "journal": "# Product Journal\n",
                        "findings": [],
                        "evidence": [evidence("explicit_acceptance_criteria", summary="Acceptance criteria documented.")],
                        "summary": "Drafted PRD",
                    }
                )
            )

            submit_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "submit-stage-result",
                    "--session-id",
                    session_id,
                    "--bundle",
                    str(product_bundle),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(submit_result.returncode, 0)

            verify_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "verify-stage-result",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify_result.returncode, 0)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "record-human-decision",
                    "--session-id",
                    session_id,
                    "--decision",
                    "go",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("current_state: Dev", result.stdout)
            self.assertIn("current_stage: Dev", result.stdout)
            self.assertIn("execution_context:", result.stdout)
            context_path = Path(temp_dir) / session_id / "execution_context" / "dev_round_1.json"
            self.assertTrue(context_path.exists())
            context_payload = json.loads(context_path.read_text())
            self.assertEqual(context_payload["stage"], "Dev")
            self.assertIn("Verify the harness.", context_payload["approved_prd_summary"])

    def test_record_human_decision_rejects_agent_initiated_session(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("做一个等待人工确认的流程", initiator="agent")
            store.save_workflow_summary(
                session,
                WorkflowSummary(
                    session_id=session.session_id,
                    runtime_mode="session_bootstrap",
                    current_state="WaitForCEOApproval",
                    current_stage="ProductDraft",
                    prd_status="drafted",
                    human_decision="pending",
                    artifact_paths={"workflow_summary": str(session.artifact_dir / "workflow_summary.md")},
                ),
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "record-human-decision",
                    "--session-id",
                    session.session_id,
                    "--decision",
                    "go",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Human decisions are reserved for human-initiated sessions", result.stderr + result.stdout)

    def test_start_session_persists_initiator(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个 human initiated workflow",
                    "--initiator",
                    "human",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            session_id = dict(
                line.split(": ", 1) for line in result.stdout.splitlines() if ":" in line
            )["session_id"]
            payload = json.loads((Path(temp_dir) / session_id / "session.json").read_text())
            self.assertEqual(payload["initiator"], "human")

    def test_record_feedback_persists_learning_and_feedback_metadata(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个支持反馈回流的流程",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(bootstrap.returncode, 0)
            output_lines = [line for line in bootstrap.stdout.splitlines() if ":" in line]
            session_id = dict(line.split(": ", 1) for line in output_lines)["session_id"]

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "record-feedback",
                    "--session-id",
                    session_id,
                    "--source-stage",
                    "Acceptance",
                    "--target-stage",
                    "Dev",
                    "--issue",
                    "User reported an unhandled empty state.",
                    "--lesson",
                    "Cover empty states in product-level validation.",
                    "--context-update",
                    "Review empty-state behavior before handoff.",
                    "--skill-update",
                    "Require visible empty-state evidence before reporting success.",
                    "--severity",
                    "high",
                    "--evidence-kind",
                    "human_feedback",
                    "--required-evidence",
                    "runtime_screenshot",
                    "--required-evidence",
                    "overlay_diff",
                    "--completion-signal",
                    "Attach runtime_screenshot and overlay_diff evidence before closing the issue.",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("recorded_feedback:", result.stdout)

            feedback_lines = [line for line in result.stdout.splitlines() if ":" in line]
            feedback_path = Path(dict(line.split(": ", 1) for line in feedback_lines)["recorded_feedback"])
            lessons_path = Path(temp_dir) / "memory" / "Dev" / "lessons.md"
            session_json_path = Path(temp_dir) / session_id / "session.json"

            self.assertTrue(feedback_path.exists())
            self.assertTrue(lessons_path.exists())
            self.assertTrue(session_json_path.exists())
            self.assertIn("User reported an unhandled empty state.", lessons_path.read_text())
            feedback_payload = json.loads(feedback_path.read_text())
            self.assertEqual(feedback_payload["evidence_kind"], "human_feedback")
            self.assertEqual(
                feedback_payload["required_evidence"],
                ["runtime_screenshot", "overlay_diff"],
            )
            self.assertIn("Attach runtime_screenshot and overlay_diff evidence", feedback_payload["completion_signal"])
            session_payload = json.loads(session_json_path.read_text())
            self.assertIn("feedback_records", session_payload)
            self.assertEqual(len(session_payload["feedback_records"]), 1)

    def test_record_feedback_can_apply_rework_decision_in_same_command(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("做一个支持验收回流的流程")
            store.save_workflow_summary(
                session,
                WorkflowSummary(
                    session_id=session.session_id,
                    runtime_mode="session_bootstrap",
                    current_state="WaitForHumanDecision",
                    current_stage="Acceptance",
                    prd_status="drafted",
                    dev_status="completed",
                    qa_status="passed",
                    acceptance_status="recommended_go",
                    human_decision="pending",
                    artifact_paths={"workflow_summary": str(session.artifact_dir / "workflow_summary.md")},
                ),
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "record-feedback",
                    "--session-id",
                    session.session_id,
                    "--source-stage",
                    "Acceptance",
                    "--target-stage",
                    "Dev",
                    "--issue",
                    "Acceptance found a missed Figma parity issue.",
                    "--severity",
                    "high",
                    "--apply-rework",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("recorded_feedback:", result.stdout)
            self.assertIn("current_state: Dev", result.stdout)
            self.assertIn("current_stage: Dev", result.stdout)
            self.assertIn("human_decision: rework", result.stdout)

if __name__ == "__main__":
    unittest.main()
