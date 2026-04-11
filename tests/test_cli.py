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


class CliTests(unittest.TestCase):
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
            session_json_path = Path(temp_dir) / "sessions" / session_id / "session.json"

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
            session_json_path = Path(temp_dir) / "sessions" / session_id / "session.json"

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


if __name__ == "__main__":
    unittest.main()
