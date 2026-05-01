import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class BoardSnapshotTests(unittest.TestCase):
    def test_board_snapshot_groups_sessions_by_project_and_worktree(self) -> None:
        from agent_team.board import build_board_snapshot
        from agent_team.state import StateStore
        from agent_team.workspace_metadata import refresh_workspace_metadata

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            codex_home = Path(temp_dir)
            state_root = codex_home / "agent-team" / "workspaces" / "agent-team-runtime-abc"
            store = StateStore(state_root)
            session = store.create_session("build readonly board")
            refresh_workspace_metadata(state_root=state_root, repo_root=repo_root)

            snapshot = build_board_snapshot(codex_home=codex_home)

            self.assertEqual(snapshot["stats"]["projects"], 1)
            self.assertEqual(snapshot["stats"]["worktrees"], 1)
            self.assertEqual(snapshot["stats"]["sessions"], 1)
            project = snapshot["projects"][0]
            self.assertEqual(project["project_name"], repo_root.name)
            worktree = project["worktrees"][0]
            self.assertEqual(worktree["worktree_path"], str(repo_root.resolve()))
            self.assertEqual(worktree["sessions"][0]["session_id"], session.session_id)
            self.assertEqual(worktree["sessions"][0]["current_state"], "Intake")

    def test_board_snapshot_includes_active_stage_run_summary(self) -> None:
        from agent_team.board import build_board_snapshot
        from agent_team.state import StateStore
        from agent_team.workspace_metadata import refresh_workspace_metadata

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            codex_home = Path(temp_dir)
            state_root = codex_home / "agent-team" / "workspaces" / "agent-team-runtime-abc"
            store = StateStore(state_root)
            session = store.create_session("build readonly board")
            store.create_stage_run(
                session_id=session.session_id,
                stage="Product",
                contract_id="contract-product",
                required_outputs=["prd.md"],
                required_evidence=["explicit_acceptance_criteria"],
                worker="codex",
            )
            refresh_workspace_metadata(state_root=state_root, repo_root=repo_root)

            snapshot = build_board_snapshot(codex_home=codex_home)
            session_payload = snapshot["projects"][0]["worktrees"][0]["sessions"][0]

            self.assertEqual(session_payload["active_run"]["state"], "RUNNING")
            self.assertEqual(session_payload["active_run"]["required_outputs"], ["prd.md"])
            self.assertEqual(
                session_payload["active_run"]["required_evidence"],
                ["explicit_acceptance_criteria"],
            )

    def test_board_snapshot_falls_back_for_legacy_workspace_without_metadata(self) -> None:
        from agent_team.board import build_board_snapshot
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            codex_home = Path(temp_dir)
            state_root = codex_home / "agent-team" / "workspaces" / "legacy-workspace-123"
            StateStore(state_root).create_session("legacy session")

            snapshot = build_board_snapshot(codex_home=codex_home)

            self.assertEqual(snapshot["projects"][0]["project_name"], "legacy-workspace-123")
            self.assertEqual(snapshot["projects"][0]["project_root"], "")
            self.assertEqual(snapshot["projects"][0]["worktrees"][0]["branch"], "")

    def test_artifact_path_must_be_under_discovered_state_roots(self) -> None:
        from agent_team.board import BoardSnapshot, is_allowed_artifact_path
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            codex_home = Path(temp_dir)
            state_root = codex_home / "agent-team" / "workspaces" / "workspace-a"
            store = StateStore(state_root)
            session = store.create_session("artifact safety")
            request_path = session.artifact_dir / "request.md"
            snapshot = BoardSnapshot(
                payload={"generated_at": "", "stats": {}, "projects": []},
                state_roots=[state_root],
            )

            self.assertTrue(is_allowed_artifact_path(request_path, snapshot.state_roots))
            self.assertFalse(is_allowed_artifact_path(Path("/etc/passwd"), snapshot.state_roots))
