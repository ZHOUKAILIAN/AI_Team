import json
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class FiveLayerInitTests(unittest.TestCase):
    def test_auto_mode_non_interactive_writes_prompt_without_running_codex(self) -> None:
        from agent_team.five_layer_init import run_five_layer_classification

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            project_root = repo_root / "agent-team" / "project"
            repo_root.mkdir()

            result = run_five_layer_classification(
                repo_root=repo_root,
                project_root=project_root,
                mode="auto",
                interactive=False,
            )

            self.assertEqual(result.status, "skipped")
            self.assertTrue(result.prompt_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue(result.metadata_path.exists())
            self.assertIn("five-layer-classifier", result.prompt_path.read_text())
            metadata = json.loads(result.metadata_path.read_text())
            self.assertEqual(metadata["status"], "skipped")
            self.assertEqual(metadata["command"], [])
            self.assertIn("github.com/ZHOUKAILIAN/skills", metadata["skill_source"])

    def test_init_trace_files_use_portable_paths(self) -> None:
        from agent_team.five_layer_init import run_five_layer_classification

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            project_root = repo_root / "agt-control" / "project"
            codex_home = root / "codex-home"
            skill_dir = codex_home / "skills" / "five-layer-classifier"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("# Five Layer Classifier\n")
            repo_root.mkdir()

            with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}):
                result = run_five_layer_classification(
                    repo_root=repo_root,
                    project_root=project_root,
                    mode="skip",
                    interactive=False,
                )

            prompt = result.prompt_path.read_text()
            metadata = json.loads(result.metadata_path.read_text())
            serialized_metadata = json.dumps(metadata, sort_keys=True)

            self.assertNotIn(str(root), prompt)
            self.assertNotIn(str(root), serialized_metadata)
            self.assertIn("Target scope: .", prompt)
            self.assertIn(
                "Output destination: agt-control/project/five-layer/classification.md",
                prompt,
            )
            self.assertEqual(metadata["five_layer_root"], "agt-control/project/five-layer")
            self.assertEqual(metadata["report_path"], "agt-control/project/five-layer/classification.md")
            self.assertEqual(metadata["prompt_path"], "agt-control/project/five-layer/classification-prompt.md")
            self.assertEqual(metadata["skill_path"], "local-cache-present")

    def test_forced_run_invokes_codex_and_records_completed_report(self) -> None:
        from agent_team.five_layer_init import run_five_layer_classification

        calls = []

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            project_root = repo_root / "agent-team" / "project"
            codex_home = root / "codex-home"
            skill_dir = codex_home / "skills" / "five-layer-classifier"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("# Five Layer Classifier\n")
            repo_root.mkdir()

            def fake_run(command, *, cwd, capture_output, text, timeout, check, stdin):
                calls.append(command)
                self.assertEqual(cwd, repo_root)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                self.assertEqual(timeout, 1800)
                self.assertFalse(check)
                self.assertIs(stdin, subprocess.DEVNULL)
                prompt = command[-1]
                self.assertIn("Use the five-layer-classifier skill", prompt)
                self.assertIn("Skill source URL: https://github.com/ZHOUKAILIAN/skills", prompt)
                self.assertIn("Local skill path, if available:", prompt)
                report_path = project_root / "five-layer" / "classification.md"
                report_path.write_text(
                    "# Five-Layer Classification Report\n\n"
                    "| Path | Layer | Action | Reason |\n"
                    "| --- | --- | --- | --- |\n"
                    "| docs/product-definition | L1 | keep | canonical product definition entry |\n"
                )
                return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

            with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}), patch(
                "agent_team.five_layer_init.shutil.which",
                return_value="/usr/local/bin/codex",
            ), patch("agent_team.five_layer_init.subprocess.run", side_effect=fake_run):
                result = run_five_layer_classification(
                    repo_root=repo_root,
                    project_root=project_root,
                    mode="run",
                    interactive=False,
                )

            self.assertEqual(result.status, "completed")
            self.assertEqual(len(calls), 1)
            self.assertIn("--output-last-message", calls[0])
            self.assertEqual(calls[0][-1].count("classification.md"), 2)
            metadata = json.loads(result.metadata_path.read_text())
            self.assertEqual(metadata["status"], "completed")
            self.assertEqual(metadata["returncode"], 0)
            self.assertIn("<classification-prompt>", metadata["command"])
            self.assertIn("github.com/ZHOUKAILIAN/skills", metadata["skill_source"])
            self.assertEqual(result.stdout_path.read_text(), "ok\n")

    def test_forced_run_uses_remote_source_when_local_skill_is_missing(self) -> None:
        from agent_team.five_layer_init import run_five_layer_classification

        calls = []

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            project_root = repo_root / "agent-team" / "project"
            codex_home = root / "empty-codex-home"
            codex_home.mkdir()
            repo_root.mkdir()

            def fake_run(command, *, cwd, capture_output, text, timeout, check, stdin):
                calls.append(command)
                self.assertIn("Skill source URL: https://github.com/example/skills/tree/main/five-layer-classifier", command[-1])
                report_path = project_root / "five-layer" / "classification.md"
                report_path.write_text(
                    "# Five-Layer Classification Report\n\n"
                    "| Path | Layer | Action | Reason |\n"
                    "| --- | --- | --- | --- |\n"
                    "| README.md | L3 | keep | project landing context |\n"
                )
                return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

            with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}), patch(
                "agent_team.five_layer_init.shutil.which",
                return_value="/usr/local/bin/codex",
            ), patch("agent_team.five_layer_init.subprocess.run", side_effect=fake_run):
                result = run_five_layer_classification(
                    repo_root=repo_root,
                    project_root=project_root,
                    mode="run",
                    interactive=False,
                    skill_source="https://github.com/example/skills/tree/main/five-layer-classifier",
                )

            self.assertEqual(result.status, "completed")
            self.assertEqual(len(calls), 1)
            metadata = json.loads(result.metadata_path.read_text())
            self.assertEqual(metadata["skill_path"], "")
            self.assertEqual(
                metadata["skill_source"],
                "https://github.com/example/skills/tree/main/five-layer-classifier",
            )

    def test_forced_run_blocks_when_no_skill_source_is_available(self) -> None:
        from agent_team.five_layer_init import run_five_layer_classification

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            project_root = repo_root / "agent-team" / "project"
            codex_home = root / "empty-codex-home"
            codex_home.mkdir()
            repo_root.mkdir()

            with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}), patch(
                "agent_team.five_layer_init.shutil.which",
                return_value="/usr/local/bin/codex",
            ):
                result = run_five_layer_classification(
                    repo_root=repo_root,
                    project_root=project_root,
                    mode="run",
                    interactive=False,
                    skill_source="",
                )

            self.assertEqual(result.status, "blocked")
            self.assertIn("no local installation and no remote source URL", result.reason)
            metadata = json.loads(result.metadata_path.read_text())
            self.assertEqual(metadata["returncode"], 126)


if __name__ == "__main__":
    unittest.main()
