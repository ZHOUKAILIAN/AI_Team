from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .board import build_board_snapshot_with_roots, is_allowed_artifact_path
from .board_assets import BOARD_HTML


def create_board_server(*, host: str, port: int, codex_home: Path | None = None) -> ThreadingHTTPServer:
    class BoardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_text(BOARD_HTML, content_type="text/html; charset=utf-8")
                return
            if parsed.path == "/api/board":
                snapshot = build_board_snapshot_with_roots(codex_home=codex_home)
                self._send_json(snapshot.payload)
                return
            if parsed.path == "/api/artifact":
                self._handle_artifact(parsed.query)
                return
            self.send_error(404, "Not found")

        def log_message(self, format: str, *args: object) -> None:
            return

        def _handle_artifact(self, query: str) -> None:
            params = parse_qs(query)
            raw_path = params.get("path", [""])[0]
            if not raw_path:
                self.send_error(400, "Missing path")
                return

            snapshot = build_board_snapshot_with_roots(codex_home=codex_home)
            artifact_path = Path(raw_path)
            if not is_allowed_artifact_path(artifact_path, snapshot.state_roots):
                self.send_error(403, "Artifact path is outside known state roots")
                return
            if not artifact_path.exists() or not artifact_path.is_file():
                self.send_error(404, "Artifact not found")
                return
            self._send_text(artifact_path.read_text(errors="replace"), content_type="text/plain; charset=utf-8")

        def _send_json(self, payload: object) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, content: str, *, content_type: str) -> None:
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), BoardHandler)
