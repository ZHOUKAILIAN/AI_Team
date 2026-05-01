# React Runtime Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React/Tailwind runtime console with Python ASGI REST/WebSocket serving while preserving the existing CLI commands.

**Architecture:** Keep the Python runtime as the source of truth and add a React frontend workspace under `apps/web`. Python exposes normalized console REST endpoints, a WebSocket endpoint, and static asset serving; the React app consumes those endpoints and renders project map, project workbench, and session detail routes.

**Tech Stack:** Python 3.13, Starlette, Uvicorn, React, Vite, TypeScript, Tailwind CSS, npm workspaces.

---

### Task 1: Monorepo React Workspace

**Files:**
- Create: `package.json`
- Create: `apps/web/package.json`
- Create: `apps/web/index.html`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/tailwind.config.ts`
- Create: `apps/web/postcss.config.js`
- Create: `apps/web/src/main.tsx`
- Create: `apps/web/src/styles.css`

- [ ] **Step 1: Add npm workspace metadata**

Create root `package.json` with:

```json
{
  "name": "agent-team-runtime-monorepo",
  "private": true,
  "workspaces": ["apps/web"],
  "scripts": {
    "dev:web": "npm --workspace apps/web run dev",
    "build:web": "npm --workspace apps/web run build",
    "typecheck:web": "npm --workspace apps/web run typecheck"
  }
}
```

- [ ] **Step 2: Add Vite app metadata**

Create `apps/web/package.json` with React, Vite, Tailwind, TypeScript, and Lucide dependencies. Add `dev`, `build`, `preview`, and `typecheck` scripts.

- [ ] **Step 3: Add Vite, TypeScript, Tailwind, and PostCSS config**

Create config files that build to `dist`, proxy `/api` and `/ws` to `http://127.0.0.1:8765` in dev, and scan `src/**/*.{ts,tsx}` for Tailwind classes.

- [ ] **Step 4: Add frontend entrypoint and Tailwind base stylesheet**

Create `src/main.tsx` and `src/styles.css`. The initial entrypoint must render a placeholder app so `npm run build:web` can pass before feature routes are added.

- [ ] **Step 5: Run frontend install and build**

Run: `npm install`

Run: `npm run build:web`

Expected: Vite produces `apps/web/dist/index.html`.

### Task 2: Console Data Adapter

**Files:**
- Create: `agent_team/console_data.py`
- Create: `tests/test_console_data.py`

- [ ] **Step 1: Write adapter tests**

Create tests for:

```python
def test_console_snapshot_normalizes_projects_sessions_and_counts() -> None: ...
def test_project_detail_returns_selected_project() -> None: ...
def test_session_detail_reuses_panel_snapshot() -> None: ...
```

The tests should build a temporary `codex_home`, create sessions with `StateStore`, refresh workspace metadata, and assert normalized project/session fields.

- [ ] **Step 2: Implement `console_data.py`**

Expose:

```python
def build_console_snapshot(*, codex_home: Path | None = None) -> dict[str, Any]: ...
def build_project_detail(project_id: str, *, codex_home: Path | None = None) -> dict[str, Any]: ...
def build_project_sessions(project_id: str, *, codex_home: Path | None = None) -> dict[str, Any]: ...
def build_session_detail(session_id: str, *, state_root: Path | None = None, repo_root: Path | None = None, codex_home: Path | None = None) -> dict[str, Any]: ...
```

Derive data from existing board and panel snapshot builders rather than reading raw files twice.

- [ ] **Step 3: Run data adapter tests**

Run: `python -m pytest tests/test_console_data.py -q`

Expected: all tests pass.

### Task 3: ASGI Console Server

**Files:**
- Create: `agent_team/web_server.py`
- Create: `agent_team/web_assets.py`
- Modify: `pyproject.toml`
- Create: `tests/test_web_server.py`

- [ ] **Step 1: Add web dependencies and package data**

Modify `pyproject.toml` so runtime dependencies include `starlette` and `uvicorn`, and package data includes `web_dist/**/*`.

- [ ] **Step 2: Write ASGI server tests**

Create tests for:

```python
def test_console_server_serves_index_and_console_snapshot() -> None: ...
def test_console_server_rejects_unsafe_artifact_path() -> None: ...
def test_console_websocket_sends_hello_message() -> None: ...
```

Use Starlette `TestClient`.

- [ ] **Step 3: Implement `web_assets.py`**

Expose:

```python
def bundled_web_dist() -> Path: ...
def resolve_web_dist(web_dist: Path | None = None) -> Path: ...
```

If a caller supplies `web_dist`, use it. Otherwise use bundled `agent_team/web_dist`.

- [ ] **Step 4: Implement `web_server.py`**

Expose:

```python
def create_console_app(...): ...
def run_console_server(...): ...
```

Routes:

```text
GET /
GET /projects
GET /projects/{project_id}
GET /projects/{project_id}/sessions/{session_id}
GET /api/console/snapshot
GET /api/projects
GET /api/projects/{project_id}
GET /api/projects/{project_id}/sessions
GET /api/sessions/{session_id}
GET /api/artifact?path=...
WS  /ws/runtime
```

- [ ] **Step 5: Run web server tests**

Run: `python -m pytest tests/test_web_server.py -q`

Expected: all tests pass.

### Task 4: CLI Integration

**Files:**
- Modify: `agent_team/cli.py`
- Modify: `tests/test_board_server.py`
- Modify: `tests/test_panel.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add CLI tests for new console serving**

Update tests so `agent-team panel` and `agent-team serve-board --all-workspaces` still expose old JSON compatibility endpoints and serve React HTML.

- [ ] **Step 2: Wire CLI handlers to `run_console_server`**

Replace `create_board_server` / `run_panel_server` usage in CLI handlers with the new ASGI runner while keeping `panel-snapshot` and `board-snapshot` unchanged.

- [ ] **Step 3: Keep compatibility tests passing**

Run:

```bash
python -m pytest tests/test_board_server.py tests/test_panel.py tests/test_cli.py -q
```

Expected: all selected tests pass.

### Task 5: React Console UI

**Files:**
- Create: `apps/web/src/app/App.tsx`
- Create: `apps/web/src/i18n/messages.ts`
- Create: `apps/web/src/lib/api.ts`
- Create: `apps/web/src/lib/socket.ts`
- Create: `apps/web/src/routes/ProjectMapPage.tsx`
- Create: `apps/web/src/routes/ProjectWorkbenchPage.tsx`
- Create: `apps/web/src/routes/SessionDetailPage.tsx`
- Create: `apps/web/src/components/LanguageSwitch.tsx`
- Create: `apps/web/src/components/SocketIndicator.tsx`
- Create: `apps/web/src/components/StagePill.tsx`

- [ ] **Step 1: Add shared frontend types and API client**

Implement fetch helpers for console snapshot, project detail, project sessions, session detail, and artifact text.

- [ ] **Step 2: Add WebSocket client hook**

Implement reconnecting `/ws/runtime` connection with REST fallback callback hooks and visible connection states.

- [ ] **Step 3: Add app shell and language state**

Implement Chinese default, English switch, `localStorage` persistence, route parsing, and URL navigation.

- [ ] **Step 4: Add project map page**

Render project nodes from API data with list fallback for smaller screens.

- [ ] **Step 5: Add project workbench page**

Render project metrics, stage lanes, filters, worktree context, current action, and recent events.

- [ ] **Step 6: Add session detail page**

Render request, current action, workflow, evidence, artifacts, and event stream.

- [ ] **Step 7: Build frontend**

Run: `npm run build:web`

Expected: TypeScript and Vite build pass.

### Task 6: Verification and Documentation

**Files:**
- Modify: `README.md`
- Modify: `agent_team/packaged_assets.py` if packaged asset tests require it.
- Modify: `tests/test_packaged_assets.py` if needed for web assets.

- [ ] **Step 1: Document the console architecture**

Update README observability section to mention React console, project map, WebSocket, and monorepo web build.

- [ ] **Step 2: Add packaged web asset test**

Assert that packaged web dist lookup has a deterministic path and release builds can include it.

- [ ] **Step 3: Run final verification**

Run:

```bash
npm run build:web
python -m pytest tests/test_console_data.py tests/test_web_server.py tests/test_board_server.py tests/test_panel.py tests/test_cli.py tests/test_packaged_assets.py -q
```

Expected: all selected checks pass.
