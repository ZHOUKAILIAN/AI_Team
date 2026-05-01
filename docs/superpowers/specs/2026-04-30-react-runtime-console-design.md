# React Runtime Console Design

## Summary

Replace the existing Python-embedded Panel and Board HTML with a React runtime console. The console uses a project-map first screen, a project workbench second screen, and a session flow detail third screen. The frontend is built with React, Vite, and Tailwind inside a monorepo workspace. The Python runtime remains authoritative for the state machine, artifacts, snapshots, and CLI commands.

The console keeps the current CLI product shape: users still run `agent-team panel` or `agent-team serve-board`. Internally, those commands start a Python ASGI server that serves the React build, REST snapshot APIs, and a WebSocket endpoint for live updates.

## Goals

- Build the frontend in React instead of Python string-rendered HTML.
- Use Tailwind CSS for styling and responsive behavior.
- Move the repository toward a monorepo shape with `apps/web` as the frontend workspace.
- Keep Python responsible for the runtime state machine, artifact reads, API snapshots, and CLI entrypoints.
- Provide a project-map global overview as the primary first screen.
- Provide a non-map project workbench as the second layer after selecting a project.
- Provide a focused session detail page for one active requirement and its workflow.
- Support Chinese and English UI strings, with Chinese as the default.
- Use REST for initial snapshots and fallback refresh.
- Use WebSocket to keep the frontend connected to runtime updates.
- Preserve shareable URLs for project, session, filters, and language state.

## Non-Goals

- Do not rewrite the Agent Team state machine.
- Do not replace the artifact storage model.
- Do not remove `agent-team panel`, `agent-team serve-board`, `panel-snapshot`, or `board-snapshot`.
- Do not require users to run a separate frontend server in normal installed usage.
- Do not introduce write operations from the console in the first version.
- Do not make the project map the only navigation model. It is the first screen only.

## Product Model

The console has three primary layers.

### Layer 1: Global Project Map

Route:

```text
/projects
```

The first screen shows all discovered projects as spatial nodes.

Node behavior:

- Node size reflects session volume.
- Node color reflects the highest-risk state in the project.
- Live pulse indicates recent WebSocket activity.
- Selecting a node updates a right-side project summary panel.
- Opening a node navigates to the project workbench.

The right summary panel shows:

- Project name and root.
- Worktree count.
- Session count.
- Blocked count.
- Active sessions.
- Recent events.
- WebSocket connection status.

### Layer 2: Project Workbench

Route:

```text
/projects/:projectId
```

The project workbench is not a map. It is an operational page for daily use.

Structure:

- Top project summary with worktree count, session count, active count, waiting-human count, and blocked count.
- Main stage board grouped by workflow stage:
  - Intake
  - Product
  - Dev
  - QA
  - Acceptance
- Waiting-human and Done are status filters in the first version, not primary lanes.
- Right-side project context:
  - Current action.
  - Worktree summaries.
  - Recent events.
  - WebSocket state.

Filtering:

- All sessions.
- Needs human.
- Blocked.
- In progress.
- Worktree.
- Stage.

### Layer 3: Session Flow Detail

Route:

```text
/projects/:projectId/sessions/:sessionId
```

The session detail page is focused on one requirement.

Primary content:

- Request title and raw request text.
- Current stage and next action.
- Full flow timeline:
  - Intake
  - Product
  - Dev
  - QA
  - Acceptance
  - WaitForHumanDecision
  - Done
- Required evidence, provided evidence, and missing evidence.
- Artifact list with previews.
- Event stream.

The page should make the current stage visually obvious, but avoid decorative motion that does not communicate state.

## Interaction Principles

- Chinese is the default language.
- The language switcher is visible in the top bar and persists to `localStorage`.
- URLs include enough state to survive refresh and support sharing.
- Main navigation state is reflected in path segments, not only component state.
- Search is always available on desktop and reachable on mobile.
- Desktop uses a top bar plus contextual panels.
- Mobile uses a bottom navigation pattern for top-level console sections.
- Touch targets must be at least 44px high.
- Focus states must be visible for keyboard users.
- Animations should use transform and opacity only.
- Motion should express navigation hierarchy or live status changes.
- `prefers-reduced-motion` must be respected.

## Frontend Architecture

Add a frontend workspace:

```text
agent-team-runtime/
  package.json
  apps/
    web/
      package.json
      index.html
      vite.config.ts
      tailwind.config.ts
      postcss.config.js
      src/
        app/
        components/
        i18n/
        lib/
        routes/
        styles.css
```

Recommended dependencies:

- `@vitejs/plugin-react`
- `vite`
- `typescript`
- `react`
- `react-dom`
- `tailwindcss`
- `postcss`
- `autoprefixer`
- `lucide-react`

Routing can start with a small internal router built around the History API. If route complexity grows, introduce `react-router` later. The first implementation should avoid adding a routing dependency unless it removes real complexity.

Frontend modules:

- `src/app/App.tsx`
  - App shell, route selection, connection status.
- `src/routes/ProjectMapPage.tsx`
  - Global project map and project summary panel.
- `src/routes/ProjectWorkbenchPage.tsx`
  - Stage board, filters, project context.
- `src/routes/SessionDetailPage.tsx`
  - Request, workflow, evidence, artifacts, events.
- `src/components/`
  - Reusable cards, stage pills, language switcher, socket indicator, artifact preview.
- `src/lib/api.ts`
  - REST API client.
- `src/lib/socket.ts`
  - WebSocket client with reconnect and REST fallback hooks.
- `src/i18n/messages.ts`
  - Chinese and English copy.

## Styling

Tailwind is the primary styling layer.

Use Tailwind for:

- Layout.
- Spacing.
- Responsive breakpoints.
- Typography.
- Focus states.
- Colors via theme tokens.
- State variants.
- Small transitions.

Use plain CSS only for:

- Global CSS variables.
- Complex map node positioning.
- Reduced-motion overrides.
- Any animation that is too awkward to express clearly in Tailwind utilities.

The visual direction is operational, spatial, and calm:

- Off-white and muted green-blue surfaces.
- Strong semantic colors for blocked, waiting, active, and done.
- Rounded surfaces, but not oversized toy-like cards.
- No decorative gradient blobs.
- Map nodes and stage cards should communicate state density, not decoration.

## Backend Architecture

Move local web serving from `http.server` to a lightweight ASGI server.

Recommended implementation:

- Starlette for routes, WebSocket, and static files.
- Uvicorn as the local server runtime.

Add a module such as:

```text
agent_team/web_server.py
```

Responsibilities:

- Serve React static assets.
- Serve REST JSON APIs.
- Serve artifact previews with existing path safety checks.
- Accept WebSocket clients.
- Broadcast runtime updates.
- Provide fallback polling semantics when WebSocket is disconnected.

Existing commands keep their names:

```bash
agent-team panel
agent-team serve-board --all-workspaces
```

Both commands can start the same console server. The difference is their default route and API scope:

- `panel` defaults to a session route when `--session-id` is provided.
- `serve-board` defaults to `/projects`.

## REST API

REST is the source for initial page load and reconnect fallback.

Proposed endpoints:

```text
GET /api/console/snapshot
GET /api/projects
GET /api/projects/:project_id
GET /api/projects/:project_id/sessions
GET /api/sessions/:session_id
GET /api/artifact?path=...
```

Compatibility endpoints may remain:

```text
GET /api/board
GET /api/sessions
GET /api/session?session_id=...
```

The new frontend should prefer `/api/console/*` and project-scoped endpoints. Existing tests and external users can continue using the compatibility endpoints.

## WebSocket API

Endpoint:

```text
WS /ws/runtime
```

Client behavior:

1. Load REST snapshot.
2. Connect to `/ws/runtime`.
3. Apply incoming update events.
4. If the socket disconnects, show reconnecting state.
5. While disconnected, use REST polling as fallback.
6. On reconnect, reload a REST snapshot before applying new events.

Message examples:

```json
{
  "type": "hello",
  "generated_at": "2026-04-30T00:00:00Z"
}
```

```json
{
  "type": "project.updated",
  "project_id": "agent-team-runtime",
  "summary": {}
}
```

```json
{
  "type": "session.updated",
  "project_id": "agent-team-runtime",
  "session_id": "20260430T000000Z-session",
  "summary": {}
}
```

```json
{
  "type": "event.appended",
  "project_id": "agent-team-runtime",
  "session_id": "20260430T000000Z-session",
  "event": {}
}
```

First implementation can broadcast snapshot updates on an interval or after filesystem polling detects changes. A later implementation can emit events from state-writing code paths directly.

## Data Shape

The frontend should receive normalized project and session data derived from the existing board and panel snapshots.

Project summary:

```json
{
  "project_id": "agent-team-runtime",
  "project_name": "agent-team-runtime",
  "project_root": "/path/to/repo",
  "worktree_count": 3,
  "session_count": 7,
  "active_count": 3,
  "waiting_human_count": 2,
  "blocked_count": 0,
  "updated_at": "2026-04-30T00:00:00Z"
}
```

Session summary:

```json
{
  "session_id": "20260430T000000Z-session",
  "project_id": "agent-team-runtime",
  "worktree_path": "/path/to/repo",
  "request": "Build React runtime console",
  "current_state": "QA",
  "current_stage": "QA",
  "workflow_status": "in_progress",
  "blocked_reason": "",
  "active_run": {},
  "artifact_paths": {},
  "created_at": "2026-04-30T00:00:00Z",
  "updated_at": "2026-04-30T00:00:00Z"
}
```

Session detail can reuse `build_panel_snapshot` output at first, then gradually move to a cleaner console-specific shape.

## Static Asset Packaging

Vite build output should be copied into the Python package for release builds:

```text
agent_team/web_dist/
  index.html
  assets/
```

Editable development can serve from `apps/web/dist` when present, or proxy to the Vite dev server when a `--web-dev-url` option is provided.

Recommended scripts:

```json
{
  "scripts": {
    "dev:web": "npm --workspace apps/web run dev",
    "build:web": "npm --workspace apps/web run build",
    "copy:web": "python -m agent_team.web_assets copy",
    "build": "npm run build:web && npm run copy:web"
  },
  "workspaces": [
    "apps/web"
  ]
}
```

The Python package data should include:

```text
agent_team/web_dist/**/*
```

## CLI Behavior

`agent-team panel`:

- Starts the console server.
- Prints `panel_url`.
- If `--session-id` is present, route to `/projects/:projectId/sessions/:sessionId` when the project can be resolved.
- If `--open` is present, open the URL.

`agent-team serve-board --all-workspaces`:

- Starts the same console server.
- Defaults to `/projects`.
- Keeps `/api/board` for compatibility.

`panel-snapshot` and `board-snapshot`:

- Continue printing JSON.
- Do not require Node or React build assets.

## Testing

Python tests:

- API endpoints return expected JSON.
- Static `index.html` is served.
- Artifact path safety still rejects paths outside known state roots.
- WebSocket accepts a client and sends an initial `hello` or snapshot message.
- Existing board and panel snapshot tests continue passing.

Frontend tests:

- Language switch persists and changes labels.
- Project map renders project nodes from API data.
- Project workbench groups sessions by stage.
- Session detail highlights the current stage.
- WebSocket reconnect state appears when disconnected.
- REST fallback refresh is triggered after socket failure.

Build checks:

- `npm run build:web`
- Python test suite.
- At least one smoke test that starts the console server and fetches `/`.

Accessibility checks:

- Visible focus states.
- Keyboard navigation through project nodes, sessions, and artifact links.
- `aria-live` on connection state and live event updates.
- No color-only status indicators.
- Touch targets at least 44px.

## Migration Plan

1. Add monorepo scaffolding and React app.
2. Add Tailwind theme tokens and app shell.
3. Implement REST clients against existing `/api/board` and `/api/session` first.
4. Add project map route.
5. Add project workbench route.
6. Add session detail route.
7. Add ASGI server and static asset serving.
8. Add WebSocket endpoint with snapshot or polling-based broadcasts.
9. Wire existing `panel` and `serve-board` commands to the ASGI server.
10. Keep compatibility endpoints and tests.
11. Remove Python string-rendered HTML only after React pages cover the same flows.

## Risks

- ASGI dependencies add packaging surface to a previously mostly-stdlib web server.
- WebSocket updates can drift from REST snapshots if the message contract is too granular too early.
- Project-map positioning can become noisy with many projects.
- Build artifacts can be missed in release packaging if the build/copy step is not enforced.

Mitigations:

- Keep REST snapshots authoritative.
- Use WebSocket primarily as an invalidation and update channel in the first version.
- Provide list fallback for project map.
- Add release tests that assert packaged `web_dist/index.html` exists.

## Open Decisions Resolved

- Frontend framework: React.
- Styling: Tailwind CSS.
- Repository shape: monorepo with `apps/web`.
- Server model: Python ASGI server.
- Realtime model: REST snapshot plus WebSocket updates.
- Primary first screen: global project map.
- Second screen: project workbench, not a map.
- Third screen: focused session flow detail.
- Default language: Chinese.
