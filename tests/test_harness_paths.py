import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class HarnessPathTests(unittest.TestCase):
    def test_default_state_root_uses_repo_local_ai_team_directory(self) -> None:
        from ai_company.harness_paths import default_state_root

        repo_root = Path("/tmp/Demo Repo")
        codex_home = Path("/tmp/codex-home")

        state_root = default_state_root(repo_root=repo_root, codex_home=codex_home)

        self.assertEqual(state_root, repo_root.resolve() / ".ai-team")

    def test_default_state_root_ignores_codex_home_environment_variable(self) -> None:
        from ai_company.harness_paths import default_state_root

        with TemporaryDirectory() as temp_dir:
            state_root = default_state_root(repo_root=Path(temp_dir) / "project")

        self.assertEqual(state_root, (Path(temp_dir) / "project").resolve() / ".ai-team")


if __name__ == "__main__":
    unittest.main()
