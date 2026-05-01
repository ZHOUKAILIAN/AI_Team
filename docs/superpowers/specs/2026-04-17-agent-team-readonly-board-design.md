# Agent Team Read-Only Board Design

Date: 2026-04-17

## Goal

Add a local, read-only board for Agent Team so an operator can see:

- all projects aggregated across all workspaces
- each project's worktrees and branches
- each worktree's sessions
- the current workflow stage, active stage run, gate result, and artifact links for a selected session

The board must make the enforced runtime visible without weakening the current CLI-owned state transition model.

## Summary

The current runtime already persists enough workflow data to support a board:

- `workflow_summary.md`
- `session.json`
- `stage_runs/*.json`
- artifact files under `artifacts/<session_id>/`

What is still missing is a stable way to display:

- project identity
- worktree identity
- branch identity

So the board design has two parts:

1. add lightweight workspace metadata so the runtime can describe `project -> worktree -> branch`
2. add a read-only board snapshot and local HTTP server that render a `Master-detail` board with automatic polling

The first version stays intentionally narrow:

- local only
- read-only only
- Python standard library server
- polling every 5 seconds
- no React/Vite/frontend framework
- no write actions from the board

## User-Approved Decisions

- board type: `Master-detail`
- scope: `read-only`
- data scope: `all workspaces aggregated`
- information hierarchy: `Project -> Worktree -> Session`
- project definition: `Git repository / workspace root`
- refresh mode: `automatic polling`

## Non-Goals

- no board-triggered stage transitions
- no approve / rework / verify / submit buttons
- no database
- no websocket / SSE for v1
- no standalone frontend application
- no cross-machine or remote multi-user access concerns in v1

## Current Runtime Constraints

The current workspace state root is derived from a workspace fingerprint:

```text
$CODEX_HOME/agent-team/workspaces/<workspace_fingerprint>/
```

This is enough to isolate runtime state, but not enough to reliably render:

- repo root
- repo display name
- worktree path
- current branch

The board therefore cannot depend on state-root name guessing. It needs first-class metadata.

## Proposed Data Model

### 1. Workspace Metadata

Add a file at the state root:

```text
workspace.json
```

Suggested shape:

```json
{
  "project_name": "agent-team-runtime",
  "project_root": "/Users/.../agent-team-runtime",
  "worktree_path": "/Users/.../.worktrees/enforced-stage-gates",
  "branch": "codex/enforced-stage-gates",
  "state_root": "/Users/.../.codex/agent-team/workspaces/agent-team-runtime-xxxx",
  "updated_at": "2026-04-17T00:00:00+00:00"
}
```

Rules:

- `project_name` comes from the repo root directory name
- `project_root` is the resolved repo root path
- `worktree_path` is the actual working directory where the runtime is invoked
- `branch` is the current Git branch when resolvable
- `state_root` is included for debugging and supportability

This metadata should be written or refreshed whenever the runtime is invoked through normal CLI entrypoints such as:

- `start-session`
- `step`
- `acquire-stage-run`
- `submit-stage-result`
- `verify-stage-result`
- `record-human-decision`

### 2. Aggregated Board Snapshot

The board server should build one in-memory snapshot across every workspace under:

```text
$CODEX_HOME/agent-team/workspaces/*
```

Suggested response shape:

```json
{
  "generated_at": "2026-04-17T00:00:00+00:00",
  "projects": [
    {
      "project_name": "agent-team-runtime",
      "project_root": "/Users/.../agent-team-runtime",
      "worktrees": [
        {
          "worktree_path": "/Users/.../.worktrees/enforced-stage-gates",
          "branch": "codex/enforced-stage-gates",
          "state_root": "/Users/.../agent-team/workspaces/agent-team-runtime-xxxx",
          "session_count": 3,
          "sessions": [
            {
              "session_id": "20260417T000000Z-example",
              "request": "build a readonly board",
              "created_at": "2026-04-17T00:00:00+00:00",
              "current_state": "Dev",
              "current_stage": "Dev",
              "human_decision": "pending",
              "blocked_reason": "",
              "workflow_status": "in_progress",
              "active_run": {
                "run_id": "dev-run-2",
                "state": "SUBMITTED",
                "gate_status": "",
                "gate_reason": "",
                "required_outputs": ["implementation.md"],
                "required_evidence": ["self_verification"]
              },
              "artifact_paths": {
                "request": "...",
                "workflow_summary": "...",
                "dev": "..."
              }
            }
          ]
        }
      ]
    }
  ]
}
```

### 3. Legacy Fallback

Old workspaces may not yet have `workspace.json`.

Fallback policy:

- infer `project_name` from the state root folder name when necessary
- set `project_root`, `worktree_path`, and `branch` to empty strings when unavailable
- still include the workspace in the snapshot
- never guess a branch from arbitrary filenames

This keeps the board backward-compatible without inventing false facts.

## CLI And HTTP Surface

### 1. `agent-team board-snapshot`

Add:

```bash
agent-team board-snapshot --all-workspaces
```

Behavior:

- emits the aggregated board snapshot as JSON
- supports local testing and debugging
- becomes the contract used by the board server

### 2. `agent-team serve-board`

Add:

```bash
agent-team serve-board --all-workspaces --port 8765 --poll-interval 5
```

Behavior:

- starts a local HTTP server
- serves a built-in read-only HTML page
- serves a JSON API for polling

### 3. HTTP Endpoints

#### `GET /`

Returns the built-in board page.

#### `GET /api/board`

Returns the same aggregated snapshot as `board-snapshot`.

#### `GET /api/artifact?path=<absolute_path>`

Returns text content for an artifact preview.

Safety rule:

- the requested path must resolve under one of the discovered state roots
- if not, return `403`

This avoids turning the board into a general arbitrary-file reader for the local machine.

## Board UI Design

### Layout

Use a single-page `Master-detail` layout.

#### Top Summary Bar

Display high-level counts:

- projects
- worktrees
- sessions
- blocked sessions
- waiting-for-human sessions
- submitted runs

#### Left Navigation Tree

Three levels:

```text
Project
└── Worktree / branch
    └── Session
```

Each session row should show:

- short request title
- current workflow stage
- active run state when available

#### Right Detail Panel

For the selected session, render four blocks:

1. Session header
2. Workflow timeline
3. Active stage run
4. Artifacts and previews

### Workflow Timeline

Render the canonical stage chain:

```text
Product -> WaitForCEOApproval -> Dev -> QA -> Acceptance -> WaitForHumanDecision -> Done
```

Show the selected session's current place in that chain and highlight:

- wait states
- blocked states
- current execution stage

### Active Run Panel

Show:

- `run_id`
- `stage`
- `state`
- `gate_status`
- `gate_reason`
- `required_outputs`
- `required_evidence`
- next expected operator action

### Artifact Panel

List known artifact files from `artifact_paths`.

Clicking an artifact opens an inline read-only text preview on the detail side.

## Refresh Model

Use polling every 5 seconds.

Rules:

- keep the currently selected session if it still exists
- if the selected session disappears, select the newest visible session
- display `last refreshed at`
- the board should tolerate incomplete reads and simply recover on the next poll

Why polling:

- enough for a local runtime board
- much simpler than websocket/SSE
- avoids introducing long-lived server state for v1

## Status Presentation

Recommended color semantics:

- green: `PASSED`, `Done`
- blue: `RUNNING`, `SUBMITTED`
- orange: `VERIFYING`
- red: `FAILED`
- deep red: `BLOCKED`
- yellow: `WaitForCEOApproval`, `WaitForHumanDecision`

These colors should communicate runtime semantics, not product branding.

## Runtime Boundaries

The board must not mutate workflow state.

Explicitly excluded from v1:

- approve / rework buttons
- verify button
- submit bundle button
- artifact editing

All state changes remain CLI-owned:

- `acquire-stage-run`
- `submit-stage-result`
- `verify-stage-result`
- `record-human-decision`

This preserves the enforced stage-gate architecture.

## Implementation Boundaries

Keep v1 dependency-light:

- Python standard library for HTTP serving
- built-in HTML/CSS/JS assets
- no frontend build chain

The board can live inside the existing package, for example:

```text
agent_team/board.py
agent_team/board_server.py
agent_team/board_assets/
```

## Testing Strategy

Add tests for:

### Snapshot aggregation

- reads multiple workspace roots
- groups by project root
- nests worktrees correctly
- includes active run summary
- handles missing `workspace.json`

### Artifact path safety

- allows paths under discovered state roots
- rejects paths outside them

### CLI behavior

- `board-snapshot` outputs valid JSON
- `serve-board` binds and responds on `/api/board`

### UI smoke behavior

Minimal HTML tests should verify the page includes:

- left navigation shell
- detail panel shell
- polling hook

## Rollout Order

1. add `workspace.json` metadata writing
2. add board snapshot builder
3. add `board-snapshot` CLI
4. add local HTTP board server
5. add read-only HTML page and polling
6. add artifact preview endpoint
7. add tests and docs

## Risks

### 1. Metadata drift

If branch/worktree metadata is only written once, it can go stale. Refreshing it on normal CLI commands reduces this risk.

### 2. Partial legacy coverage

Old sessions may not fully identify their worktree. The fallback policy makes this explicit instead of guessing.

### 3. Board accidentally becomes a control plane

The design avoids this by keeping all write operations out of v1.

## Final Decision

Build a local, read-only `Master-detail` board inside the existing Python runtime, aggregating all workspaces, organized by `project -> worktree -> session`, refreshing every 5 seconds, and showing workflow plus stage-run enforcement details without allowing any state mutation from the UI.
