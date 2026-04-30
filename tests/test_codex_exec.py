import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_team.codex_exec import CodexExecConfig, CodexExecResult, CodexExecRunner


class CodexExecTests(unittest.TestCase):
    def test_build_command_uses_json_and_output_last_message(self) -> None:
        config = CodexExecConfig(
            repo_root=Path("/repo"),
            codex_bin="codex",
            output_last_message=Path("/tmp/last.txt"),
            model="gpt-5.5",
            sandbox="workspace-write",
            approval="never",
            profile="default",
        )

        command = config.build_command("Prompt")

        self.assertEqual(command[:4], ["codex", "exec", "--cd", "/repo"])
        self.assertIn("--json", command)
        self.assertIn("--output-last-message", command)
        self.assertIn("/tmp/last.txt", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("--disable", command)
        self.assertIn("plugins", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("--model", command)
        self.assertIn("gpt-5.5", command)
        self.assertIn("--sandbox", command)
        self.assertIn("workspace-write", command)
        self.assertIn("-c", command)
        self.assertIn('approval_policy="never"', command)
        self.assertIn("--profile", command)
        self.assertIn("default", command)
        self.assertEqual(command[-1], "Prompt")

    def test_build_command_uses_prompt_protection_flags_by_default(self) -> None:
        config = CodexExecConfig(repo_root=Path("/repo"))

        command = config.build_command("Prompt")

        self.assertIn("--ignore-rules", command)
        self.assertIn("--disable", command)
        self.assertIn("plugins", command)
        self.assertNotIn("--ignore-user-config", command)

    def test_runner_captures_output_last_message(self) -> None:
        calls = []

        def fake_run(command, *, capture_output, text, check, env=None, stdin=None):
            calls.append(command)
            self.assertIsNotNone(env)
            self.assertIn("CODEX_HOME", env)
            self.assertIs(stdin, subprocess.DEVNULL)
            return subprocess.CompletedProcess(command, 0, stdout='{"event":"done"}\n', stderr="")

        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "last.txt"
            output_path.write_text('{"result": "ok"}')
            runner = CodexExecRunner(run=fake_run)
            result = runner.run(
                CodexExecConfig(
                    repo_root=Path(temp_dir),
                    codex_bin="codex",
                    output_last_message=output_path,
                ),
                "Prompt",
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '{"event":"done"}\n')
        self.assertEqual(result.last_message, '{"result": "ok"}')
        self.assertEqual(calls[0][-1], "Prompt")

    def test_result_success_reflects_return_code(self) -> None:
        self.assertTrue(CodexExecResult(0, "", "", "").success)
        self.assertFalse(CodexExecResult(1, "", "", "").success)


if __name__ == "__main__":
    unittest.main()
