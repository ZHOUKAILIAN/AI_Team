import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class WorkspaceMetadataTests(unittest.TestCase):
    def test_refresh_workspace_metadata_writes_repo_and_worktree_identity(self) -> None:
        from agent_team.workspace_metadata import refresh_workspace_metadata

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir) / "agent-team-runtime-test"

            metadata = refresh_workspace_metadata(state_root=state_root, repo_root=repo_root)

            metadata_path = state_root / "workspace.json"
            self.assertTrue(metadata_path.exists())
            payload = json.loads(metadata_path.read_text())
            self.assertEqual(payload["project_name"], repo_root.name)
            self.assertEqual(payload["project_root"], str(repo_root.resolve()))
            self.assertEqual(payload["worktree_path"], str(repo_root.resolve()))
            self.assertEqual(payload["state_root"], str(state_root.resolve()))
            self.assertEqual(metadata.project_name, repo_root.name)
            self.assertIn("updated_at", payload)

    def test_load_workspace_metadata_falls_back_to_state_root_name(self) -> None:
        from agent_team.workspace_metadata import load_workspace_metadata

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            state_root = Path(temp_dir) / "legacy-workspace-123"
            state_root.mkdir()

            metadata = load_workspace_metadata(state_root)

            self.assertEqual(metadata.project_name, "legacy-workspace-123")
            self.assertEqual(metadata.project_root, "")
            self.assertEqual(metadata.worktree_path, "")
            self.assertEqual(metadata.branch, "")
            self.assertEqual(metadata.state_root, str(state_root.resolve()))
