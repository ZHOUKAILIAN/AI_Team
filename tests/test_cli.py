import os
import subprocess
import sys
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory


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
            [sys.executable, "-m", "ai_company"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("the following arguments are required: command", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_help_exits_successfully(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "ai_company", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("run", result.stdout)
        self.assertIn("review", result.stdout)
        self.assertIn("agent-run", result.stdout)
        self.assertIn("start-session", result.stdout)
        self.assertIn("codex-init", result.stdout)
        self.assertIn("panel", result.stdout)
        self.assertIn("panel-snapshot", result.stdout)
        self.assertIn("status", result.stdout)

    def test_cli_help_lists_readonly_board_commands(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "ai_company", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("board-snapshot", result.stdout)
        self.assertIn("serve-board", result.stdout)

    def test_agent_run_accepts_raw_user_message(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "agent-run",
                    "--message",
                    "执行这个需求：做一个支持验收回写学习记录的任务系统",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("session_id:", result.stdout)
        self.assertIn("acceptance_status:", result.stdout)

    def test_run_and_agent_run_help_describe_demo_deterministic_commands(self) -> None:
        run_help = subprocess.run(
            [sys.executable, "-m", "ai_company", "run", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        agent_run_help = subprocess.run(
            [sys.executable, "-m", "ai_company", "agent-run", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(run_help.returncode, 0)
        self.assertEqual(agent_run_help.returncode, 0)
        self.assertIn("Demo command: execute the deterministic workflow session", run_help.stdout)
        self.assertIn("Demo command: execute the deterministic workflow session", agent_run_help.stdout)

    def test_start_session_bootstraps_session_from_raw_message(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        raw_message = "执行这个需求：做一个支持验收回写学习记录的任务系统"

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
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
            [sys.executable, "-m", "ai_company", "start-session", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "Create a session scaffold for the single-session AI_Team workflow.",
            result.stdout,
        )

    def test_start_session_uses_repo_local_ai_team_state_root_by_default(self) -> None:
        raw_message = "执行这个需求：做一个 harness-first workflow"

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
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
            self.assertEqual(artifact_dir.parent, repo_root / ".ai-team")
            self.assertTrue(artifact_dir.exists())

    def test_current_stage_prints_session_summary_fields(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        raw_message = "执行这个需求：做一个 harness-first workflow"

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
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
                    "ai_company",
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
        from ai_company.workspace_metadata import refresh_workspace_metadata

        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as codex_home:
            env = os.environ.copy()
            env["CODEX_HOME"] = codex_home
            state_root = Path(codex_home) / "ai-team" / "workspaces" / "cli-board-test"
            start_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
            state_root = Path(temp_dir) / ".ai-team"
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
        from ai_company.models import EvidenceItem, StageResultEnvelope
        from ai_company.state import StateStore

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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个 harness-first workflow",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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
                    "ai_company",
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

    def test_record_feedback_persists_learning_and_feedback_metadata(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
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
                    "ai_company",
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
        from ai_company.models import WorkflowSummary
        from ai_company.state import StateStore

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
                    "ai_company",
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

    def test_codex_init_reports_project_scoped_codex_setup(self) -> None:
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "codex-init",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("state_root:", result.stdout)
            self.assertIn("agents_dir:", result.stdout)
            self.assertIn("run_skill:", result.stdout)
            self.assertIn("generated_files: 5", result.stdout)
            self.assertIn(".agents/skills/ai-team-run/SKILL.md", result.stdout)
            self.assertIn("project_root:", result.stdout)
            self.assertIn("recommended_context:", result.stdout)
            self.assertIn("recommended_run_entry: $ai-team-run", result.stdout)
            self.assertNotIn("$ai-team-init", result.stdout)
            self.assertIn("$ai-team-run", result.stdout)
            self.assertIn("manual_init_fallback:", result.stdout)
            self.assertIn("manual_run_fallback:", result.stdout)
            self.assertTrue((repo_root / ".codex" / "agents" / "ai_team_product.toml").exists())
            self.assertTrue((repo_root / ".codex" / "agents" / "ai_team_dev.toml").exists())
            self.assertTrue((repo_root / ".codex" / "agents" / "ai_team_qa.toml").exists())
            self.assertTrue((repo_root / ".codex" / "agents" / "ai_team_acceptance.toml").exists())
            self.assertTrue((repo_root / ".agents" / "skills" / "ai-team-run" / "SKILL.md").exists())
            self.assertFalse((repo_root / ".codex" / "config.toml").exists())
            product_agent_lines = (repo_root / ".codex" / "agents" / "ai_team_product.toml").read_text().splitlines()
            self.assertIn('developer_instructions = """', product_agent_lines)
            self.assertNotIn('instructions = """', product_agent_lines)


if __name__ == "__main__":
    unittest.main()
