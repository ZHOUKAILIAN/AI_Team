from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from .board import build_board_snapshot, build_board_snapshot_with_roots, is_allowed_artifact_path
from .console_data import (
    build_console_snapshot,
    build_project_detail,
    build_project_sessions,
    build_session_detail,
)
from .panel import build_panel_snapshot, list_panel_sessions
from .state import StateStore
from .web_assets import resolve_web_dist


def create_console_app(
    *,
    codex_home: Path | None = None,
    store: StateStore | None = None,
    default_session_id: str | None = None,
    repo_root: Path | None = None,
    web_dist: Path | None = None,
) -> Starlette:
    dist = resolve_web_dist(web_dist)
    routes = [
        Route("/", _index(dist), methods=["GET"]),
        Route("/projects", _index(dist), methods=["GET"]),
        Route("/projects/{project_id}", _index(dist), methods=["GET"]),
        Route("/projects/{project_id}/sessions/{session_id}", _index(dist), methods=["GET"]),
        Route("/api/console/snapshot", _json(lambda: build_console_snapshot(codex_home=codex_home)), methods=["GET"]),
        Route("/api/projects", _json(lambda: {"projects": build_console_snapshot(codex_home=codex_home)["projects"]}), methods=["GET"]),
        Route("/api/projects/{project_id}", _project_detail(codex_home), methods=["GET"]),
        Route("/api/projects/{project_id}/sessions", _project_sessions(codex_home), methods=["GET"]),
        Route("/api/sessions/{session_id}", _session_detail(codex_home, repo_root), methods=["GET"]),
        Route("/api/artifact", _artifact(codex_home), methods=["GET"]),
        Route("/api/board", _json(lambda: build_board_snapshot(codex_home=codex_home)), methods=["GET"]),
        Route("/api/sessions", _panel_sessions(store), methods=["GET"]),
        Route("/api/session", _panel_session(store, default_session_id, repo_root), methods=["GET"]),
        WebSocketRoute("/ws/runtime", _runtime_socket),
    ]
    assets = dist / "assets"
    if assets.exists():
        routes.append(Mount("/assets", StaticFiles(directory=assets), name="assets"))
    return Starlette(debug=False, routes=routes)


def run_console_server(
    *,
    host: str,
    port: int,
    codex_home: Path | None = None,
    store: StateStore | None = None,
    default_session_id: str | None = None,
    repo_root: Path | None = None,
    open_browser: bool = False,
    default_route: str = "/projects",
    web_dist: Path | None = None,
) -> None:
    app = create_console_app(
        codex_home=codex_home,
        store=store,
        default_session_id=default_session_id,
        repo_root=repo_root,
        web_dist=web_dist,
    )
    route = default_route
    if default_session_id and route == "/projects":
        route = f"/?{urlencode({'session_id': default_session_id})}"
    url = f"http://{host}:{port}{route}"
    print(f"console_url: {url}")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _index(dist: Path):
    async def endpoint(request):
        index_path = dist / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse(
            "<!doctype html><html><head><title>Agent Team Runtime Console</title></head>"
            "<body><h1>Agent Team Runtime Console</h1>"
            "<p>React build assets are not available. Run npm run build:web.</p></body></html>"
        )

    return endpoint


def _json(factory):
    async def endpoint(request):
        return JSONResponse(factory())

    return endpoint


def _project_detail(codex_home: Path | None):
    async def endpoint(request):
        try:
            return JSONResponse(build_project_detail(request.path_params["project_id"], codex_home=codex_home))
        except FileNotFoundError as error:
            return JSONResponse({"error": str(error)}, status_code=404)

    return endpoint


def _project_sessions(codex_home: Path | None):
    async def endpoint(request):
        try:
            return JSONResponse(build_project_sessions(request.path_params["project_id"], codex_home=codex_home))
        except FileNotFoundError as error:
            return JSONResponse({"error": str(error)}, status_code=404)

    return endpoint


def _session_detail(codex_home: Path | None, repo_root: Path | None):
    async def endpoint(request):
        try:
            return JSONResponse(
                build_session_detail(
                    request.path_params["session_id"],
                    repo_root=repo_root,
                    codex_home=codex_home,
                )
            )
        except FileNotFoundError as error:
            return JSONResponse({"error": str(error)}, status_code=404)

    return endpoint


def _artifact(codex_home: Path | None):
    async def endpoint(request):
        raw_path = request.query_params.get("path", "")
        if not raw_path:
            return JSONResponse({"error": "Missing path"}, status_code=400)
        snapshot = build_board_snapshot_with_roots(codex_home=codex_home)
        artifact_path = Path(raw_path)
        if not is_allowed_artifact_path(artifact_path, snapshot.state_roots):
            return JSONResponse({"error": "Artifact path is outside known state roots"}, status_code=403)
        if not artifact_path.exists() or not artifact_path.is_file():
            return JSONResponse({"error": "Artifact not found"}, status_code=404)
        return PlainTextResponse(artifact_path.read_text(errors="replace"))

    return endpoint


def _panel_sessions(store: StateStore | None):
    async def endpoint(request):
        if store is None:
            return JSONResponse({"active": [], "archived": []})
        return JSONResponse(list_panel_sessions(store))

    return endpoint


def _panel_session(store: StateStore | None, default_session_id: str | None, repo_root: Path | None):
    async def endpoint(request):
        if store is None:
            return JSONResponse({"error": "Panel state store is not configured."}, status_code=404)
        session_id = request.query_params.get("session_id", default_session_id or store.latest_session_id())
        if not session_id:
            return JSONResponse({"error": "No workflow session exists yet."}, status_code=404)
        try:
            return JSONResponse(build_panel_snapshot(store, session_id, repo_root=repo_root))
        except FileNotFoundError as error:
            return JSONResponse({"error": str(error)}, status_code=404)

    return endpoint


async def _runtime_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_text(json.dumps({"type": "hello"}))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return
