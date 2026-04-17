import json
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class BoardServerTests(unittest.TestCase):
    def test_board_server_serves_html_and_board_json(self) -> None:
        from ai_company.board_server import create_board_server
        from ai_company.state import StateStore
        from ai_company.workspace_metadata import refresh_workspace_metadata

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as codex_home:
            codex_home_path = Path(codex_home)
            state_root = codex_home_path / "ai-team" / "workspaces" / "workspace-a"
            StateStore(state_root).create_session("serve board")
            refresh_workspace_metadata(state_root=state_root, repo_root=repo_root)
            server = create_board_server(host="127.0.0.1", port=0, codex_home=codex_home_path)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_address[1]}"
                html = urllib.request.urlopen(base_url + "/", timeout=5).read().decode()
                payload = json.loads(urllib.request.urlopen(base_url + "/api/board", timeout=5).read().decode())
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertIn("AI_Team Read-Only Board", html)
            self.assertIn("fetch('/api/board')", html)
            self.assertIn("let currentFilter = 'all';", html)
            self.assertIn("function renderFilters", html)
            self.assertIn("function sessionMatchesCurrentFilter", html)
            self.assertIn("function formatSessionMeta", html)
            self.assertIn("function formatRefreshTime", html)
            self.assertIn("Last refreshed: ${escapeHtml(formatRefreshTime(board.generated_at))}", html)
            self.assertEqual(payload["stats"]["sessions"], 1)

    def test_board_server_rejects_artifact_paths_outside_state_roots(self) -> None:
        from ai_company.board_server import create_board_server
        from ai_company.state import StateStore
        from ai_company.workspace_metadata import refresh_workspace_metadata

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as codex_home:
            codex_home_path = Path(codex_home)
            state_root = codex_home_path / "ai-team" / "workspaces" / "workspace-a"
            session = StateStore(state_root).create_session("serve board")
            refresh_workspace_metadata(state_root=state_root, repo_root=repo_root)
            server = create_board_server(host="127.0.0.1", port=0, codex_home=codex_home_path)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_address[1]}"
                safe_url = base_url + "/api/artifact?path=" + urllib.parse.quote(
                    str(session.artifact_dir / "request.md")
                )
                safe_content = urllib.request.urlopen(safe_url, timeout=5).read().decode()
                unsafe_url = base_url + "/api/artifact?path=" + urllib.parse.quote("/etc/passwd")
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(unsafe_url, timeout=5).read()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertIn("Workflow Request", safe_content)
            self.assertEqual(error.exception.code, 403)
