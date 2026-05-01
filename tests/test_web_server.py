import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class ConsoleWebServerTests(unittest.TestCase):
    def test_console_server_serves_index_and_console_snapshot(self) -> None:
        from agent_team.state import StateStore
        from agent_team.web_server import create_console_app
        from agent_team.workspace_metadata import refresh_workspace_metadata
        from starlette.testclient import TestClient

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            codex_home = Path(temp_dir)
            web_dist = Path(temp_dir) / "web-dist"
            web_dist.mkdir()
            (web_dist / "index.html").write_text("<!doctype html><title>Console</title><div id='root'></div>")
            state_root = codex_home / "agent-team" / "workspaces" / "workspace-a"
            StateStore(state_root).create_session("serve console")
            refresh_workspace_metadata(state_root=state_root, repo_root=repo_root)
            client = TestClient(create_console_app(codex_home=codex_home, web_dist=web_dist))

            html = client.get("/").text
            payload = client.get("/api/console/snapshot").json()

            self.assertIn("<div id='root'></div>", html)
            self.assertEqual(payload["stats"]["projects"], 1)
            self.assertEqual(payload["stats"]["sessions"], 1)

    def test_console_server_rejects_unsafe_artifact_path(self) -> None:
        from agent_team.state import StateStore
        from agent_team.web_server import create_console_app
        from agent_team.workspace_metadata import refresh_workspace_metadata
        from starlette.testclient import TestClient

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            codex_home = Path(temp_dir)
            state_root = codex_home / "agent-team" / "workspaces" / "workspace-a"
            session = StateStore(state_root).create_session("artifact safety")
            refresh_workspace_metadata(state_root=state_root, repo_root=repo_root)
            client = TestClient(create_console_app(codex_home=codex_home))

            safe_response = client.get("/api/artifact", params={"path": str(session.artifact_dir / "request.md")})
            unsafe_response = client.get("/api/artifact", params={"path": "/etc/passwd"})

            self.assertEqual(safe_response.status_code, 200)
            self.assertIn("Workflow Request", safe_response.text)
            self.assertEqual(unsafe_response.status_code, 403)

    def test_console_websocket_sends_hello_message(self) -> None:
        from agent_team.web_server import create_console_app
        from starlette.testclient import TestClient

        with TestClient(create_console_app()) as client:
            with client.websocket_connect("/ws/runtime") as websocket:
                payload = json.loads(websocket.receive_text())

        self.assertEqual(payload["type"], "hello")


if __name__ == "__main__":
    unittest.main()
