import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_team.executor import ClaudeCodeExecutor, CodexExecutor, ExecutorResult, StageExecutor, _extract_last_message


class ExecutorTests(unittest.TestCase):
    def test_codex_executor_builds_correct_command(self) -> None:
        executor = CodexExecutor(
            repo_root=Path("/repo"),
            codex_bin="/usr/local/bin/codex",
            model="gpt-5.5",
            sandbox="workspace-write",
            approval="never",
            profile="default",
        )

        command = executor.build_command(prompt="Prompt", output_path=Path("/tmp/last.json"))

        self.assertEqual(command[:4], ["/usr/local/bin/codex", "exec", "--cd", "/repo"])
        self.assertIn("--json", command)
        self.assertIn("--output-last-message", command)
        self.assertIn("/tmp/last.json", command)
        self.assertIn("--model", command)
        self.assertIn("gpt-5.5", command)
        self.assertIn("--sandbox", command)
        self.assertIn("workspace-write", command)
        self.assertIn("-c", command)
        self.assertIn('approval_policy="never"', command)
        self.assertIn("--profile", command)
        self.assertIn("default", command)
        self.assertEqual(command[-1], "Prompt")

    def test_codex_executor_reads_last_message(self) -> None:
        calls = []

        def fake_run(command, *, capture_output, text, check):
            calls.append(command)
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text('{"status":"completed"}')
            return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

        with TemporaryDirectory() as temp_dir:
            executor = CodexExecutor(repo_root=Path(temp_dir), run=fake_run)
            result = executor.execute(prompt="Prompt", output_dir=Path(temp_dir) / "out", stage="Dev")

        self.assertIsInstance(executor, StageExecutor)
        self.assertEqual(result.last_message, '{"status":"completed"}')
        self.assertEqual(calls[0][-1], "Prompt")

    def test_claude_code_executor_builds_correct_command(self) -> None:
        executor = ClaudeCodeExecutor(claude_bin="/opt/claude", model="sonnet", allowed_tools=["Read", "Grep"])

        command = executor.build_command(prompt="Prompt")

        self.assertEqual(command[:5], ["/opt/claude", "--print", "--output-format", "json", "--allowedTools"])
        self.assertIn("Read,Grep", command)
        self.assertIn("--model", command)
        self.assertIn("sonnet", command)
        self.assertEqual(command[-1], "Prompt")

    def test_claude_code_executor_extracts_last_message(self) -> None:
        calls = []

        def fake_run(command, *, capture_output, text, check):
            calls.append(command)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='[{"type":"system"},{"content":"{\\"status\\":\\"passed\\"}"}]',
                stderr="",
            )

        with TemporaryDirectory() as temp_dir:
            executor = ClaudeCodeExecutor(run=fake_run)
            result = executor.execute(prompt="Prompt", output_dir=Path(temp_dir), stage="QA")

        self.assertEqual(result.last_message, '{"status":"passed"}')
        self.assertEqual(calls[0][-1], "Prompt")

    def test_extract_last_message_handles_dict_result_shape(self) -> None:
        self.assertEqual(_extract_last_message('{"result":"ok"}'), "ok")

    def test_result_success_reflects_return_code(self) -> None:
        self.assertTrue(ExecutorResult(0, "", "", "").success)
        self.assertFalse(ExecutorResult(1, "", "", "").success)


if __name__ == "__main__":
    unittest.main()
