import argparse
import io
import json
import subprocess
import sys
import unittest
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


def _session_id_from_stdout(stdout: str) -> str:
    return dict(line.split(": ", 1) for line in stdout.splitlines() if ": " in line)["session_id"]


class CliTests(unittest.TestCase):
    def test_cli_without_command_exits_with_argparse_error_instead_of_traceback(self) -> None:
        result = subprocess.run([sys.executable, "-m", "agent_team"], capture_output=True, text=True, check=False)

        self.assertEqual(result.returncode, 2)
        self.assertIn("the following arguments are required: command", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_help_exits_successfully(self) -> None:
        result = subprocess.run([sys.executable, "-m", "agent_team", "--help"], capture_output=True, text=True, check=False)

        self.assertEqual(result.returncode, 0)
        self.assertIn("init", result.stdout)
        self.assertIn("update", result.stdout)
        self.assertIn("run", result.stdout)
        self.assertIn("panel", result.stdout)
        self.assertIn("status", result.stdout)
        self.assertIn("continue", result.stdout)
        self.assertIn("next", result.stdout)
        self.assertIn("go", result.stdout)
        self.assertIn("fix", result.stdout)
        self.assertIn("detail", result.stdout)
        self.assertNotIn("agent-run", result.stdout)

    def test_project_scripts_include_short_agt_alias(self) -> None:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"

        payload = pyproject.read_text()

        self.assertIn('agent-team = "agent_team.cli:main"', payload)
        self.assertIn('agt = "agent_team.cli:main"', payload)

    def test_legacy_run_requirement_alias_still_opens_run_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "run-requirement", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("usage: agent-team run", result.stdout)
        self.assertIn("--message", result.stdout)

    def test_init_bootstraps_state_project_structure_and_five_layer_skip_record(self) -> None:
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
            self.assertIn("executor_env_config:", result.stdout)
            self.assertIn("five_layer_classification_status: skipped", result.stdout)
            self.assertTrue((repo_root / ".agt" / "memory").is_dir())
            self.assertTrue((repo_root / ".agt" / "executor-env.json").is_file())
            self.assertTrue((repo_root / "agt-control" / "project" / "doc-map.json").is_file())
            self.assertTrue((repo_root / "agt-control" / "project" / "five-layer" / "classification-prompt.md").is_file())
            self.assertTrue((repo_root / "agt-control" / "project" / "five-layer" / "classification-run.json").is_file())

    def test_update_reports_and_preserves_existing_project_files(self) -> None:
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            project_dir = repo_root / "agent-team" / "project"
            roles_dir = project_dir / "roles"
            roles_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "context.md").write_text("# Custom Context\n")
            (project_dir / "rules.md").write_text("# Custom Rules\n")
            (project_dir / "doc-map.json").write_text(json.dumps({"product_definition": "docs/requirements"}))
            (roles_dir / "dev.context.md").write_text("# Legacy Dev\n")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "update",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Agent Team 项目配置更新", result.stdout)
            self.assertIn("dry_run: false", result.stdout)
            self.assertIn("已创建", result.stdout)
            self.assertIn("已保留", result.stdout)
            self.assertEqual((project_dir / "context.md").read_text(), "# Custom Context\n")
            self.assertEqual((project_dir / "rules.md").read_text(), "# Custom Rules\n")
            self.assertTrue((roles_dir / "dev.context.md").exists())
            doc_map = json.loads((project_dir / "doc-map.json").read_text())
            self.assertEqual(doc_map["product_definition"], "docs/requirements")
            self.assertEqual(doc_map["project_runtime"], "docs/project-runtime")

    def test_update_dry_run_does_not_write_files(self) -> None:
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            project_dir = repo_root / "agent-team" / "project"
            project_dir.mkdir(parents=True)
            (project_dir / "doc-map.json").write_text(json.dumps({"requirements": "docs/requirements"}))

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "update",
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("dry_run: true", result.stdout)
            self.assertIn("预览更新", result.stdout)
            self.assertEqual((project_dir / "doc-map.json").read_text(), json.dumps({"requirements": "docs/requirements"}))
            self.assertFalse((project_dir / "context.md").exists())
            self.assertFalse((repo_root / ".agt").exists())

    def test_run_help_lists_skill_overrides(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "run", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("--with-skills", result.stdout)
        self.assertIn("--skip-skills", result.stdout)
        self.assertIn("--skills-empty", result.stdout)

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
                "Implementation",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("plan", result.stdout)
        self.assertIn("built-in", result.stdout)

    def test_skill_show_includes_source_reference(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_team",
                "--repo-root",
                str(repo_root),
                "skill",
                "show",
                "plan",
                "--stage",
                "Implementation",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("source_ref:", result.stdout)
        self.assertIn("path:", result.stdout)

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
            self.assertIn("implementation:", result.stdout)
            self.assertIn("productdefinition:", result.stdout)
            self.assertTrue((repo_root / ".agt" / "skill-preferences.yaml").exists())

    def test_run_requirement_dry_run_stops_at_product_definition_approval_gate(self) -> None:
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
                    "run",
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
            self.assertIn("current_state: WaitForProductDefinitionApproval", result.stdout)
            self.assertIn("current_stage: ProductDefinition", result.stdout)
            self.assertIn("next_action: approve", result.stdout)
            session_id = _session_id_from_stdout(result.stdout)
            session_dir = Path(temp_dir) / session_id
            runtime_session_dir = Path(temp_dir) / "_runtime" / "sessions" / session_id
            self.assertTrue((session_dir / "route-packet.json").exists())
            self.assertTrue((session_dir / "product-definition-delta.md").exists())
            self.assertFalse((session_dir / "technical-design.md").exists())
            self.assertTrue(
                (
                    runtime_session_dir
                    / "roles"
                    / "product-definition"
                    / "attempt-001"
                    / "stage-results"
                    / "product-definition-stage-result.json"
                ).exists()
            )

    def test_run_requirement_command_executor_skips_product_definition_gate_when_route_marks_no_l1_delta(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            worker_path = Path(temp_dir) / "skip_product_definition_worker.py"
            worker_path.write_text(
                "import json, os\n"
                "from pathlib import Path\n"
                "stage = os.environ['AGENT_TEAM_STAGE']\n"
                "payloads = {\n"
                "  'Route': {\n"
                "    'status': 'completed',\n"
                "    'artifact_content': json.dumps({\n"
                "      'affected_layers': ['L2', 'L3'],\n"
                "      'required_stages': ['TechnicalDesign', 'Implementation', 'Verification', 'GovernanceReview', 'Acceptance', 'SessionHandoff'],\n"
                "      'stage_decisions': {'ProductDefinition': {'decision': 'skipped', 'reason': 'no_l1_delta'}},\n"
                "      'verification_mode': 'static_only',\n"
                "      'baseline_sources': [],\n"
                "      'red_lines': [],\n"
                "      'unresolved_questions': []\n"
                "    }),\n"
                "    'journal': '',\n"
                "    'findings': [],\n"
                "    'evidence': [{'name': 'route_classification', 'kind': 'artifact', 'summary': 'routed', 'artifact_path': '', 'command': '', 'exit_code': None, 'producer': 'test'}],\n"
                "    'suggested_next_owner': '',\n"
                "    'summary': 'route',\n"
                "    'acceptance_status': '',\n"
                "    'blocked_reason': ''\n"
                "  },\n"
                "  'TechnicalDesign': {\n"
                "    'status': 'completed',\n"
                "    'artifact_content': '# Technical Design\\n',\n"
                "    'journal': '',\n"
                "    'findings': [],\n"
                "    'evidence': [{'name': 'technical_design_plan', 'kind': 'report', 'summary': 'design', 'artifact_path': '', 'command': '', 'exit_code': None, 'producer': 'test'}],\n"
                "    'suggested_next_owner': '',\n"
                "    'summary': 'design',\n"
                "    'acceptance_status': '',\n"
                "    'blocked_reason': ''\n"
                "  }\n"
                "}\n"
                "Path(os.environ['AGENT_TEAM_RESULT_BUNDLE']).write_text(json.dumps(payloads[stage]))\n"
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
                    "run",
                    "--message",
                    "执行这个需求：Route 跳过 ProductDefinition",
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
            self.assertIn("current_state: WaitForTechnicalDesignApproval", result.stdout)
            self.assertIn("current_stage: TechnicalDesign", result.stdout)
            self.assertIn("product_definition: no_l1_delta (skipped approval gate; continue to next required stage)", result.stdout)
            self.assertNotIn("WaitForProductDefinitionApproval", result.stdout)
            self.assertIn("next_action: approve|rework|reject", result.stdout)
            session_id = _session_id_from_stdout(result.stdout)
            session_dir = Path(temp_dir) / session_id
            self.assertTrue((session_dir / "route-packet.json").exists())
            self.assertFalse((session_dir / "product-definition-delta.md").exists())
            self.assertTrue((session_dir / "technical-design.md").exists())

    def test_run_requirement_without_message_or_session_id_in_non_tty_fails_cleanly(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "--repo-root", str(repo_root), "run"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "run requires --message or --session-id when stdin/stdout are not interactive.",
            result.stderr + result.stdout,
        )
        self.assertNotIn("Traceback", result.stderr + result.stdout)

    def test_run_requirement_flow_progress_bar_animates_without_hash_dash_bar(self) -> None:
        from agent_team.cli import _render_flow_progress_bar, _render_running_progress_line

        first_frame = _render_flow_progress_bar(1, 9, phase=0)
        second_frame = _render_flow_progress_bar(1, 9, phase=1)
        first_line = _render_running_progress_line(stage="Route", completed=0, phase=0)
        second_line = _render_running_progress_line(stage="Route", completed=0, phase=1)

        self.assertNotEqual(first_frame, second_frame)
        self.assertNotEqual(first_line, second_line)
        self.assertNotIn("#", first_frame)
        self.assertNotIn("-", first_frame)
        self.assertIn(">", first_frame)
        self.assertTrue(first_frame.endswith("1/9"))
        self.assertTrue(first_line.startswith("◐ ["))
        self.assertTrue(second_line.startswith("◓ ["))
        self.assertIn("Route · 读取需求", first_line)
        self.assertIn("Route · 识别层级", second_line)
        self.assertIn(
            "Technical Design · 准备上下文",
            _render_running_progress_line(stage="TechnicalDesign", completed=3, phase=0, activity="准备上下文"),
        )

    def test_run_requirement_animation_wraps_interactive_stage_line(self) -> None:
        import time

        from agent_team.cli import _run_requirement_with_stage_animation

        stdout = TtyStringIO()
        with patch("sys.stdout", stdout):
            result = _run_requirement_with_stage_animation(
                stage="Route",
                completed=0,
                run=lambda: (time.sleep(0.18), "done")[1],
            )

        output = stdout.getvalue()
        self.assertEqual(result, "done")
        self.assertIn("\r◐ [", output)
        self.assertIn("[>", output)
        self.assertIn("Route", output)
        self.assertIn("\033[2K", output)

    def test_run_requirement_stage_banner_keeps_static_progress_for_non_tty(self) -> None:
        from agent_team.cli import _print_run_requirement_stage_banner

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            _print_run_requirement_stage_banner(stage="Route", completed=0)

        output = stdout.getvalue()
        self.assertIn("[1/9 Route] 路由需求和五层影响中", output)
        self.assertIn("进度: [", output)
        self.assertIn("-", output)
        self.assertNotIn("\033[2K", output)

    def test_run_requirement_interactive_tty_walks_through_all_human_gates(self) -> None:
        from agent_team.cli import main

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            stdin = TtyStringIO("写个js文件，并打印hello world\ny\ny\ny\n")
            stdout = TtyStringIO()
            with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
                exit_code = main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--state-root",
                        temp_dir,
                        "run",
                        "--executor",
                        "dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("[1/9 Route] 路由需求和五层影响中", output)
            self.assertIn("Product Definition Delta:", output)
            self.assertIn("Technical Design:", output)
            self.assertIn("Session Handoff:", output)
            self.assertIn("Session completed.", output)
            session_id = next(line for line in output.splitlines() if line.startswith("session_id: ")).split(": ", 1)[1]
            session_dir = Path(temp_dir) / session_id
            self.assertTrue((session_dir / "product-definition-delta.md").exists())
            self.assertTrue((session_dir / "technical-design.md").exists())
            self.assertTrue((session_dir / "session-handoff.md").exists())

    def test_run_requirement_interactive_auto_keeps_human_design_gate(self) -> None:
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
                        "run",
                        "--executor",
                        "dry-run",
                        "--auto",
                    ]
                )

            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("[1/9 Route] 路由需求和五层影响中", output)
            self.assertIn("[4/9 Technical Design] 生成 L2 技术设计中", output)
            self.assertIn("请选择下一步：", output)
            self.assertIn("Session saved.", output)
            self.assertNotIn("--auto: 已自动通过 Technical Design", output)
            session_id = next(line for line in output.splitlines() if line.startswith("session_id: ")).split(": ", 1)[1]
            session_dir = Path(temp_dir) / session_id
            self.assertTrue((session_dir / "technical-design.md").exists())
            self.assertFalse((session_dir / "implementation.md").exists())
            self.assertFalse((session_dir / "verification-report.md").exists())
            self.assertFalse((session_dir / "acceptance-report.md").exists())

    def test_run_requirement_session_handoff_prompt_does_not_reprint_menu_after_invalid_input(self) -> None:
        from agent_team.cli import main

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            stdin = TtyStringIO("写个js文件，并打印hello world\ny\ny\n\nbad\nq\n")
            stdout = TtyStringIO()
            with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
                exit_code = main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--state-root",
                        temp_dir,
                        "run",
                        "--executor",
                        "dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertEqual(output.count("  y) 通过最终交付，完成本次任务"), 1)
            self.assertEqual(output.count("  n) 不通过最终交付，结束为 no-go"), 1)
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
                        "run",
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
            self.assertIn("阻塞诊断:", output)
            self.assertIn("错误:", output)
            self.assertIn("问题:", output)
            self.assertIn("阻塞点:", output)
            self.assertIn("Invalid stage payload JSON", output)
            self.assertIn("诊断信息:", output)
            self.assertIn("Session saved.", output)

    def test_blocked_summary_splits_error_issue_and_blocker_details(self) -> None:
        from agent_team.cli import _print_run_requirement_blocked_summary
        from agent_team.models import EvidenceItem, Finding, GateResult, StageResultEnvelope
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("修复重复社群成员")
            run = store.create_stage_run(
                session_id=session.session_id,
                stage="Implementation",
                contract_id="contract-1",
                required_outputs=["implementation.md"],
                required_evidence=["self_verification"],
                worker="codex-exec",
            )
            stage_result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Implementation",
                status="blocked",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
                contract_id="contract-1",
                blocked_reason="端到端验收需要真实服务、数据库访问权限和脱敏 groupId。",
                findings=[
                    Finding(
                        source_stage="Implementation",
                        target_stage="Verification",
                        issue="端到端 API 到持久化数据验证未完成。",
                        severity="blocking",
                        required_evidence=[
                            "脱敏 groupId",
                            "/api/v1/group/people 前两页响应",
                        ],
                        completion_signal="需要用户提供脱敏 groupId、接口响应和数据库查询结果后才能关闭验收。",
                    )
                ],
                evidence=[
                    EvidenceItem(
                        name="self_verification",
                        kind="command",
                        summary="service 测试包存在既有构造函数参数数量不匹配。",
                        command="go test ./internal/app/group_pals/service",
                        exit_code=1,
                    )
                ],
            )
            submitted = store.submit_stage_run_result(run.run_id, stage_result)
            store.update_stage_run(
                submitted,
                state="BLOCKED",
                gate_result=GateResult(
                    status="BLOCKED",
                    reason=stage_result.blocked_reason,
                    findings=list(stage_result.findings),
                ),
                blocked_reason=stage_result.blocked_reason,
            )
            result = type(
                "Result",
                (),
                {
                    "gate_status": "BLOCKED",
                    "gate_reason": stage_result.blocked_reason,
                },
            )()

            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                _print_run_requirement_blocked_summary(
                    store=store,
                    session_id=session.session_id,
                    stage="Implementation",
                    result=result,
                )

            output = stdout.getvalue()
            self.assertIn("错误:", output)
            self.assertIn("Implementation 阶段没有推进：门禁判定为 BLOCKED。", output)
            self.assertIn("问题:", output)
            self.assertIn("端到端 API 到持久化数据验证未完成。", output)
            self.assertIn("验证命令失败（exit=1）：service 测试包存在既有构造函数参数数量不匹配。", output)
            self.assertIn("阻塞点:", output)
            self.assertIn("需要补充证据：脱敏 groupId", output)
            self.assertIn("修复失败命令后重新运行：go test ./internal/app/group_pals/service", output)
            self.assertIn("诊断来源:", output)
            self.assertIn("stage_run_id:", output)
            self.assertIn("attempt: 1", output)

    def test_passed_gate_caution_findings_are_reported_as_notes_not_blockers(self) -> None:
        from agent_team.cli import _print_run_requirement_blocked_summary
        from agent_team.models import Finding, GateResult, StageResultEnvelope
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("治理注意项")
            run = store.create_stage_run(
                session_id=session.session_id,
                stage="GovernanceReview",
                contract_id="contract-1",
                required_outputs=["governance-review.md"],
                required_evidence=["layer_governance_review"],
                worker="codex-exec",
            )
            finding = Finding(
                source_stage="GovernanceReview",
                target_stage="GovernanceReview",
                issue="五层边界说明已记录，后续继续观察。",
                severity="medium",
                required_evidence=["layer_governance_review"],
                completion_signal="note_recorded",
            )
            stage_result = StageResultEnvelope(
                session_id=session.session_id,
                stage="GovernanceReview",
                status="completed",
                artifact_name="governance-review.md",
                artifact_content="# Governance Review\n\n## Non-blocking Findings / Cautions\n- [medium] 五层边界说明已记录。\n",
                contract_id="contract-1",
                findings=[finding],
            )
            submitted = store.submit_stage_run_result(run.run_id, stage_result)
            store.update_stage_run(
                submitted,
                state="PASSED",
                gate_result=GateResult(status="PASSED", reason="passed with cautions", findings=[finding]),
            )
            result = type("Result", (), {"gate_status": "PASSED", "gate_reason": "passed with cautions"})()

            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                _print_run_requirement_blocked_summary(
                    store=store,
                    session_id=session.session_id,
                    stage="GovernanceReview",
                    result=result,
                )

            output = stdout.getvalue()
            self.assertIn("Governance Review gate 已通过，但状态未推进", output)
            self.assertIn("注意项:", output)
            self.assertIn("[medium] 五层边界说明已记录，后续继续观察。", output)
            self.assertIn("记录后续对齐证据：layer_governance_review", output)
            self.assertIn("记录信号：note_recorded", output)
            self.assertNotIn("需要补充证据：layer_governance_review", output)

    def test_blocked_next_step_points_users_to_alignment_questions(self) -> None:
        from agent_team.cli import _run_requirement_blocked_next_step_text, _run_requirement_next_step_text

        self.assertIn("product-definition-delta.md", _run_requirement_blocked_next_step_text("ProductDefinition"))
        self.assertIn("澄清问题", _run_requirement_blocked_next_step_text("ProductDefinition"))
        self.assertIn("technical-design.md", _run_requirement_blocked_next_step_text("TechnicalDesign"))
        self.assertIn("待确认问题", _run_requirement_blocked_next_step_text("TechnicalDesign"))
        self.assertIn("澄清问题", _run_requirement_next_step_text("ProductDefinition"))
        self.assertIn("待确认问题", _run_requirement_next_step_text("TechnicalDesign"))

    def test_skipped_product_definition_summary_and_next_step_explain_no_l1_delta(self) -> None:
        from agent_team.cli import _run_requirement_next_step_text, _run_requirement_stage_summary_lines
        from agent_team.models import WorkflowSummary

        summary = WorkflowSummary(
            session_id="session-1",
            runtime_mode="harness",
            current_state="WaitForTechnicalDesignApproval",
            current_stage="TechnicalDesign",
            stage_statuses={"Route": "completed", "ProductDefinition": "skipped", "TechnicalDesign": "drafted"},
            route_required_stages=["TechnicalDesign", "Implementation"],
            route_stage_decisions={"ProductDefinition": {"decision": "skipped", "reason": "no_l1_delta"}},
            verification_mode="static_only",
            product_definition_outcome="no_l1_delta",
        )

        summary_lines = _run_requirement_stage_summary_lines("TechnicalDesign", summary)
        next_step = _run_requirement_next_step_text("TechnicalDesign", summary)

        self.assertIn("无 L1 delta", summary_lines[0])
        self.assertIn("跳过 ProductDefinition 审批门", summary_lines[1])
        self.assertIn("no L1 delta", next_step)
        self.assertIn("跳过", next_step)
        self.assertIn("技术设计文档", next_step)

    def test_run_accepts_positional_requirement_message(self) -> None:
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
                    "run",
                    "执行这个需求：支持短命令入口",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("runtime_driver_status: waiting_human", result.stdout)
            self.assertIn("next_action: approve", result.stdout)

    def test_approve_uses_latest_session_by_default(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            run_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run",
                    "执行这个需求：测试 approve",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stderr)

            approve = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "approve",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(approve.returncode, 0, approve.stderr)
            self.assertIn("current_state: ProjectRuntime", approve.stdout)
            self.assertIn("human_decision: go", approve.stdout)

    def test_run_requirement_dry_run_stops_at_technical_design_gate_after_product_definition_go(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            product_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run",
                    "--message",
                    "执行这个需求：做一个 runtime 强制驱动流程",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(product_result.returncode, 0)
            session_id = _session_id_from_stdout(product_result.stdout)

            approve = subprocess.run(
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
            self.assertEqual(approve.returncode, 0)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run",
                    "--session-id",
                    session_id,
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("runtime_driver_status: waiting_human", result.stdout)
            self.assertIn("current_state: WaitForTechnicalDesignApproval", result.stdout)
            self.assertIn("current_stage: TechnicalDesign", result.stdout)
            session_dir = Path(temp_dir) / session_id
            self.assertTrue((session_dir / "product-definition-delta.md").exists())
            self.assertTrue((session_dir / "project-landing-delta.md").exists())
            self.assertTrue((session_dir / "technical-design.md").exists())
            self.assertFalse((session_dir / "implementation.md").exists())
            self.assertFalse((session_dir / "verification-report.md").exists())

    def test_run_requirement_dry_run_auto_stops_at_final_human_decision(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            product_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run",
                    "--message",
                    "执行这个需求：做一个 runtime 强制驱动流程",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(product_result.returncode, 0)
            session_id = _session_id_from_stdout(product_result.stdout)

            approve_product_definition = subprocess.run(
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
            self.assertEqual(approve_product_definition.returncode, 0)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run",
                    "--session-id",
                    session_id,
                    "--executor",
                    "dry-run",
                    "--auto",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("runtime_driver_status: waiting_human", result.stdout)
            self.assertIn("current_state: WaitForTechnicalDesignApproval", result.stdout)

            approve_technical_design = subprocess.run(
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
            self.assertEqual(approve_technical_design.returncode, 0)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run",
                    "--session-id",
                    session_id,
                    "--executor",
                    "dry-run",
                    "--auto",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("runtime_driver_status: waiting_human", result.stdout)
            self.assertIn("current_state: WaitForHumanDecision", result.stdout)
            self.assertIn("current_stage: SessionHandoff", result.stdout)
            self.assertIn("human_decision: pending", result.stdout)

    def test_run_requirement_command_executor_receives_stage_environment(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            worker_path = Path(temp_dir) / "stage_worker.py"
            worker_path.write_text(
                "import json, os, sys\n"
                "stage = os.environ['AGENT_TEAM_STAGE']\n"
                "print('worker stdout')\n"
                "print('worker stderr', file=sys.stderr)\n"
                "payloads = {\n"
                "  'Route': {'status': 'completed', 'artifact_content': '{\"affected_layers\":[\"L1\"],\"required_stages\":[\"ProductDefinition\",\"ProjectRuntime\",\"TechnicalDesign\",\"Implementation\",\"Verification\",\"GovernanceReview\",\"Acceptance\",\"SessionHandoff\"],\"stage_decisions\":{\"ProductDefinition\":{\"decision\":\"required\",\"reason\":\"l1_delta_pending_approval\"}},\"verification_mode\":\"static_only\",\"baseline_sources\":[],\"red_lines\":[],\"unresolved_questions\":[]}', 'journal': '', 'evidence': [{'name': 'route_classification', 'kind': 'artifact', 'summary': 'routed'}], 'summary': 'route'},\n"
                "  'ProductDefinition': {'status': 'completed', 'artifact_content': '# Product Definition Delta\\n', 'journal': '', 'evidence': [{'name': 'l1_classification', 'kind': 'artifact', 'summary': 'l1'}], 'summary': 'l1'},\n"
                "}\n"
                "payload = payloads[stage]\n"
                "payload.setdefault('findings', [])\n"
                "payload.setdefault('suggested_next_owner', '')\n"
                "payload.setdefault('acceptance_status', '')\n"
                "payload.setdefault('blocked_reason', '')\n"
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
                    "run",
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
            session_id = _session_id_from_stdout(result.stdout)
            session_dir = Path(temp_dir) / session_id
            runtime_session_dir = Path(temp_dir) / "_runtime" / "sessions" / session_id
            self.assertIn("Product Definition Delta", (session_dir / "product-definition-delta.md").read_text())
            self.assertIn(
                "worker stdout",
                (
                    runtime_session_dir
                    / "roles"
                    / "route"
                    / "attempt-001"
                    / "command-outputs"
                    / "route-command-stdout.txt"
                ).read_text(),
            )
            self.assertIn(
                "worker stderr",
                (
                    runtime_session_dir
                    / "roles"
                    / "route"
                    / "attempt-001"
                    / "command-outputs"
                    / "route-command-stderr.txt"
                ).read_text(),
            )

    def test_run_requirement_stage_report_prints_worktree_changes(self) -> None:
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            repo_root.mkdir()
            subprocess.run(["git", "init"], cwd=repo_root, capture_output=True, text=True, check=True)
            (repo_root / "existing.txt").write_text("clean baseline\n")
            subprocess.run(["git", "add", "existing.txt"], cwd=repo_root, capture_output=True, text=True, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Agent Team Test",
                    "-c",
                    "user.email=agent-team@example.invalid",
                    "commit",
                    "-m",
                    "init",
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            (repo_root / "existing.txt").write_text("dirty before stage\n")
            worker_path = root / "stage_worker.py"
            worker_path.write_text(
                "import json, os\n"
                "from pathlib import Path\n"
                "stage = os.environ['AGENT_TEAM_STAGE']\n"
                "repo = Path(os.environ['AGENT_TEAM_REPO_ROOT'])\n"
                "if stage == 'ProductDefinition':\n"
                "    (repo / 'existing.txt').write_text('dirty after stage\\n')\n"
                "    (repo / 'created.txt').write_text('created by stage\\n')\n"
                "payloads = {\n"
                "  'Route': {'status': 'completed', 'artifact_content': '{\"affected_layers\":[\"L1\"],\"required_stages\":[\"ProductDefinition\",\"ProjectRuntime\",\"TechnicalDesign\",\"Implementation\",\"Verification\",\"GovernanceReview\",\"Acceptance\",\"SessionHandoff\"],\"stage_decisions\":{\"ProductDefinition\":{\"decision\":\"required\",\"reason\":\"l1_delta_pending_approval\"}},\"verification_mode\":\"static_only\",\"baseline_sources\":[],\"red_lines\":[],\"unresolved_questions\":[]}', 'journal': '', 'evidence': [{'name': 'route_classification', 'kind': 'artifact', 'summary': 'routed'}], 'summary': 'route'},\n"
                "  'ProductDefinition': {'status': 'completed', 'artifact_content': '# Product Definition Delta\\n', 'journal': '', 'evidence': [{'name': 'l1_classification', 'kind': 'artifact', 'summary': 'l1'}], 'summary': 'l1'},\n"
                "}\n"
                "payload = payloads[stage]\n"
                "payload.setdefault('findings', [])\n"
                "payload.setdefault('suggested_next_owner', '')\n"
                "payload.setdefault('acceptance_status', '')\n"
                "payload.setdefault('blocked_reason', '')\n"
                "Path(os.environ['AGENT_TEAM_RESULT_BUNDLE']).write_text(json.dumps(payload))\n"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    str(root / "state"),
                    "run",
                    "--message",
                    "执行这个需求：验证 CLI 展示工作树改动",
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
        self.assertIn("本阶段改动:", result.stdout)
        self.assertIn("created.txt", result.stdout)
        self.assertIn("existing.txt", result.stdout)
        self.assertIn("执行前已 dirty", result.stdout)

    def test_panel_json_prints_snapshot(self) -> None:
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
                    "run",
                    "--message",
                    "执行这个需求：做一个带面板的 workflow",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            session_id = _session_id_from_stdout(bootstrap.stdout)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "panel",
                    "--session-id",
                    session_id,
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["session"]["session_id"], session_id)



    def test_short_human_commands_go_fix_and_detail(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir) / ".agent-team"
            store = StateStore(state_root)
            session = store.create_session("执行这个需求：短命令人类操作", initiator="human")
            store.save_workflow_summary(
                session,
                WorkflowSummary(
                    session_id=session.session_id,
                    runtime_mode="harness",
                    current_state="WaitForTechnicalDesignApproval",
                    current_stage="TechnicalDesign",
                    stage_statuses={"Route": "completed", "TechnicalDesign": "drafted"},
                    route_required_stages=["TechnicalDesign", "Verification", "GovernanceReview", "Acceptance", "SessionHandoff"],
                )
            )

            detail = subprocess.run(
                [sys.executable, "-m", "agent_team", "--repo-root", str(repo_root), "--state-root", str(state_root), "detail"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(detail.returncode, 0, detail.stderr)
            self.assertIn("AGT Continue", detail.stdout)
            self.assertIn("详情:", detail.stdout)

            fix = subprocess.run(
                [sys.executable, "-m", "agent_team", "--repo-root", str(repo_root), "--state-root", str(state_root), "fix", "设计里补边界说明"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(fix.returncode, 0, fix.stderr)
            self.assertIn("已记录返工意见", fix.stdout)
            updated = store.load_workflow_summary(session.session_id)
            self.assertEqual(updated.current_state, "TechnicalDesign")
            self.assertEqual(updated.stage_statuses["TechnicalDesign"], "rework_requested")

            store.save_workflow_summary(
                session,
                WorkflowSummary(
                    session_id=session.session_id,
                    runtime_mode="harness",
                    current_state="WaitForHumanDecision",
                    current_stage="SessionHandoff",
                    stage_statuses={"Route": "completed", "TechnicalDesign": "approved", "SessionHandoff": "completed"},
                    route_required_stages=["TechnicalDesign", "Verification", "GovernanceReview", "Acceptance", "SessionHandoff"],
                    acceptance_status="accepted",
                    human_decision="pending",
                )
            )
            go = subprocess.run(
                [sys.executable, "-m", "agent_team", "--repo-root", str(repo_root), "--state-root", str(state_root), "go"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(go.returncode, 0, go.stderr)
            self.assertIn("已确认 Go", go.stdout)

    def test_continue_prints_recommended_human_action(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

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
                    "run",
                    "--message",
                    "执行这个需求：做一个 next 摘要",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0, bootstrap.stderr)
            session_id = _session_id_from_stdout(bootstrap.stdout)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    str(state_root),
                    "continue",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("AGT Continue", result.stdout)
            self.assertIn("当前：", result.stdout)
            self.assertIn("进度：", result.stdout)
            self.assertIn("建议：", result.stdout)
            self.assertIn("可执行:", result.stdout)
            self.assertNotIn("stage_run_id", result.stdout)


    def test_next_alias_prints_recommended_human_action(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

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
                    "run",
                    "--message",
                    "执行这个需求：做一个 continue 摘要",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0, bootstrap.stderr)
            session_id = _session_id_from_stdout(bootstrap.stdout)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    str(state_root),
                    "next",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("AGT Continue", result.stdout)
            self.assertIn("建议：", result.stdout)


    def test_continue_tty_prints_numbered_menu_and_exits(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.state import StateStore
        from agent_team.cli import _handle_continue

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir) / ".agent-team"
            store = StateStore(state_root)
            session = store.create_session("执行这个需求：菜单式 continue", initiator="human")
            store.save_workflow_summary(
                session,
                WorkflowSummary(
                    session_id=session.session_id,
                    runtime_mode="harness",
                    current_state="WaitForTechnicalDesignApproval",
                    current_stage="TechnicalDesign",
                    stage_statuses={"Route": "completed", "TechnicalDesign": "drafted"},
                    route_required_stages=["TechnicalDesign", "Verification", "GovernanceReview", "Acceptance", "SessionHandoff"],
                ),
            )
            args = argparse.Namespace(repo_root=repo_root, state_root=state_root, session_id=session.session_id, details=False)

            with patch("sys.stdin", TtyStringIO("4\n")), patch("sys.stdout", TtyStringIO()) as stdout:
                code = _handle_continue(args)

            self.assertEqual(code, 0)
            output = stdout.getvalue()
            self.assertIn("请选择下一步", output)
            self.assertIn("1. 审批 Technical Design（推荐）", output)
            self.assertIn("2. 提修改意见 / 返工", output)
            self.assertIn("4. 退出", output)
            self.assertIn("未修改流程状态", output)

    def test_continue_tty_feedback_uses_template_menu(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.state import StateStore
        from agent_team.cli import _handle_continue

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir) / ".agent-team"
            store = StateStore(state_root)
            session = store.create_session("执行这个需求：模板化反馈", initiator="human")
            store.save_workflow_summary(
                session,
                WorkflowSummary(
                    session_id=session.session_id,
                    runtime_mode="harness",
                    current_state="WaitForTechnicalDesignApproval",
                    current_stage="TechnicalDesign",
                    stage_statuses={"Route": "completed", "TechnicalDesign": "drafted"},
                    route_required_stages=["TechnicalDesign", "Verification", "GovernanceReview", "Acceptance", "SessionHandoff"],
                ),
            )
            args = argparse.Namespace(repo_root=repo_root, state_root=state_root, session_id=session.session_id, details=False)

            with patch("sys.stdin", TtyStringIO("2\n1\n5\n\n")), patch("sys.stdout", TtyStringIO()) as stdout:
                code = _handle_continue(args)

            self.assertEqual(code, 0)
            output = stdout.getvalue()
            self.assertIn("返工到哪个阶段", output)
            self.assertIn("你想提哪类修改意见", output)
            self.assertIn("验证口径不对", output)
            updated = store.load_workflow_summary(session.session_id)
            self.assertEqual(updated.current_state, "TechnicalDesign")
            self.assertEqual(updated.stage_statuses["TechnicalDesign"], "rework_requested")

    def test_status_prints_user_friendly_project_role_and_status(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

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
                    "run",
                    "--message",
                    "执行这个需求：做一个可查询状态的 workflow",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0)
            session_id = _session_id_from_stdout(bootstrap.stdout)

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
            self.assertIn("status:", result.stdout)
            self.assertIn("session_id:", result.stdout)

    def test_record_human_decision_routes_product_definition_approval_to_project_runtime(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            run_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run",
                    "--message",
                    "执行这个需求：做一个 harness-first workflow",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run_result.returncode, 0)
            session_id = _session_id_from_stdout(run_result.stdout)

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
            self.assertIn("current_state: ProjectRuntime", result.stdout)
            self.assertIn("current_stage: ProjectRuntime", result.stdout)

    def test_record_feedback_persists_learning_and_feedback_metadata(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            run_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run",
                    "--message",
                    "执行这个需求：测试反馈回流",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run_result.returncode, 0)
            session_id = _session_id_from_stdout(run_result.stdout)

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
                    "Verification",
                    "--target-stage",
                    "Implementation",
                    "--issue",
                    "Missing edge case handling",
                    "--severity",
                    "high",
                    "--lesson",
                    "Always check edge cases",
                    "--evidence",
                    "test_output.log",
                    "--evidence-kind",
                    "log",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("recorded_feedback:", result.stdout)
            self.assertIn(session_id, result.stdout)

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
                    current_stage="SessionHandoff",
                    stage_statuses={
                        "ProductDefinition": "approved",
                        "Implementation": "completed",
                        "Verification": "passed",
                    },
                    acceptance_status="recommended_go",
                    human_decision="pending",
                    artifact_paths={"workflow_summary": str(store.workflow_summary_path(session.session_id))},
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
                    "SessionHandoff",
                    "--target-stage",
                    "Implementation",
                    "--issue",
                    "Acceptance found a missed parity issue.",
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
            self.assertIn("current_state: Implementation", result.stdout)
            self.assertIn("current_stage: Implementation", result.stdout)
            self.assertIn("human_decision: rework", result.stdout)


    def test_friendly_feedback_rework_can_target_non_wait_stage(self) -> None:
        from agent_team.cli import main
        from agent_team.models import WorkflowSummary
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            state_root = root / "state"
            repo_root.mkdir()
            store = StateStore(state_root)
            session = store.create_session("返工", runtime_mode="runtime_driver")
            store.save_workflow_summary(
                session,
                WorkflowSummary(
                    session_id=session.session_id,
                    runtime_mode="runtime_driver",
                    current_state="Verification",
                    current_stage="Verification",
                    blocked_reason="验证失败",
                ),
            )

            code = main([
                "--repo-root",
                str(repo_root),
                "--state-root",
                str(state_root),
                "feedback",
                "Implementation",
                "改成自包含 check",
                "--session-id",
                session.session_id,
                "--source-stage",
                "Verification",
                "--severity",
                "high",
                "--rework",
            ])
            updated = store.load_workflow_summary(session.session_id)

        self.assertEqual(code, 0)
        self.assertEqual(updated.current_state, "Implementation")
        self.assertEqual(updated.current_stage, "Implementation")
        self.assertEqual(updated.stage_statuses["Implementation"], "rework_requested")

    def test_friendly_feedback_can_apply_rework_decision(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("做一个支持简短反馈命令的流程")
            store.save_workflow_summary(
                session,
                WorkflowSummary(
                    session_id=session.session_id,
                    runtime_mode="session_bootstrap",
                    current_state="WaitForHumanDecision",
                    current_stage="SessionHandoff",
                    stage_statuses={
                        "ProductDefinition": "approved",
                        "Implementation": "completed",
                        "Verification": "passed",
                    },
                    acceptance_status="recommended_go",
                    human_decision="pending",
                    artifact_paths={"workflow_summary": str(store.workflow_summary_path(session.session_id))},
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
                    "feedback",
                    "Implementation",
                    "服务端改动缺少 API 到数据库的端到端验证",
                    "--session-id",
                    session.session_id,
                    "--lesson",
                    "服务端改动必须提供接口到数据的证据",
                    "--required-evidence",
                    "API response",
                    "--required-evidence",
                    "database query result",
                    "--rework",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("recorded_feedback:", result.stdout)
            self.assertIn("current_state: Implementation", result.stdout)
            self.assertIn("human_decision: rework", result.stdout)



    def test_run_defaults_to_new_isolated_worktree_and_continue_reuses_it(self) -> None:
        from agent_team.cli import main

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()
            subprocess.run(["git", "init"], cwd=repo_root, capture_output=True, text=True, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True)
            (repo_root / "README.md").write_text("# main\n")
            subprocess.run(["git", "add", "README.md"], cwd=repo_root, capture_output=True, text=True, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, capture_output=True, text=True, check=True)
            subprocess.run(["git", "checkout", "-b", "test"], cwd=repo_root, capture_output=True, text=True, check=True)
            (repo_root / "README.md").write_text("# test baseline\n")
            subprocess.run(["git", "commit", "-am", "baseline"], cwd=repo_root, capture_output=True, text=True, check=True)
            subprocess.run(
                ["git", "checkout", "-b", "feature/current"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )

            state_root = repo_root / ".agt"
            (state_root / "local").mkdir(parents=True, exist_ok=True)
            (state_root / "local" / "worktree-policy.json").write_text(
                json.dumps(
                    {
                        "base_ref_candidates": ["test"],
                        "branch_prefix": "feature/",
                        "worktree_root": ".worktrees",
                        "date_format": "%Y%m%d",
                        "slug_max_length": 40,
                        "naming_mode": "request_summary_with_fallback",
                    }
                )
            )
            (state_root / "executor-env.json").write_text(
                '{"inherit":[],"inherit_prefixes":[],"set":{"FOO":"BAR"},"unset":[]}\n'
            )
            (state_root / "skill-preferences.yaml").write_text("initialized: true\n")
            (state_root / "memory" / "Implementation").mkdir(parents=True, exist_ok=True)
            (state_root / "memory" / "Implementation" / "lessons.md").write_text("carry over\n")
            (state_root / "_runtime" / "sessions" / "old").mkdir(parents=True, exist_ok=True)
            (state_root / "_runtime" / "sessions" / "old" / "session.json").write_text("{}\n")
            (state_root / "session-index.json").write_text(json.dumps({"sessions": [{"session_id": "old"}]}))

            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                exit_code = main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "run",
                        "--message",
                        "新增 登录 按钮",
                        "--executor",
                        "dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("worktree_path:", output)
            self.assertIn("branch: feature/", output)
            self.assertIn("add-login-button", output)
            session_id = _session_id_from_stdout(output)

            index_path = repo_root / ".agt" / "session-index.json"
            index_payload = json.loads(index_path.read_text())
            entry = next(item for item in index_payload["sessions"] if item["session_id"] == session_id)
            self.assertEqual(entry["session_id"], session_id)
            self.assertEqual(entry["base_ref"], "test")
            self.assertTrue(entry["base_commit"])
            self.assertEqual(entry["worktree_policy_source"], "local_file")
            self.assertEqual(entry["naming_source"], "request_summary")
            self.assertIn("add-login-button", entry["branch"])
            worktree_path = Path(entry["worktree_path"])
            self.assertTrue(worktree_path.exists())
            self.assertEqual((worktree_path / "README.md").read_text(), "# test baseline\n")
            self.assertTrue((worktree_path / ".agt" / session_id / "product-definition-delta.md").exists())
            self.assertTrue((worktree_path / ".agt" / "skill-preferences.yaml").exists())
            self.assertTrue((worktree_path / ".agt" / "memory" / "Implementation" / "lessons.md").exists())
            self.assertFalse((worktree_path / ".agt" / "_runtime" / "sessions" / "old").exists())
            self.assertFalse((worktree_path / ".agt" / "session-index.json").exists())
            self.assertEqual(
                (worktree_path / ".agt" / "executor-env.json").read_text(),
                (repo_root / ".agt" / "executor-env.json").read_text(),
            )

            continue_stdout = io.StringIO()
            with patch("sys.stdout", continue_stdout):
                continue_exit_code = main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "continue",
                        "--executor",
                        "dry-run",
                    ]
                )

            self.assertEqual(continue_exit_code, 0)
            continue_output = continue_stdout.getvalue()
            self.assertIn(f"session_id: {session_id}", continue_output)
            self.assertEqual(len(list((repo_root / ".worktrees").iterdir())), 1)

    def test_continue_accepts_session_id_positional_alias(self) -> None:
        from agent_team.cli import _normalize_command_aliases

        self.assertEqual(
            _normalize_command_aliases(["--repo-root", "/tmp/repo", "continue", "abc123", "--executor", "dry-run"]),
            ["--repo-root", "/tmp/repo", "run", "--continue", "--session-id", "abc123", "--executor", "dry-run"],
        )


if __name__ == "__main__":
    unittest.main()
