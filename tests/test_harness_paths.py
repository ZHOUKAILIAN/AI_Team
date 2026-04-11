import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class HarnessPathTests(unittest.TestCase):
    def test_default_state_root_uses_codex_home_workspace_directory(self) -> None:
        from ai_company.harness_paths import default_state_root

        repo_root = Path("/tmp/Demo Repo")
        codex_home = Path("/tmp/codex-home")

        state_root = default_state_root(repo_root=repo_root, codex_home=codex_home)

        self.assertEqual(state_root.parent, codex_home / "ai-team" / "workspaces")
        self.assertTrue(state_root.name.startswith("demo-repo-"))
        self.assertGreater(len(state_root.name), len("demo-repo-"))

    def test_default_state_root_reads_codex_home_environment_variable(self) -> None:
        from ai_company.harness_paths import default_state_root

        with TemporaryDirectory() as temp_dir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = temp_dir
            try:
                state_root = default_state_root(repo_root=Path("/tmp/project"))
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertTrue(str(state_root).startswith(str(Path(temp_dir) / "ai-team" / "workspaces")))


if __name__ == "__main__":
    unittest.main()
