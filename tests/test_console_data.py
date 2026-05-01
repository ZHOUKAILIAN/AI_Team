import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class ConsoleDataTests(unittest.TestCase):
    def test_console_snapshot_normalizes_projects_sessions_and_counts(self) -> None:
        from agent_team.console_data import build_console_snapshot
        from agent_team.state import StateStore
        from agent_team.workspace_metadata import refresh_workspace_metadata

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            codex_home = Path(temp_dir)
            state_root = codex_home / "agent-team" / "workspaces" / "workspace-a"
            store = StateStore(state_root)
            active_session = store.create_session("build react console")
            blocked_session = store.create_session("fix websocket reconnect")
            blocked_summary = store.load_workflow_summary(blocked_session.session_id)
            blocked_summary.current_state = "Blocked"
            blocked_summary.current_stage = "QA"
            blocked_summary.blocked_reason = "Missing build evidence."
            store.save_workflow_summary(blocked_session, blocked_summary)
            refresh_workspace_metadata(state_root=state_root, repo_root=repo_root)

            snapshot = build_console_snapshot(codex_home=codex_home)

            self.assertEqual(snapshot["stats"]["projects"], 1)
            self.assertEqual(snapshot["stats"]["worktrees"], 1)
            self.assertEqual(snapshot["stats"]["sessions"], 2)
            self.assertEqual(snapshot["stats"]["active"], 1)
            self.assertEqual(snapshot["stats"]["blocked"], 1)
            project = snapshot["projects"][0]
            self.assertTrue(project["project_id"].startswith("agent-team-runtime-"))
            self.assertEqual(project["session_count"], 2)
            self.assertEqual(project["active_count"], 1)
            self.assertEqual(project["blocked_count"], 1)
            session_ids = {session["session_id"] for session in project["sessions"]}
            self.assertEqual(session_ids, {active_session.session_id, blocked_session.session_id})

    def test_project_detail_returns_selected_project(self) -> None:
        from agent_team.console_data import build_console_snapshot, build_project_detail
        from agent_team.state import StateStore
        from agent_team.workspace_metadata import refresh_workspace_metadata

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            codex_home = Path(temp_dir)
            state_root = codex_home / "agent-team" / "workspaces" / "workspace-a"
            StateStore(state_root).create_session("project detail")
            refresh_workspace_metadata(state_root=state_root, repo_root=repo_root)
            project_id = build_console_snapshot(codex_home=codex_home)["projects"][0]["project_id"]

            detail = build_project_detail(project_id, codex_home=codex_home)

            self.assertEqual(detail["project"]["project_id"], project_id)
            self.assertEqual(detail["project"]["project_name"], repo_root.name)

    def test_session_detail_reuses_panel_snapshot(self) -> None:
        from agent_team.console_data import build_session_detail
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir) / "demo-project"
            state_root = repo_root / ".agent-team"
            store = StateStore(state_root)
            session = store.create_session("session detail")

            detail = build_session_detail(session.session_id, state_root=state_root, repo_root=repo_root)

            self.assertEqual(detail["session_id"], session.session_id)
            self.assertEqual(detail["snapshot"]["session"]["session_id"], session.session_id)
            self.assertEqual(detail["snapshot"]["session"]["request"], "session detail")


if __name__ == "__main__":
    unittest.main()
