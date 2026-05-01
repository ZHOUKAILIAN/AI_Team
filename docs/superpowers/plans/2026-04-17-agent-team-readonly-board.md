# Agent Team Read-Only Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, read-only Agent Team board that aggregates all workspaces and shows `project -> worktree -> session` progress, active stage runs, gate results, and artifact previews.

**Architecture:** Keep the board as an observer, not a control plane. Add lightweight workspace metadata, a pure snapshot builder, CLI JSON output, and a Python-standard-library HTTP server with an embedded HTML page that polls `/api/board` every 5 seconds.

**Tech Stack:** Python 3.13, dataclasses, `json`, `http.server`, `unittest`, existing `agent-team` argparse CLI, static HTML/CSS/JS with no frontend build chain.

---

## File Structure

- Modify: `.gitignore`
  - Ignore `.superpowers/` visual brainstorming artifacts.
- Create: `agent_team/workspace_metadata.py`
  - Owns `WorkspaceMetadata`, Git branch detection, and `workspace.json` refresh.
- Create: `tests/test_workspace_metadata.py`
  - Verifies metadata writing and fallback behavior.
- Create: `agent_team/board.py`
  - Owns board snapshot aggregation, session/run summarization, and artifact path allow-listing.
- Create: `tests/test_board.py`
  - Verifies multi-workspace aggregation, legacy fallback, active run summaries, and artifact path safety.
- Create: `agent_team/board_assets.py`
  - Stores the read-only board HTML as a Python string constant.
- Create: `agent_team/board_server.py`
  - Owns local read-only HTTP routes: `/`, `/api/board`, `/api/artifact`.
- Modify: `agent_team/cli.py`
  - Adds `board-snapshot` and `serve-board`.
  - Refreshes `workspace.json` for normal workspace-aware commands.
- Modify: `tests/test_cli.py`
  - Adds CLI tests for `board-snapshot`.
- Create: `tests/test_board_server.py`
  - Verifies HTTP route behavior.
- Modify: `README.md`
  - Documents read-only board usage.
- Modify: `docs/workflow-specs/2026-04-11-agent-team-cli-runtime-usage.md`
  - Adds board commands.
- Modify: `docs/workflow-specs/2026-04-11-agent-team-cli-runtime-flow.md`
  - Adds board as read-only observer.

---

### Task 1: Workspace Metadata

**Files:**
- Modify: `.gitignore`
- Create: `agent_team/workspace_metadata.py`
- Create: `tests/test_workspace_metadata.py`
- Modify: `agent_team/cli.py`

- [ ] **Step 1: Write failing metadata tests**

Create `tests/test_workspace_metadata.py`:

```python
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
```

- [ ] **Step 2: Run metadata tests to verify RED**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_workspace_metadata
```

Expected: fail with `ModuleNotFoundError: No module named 'agent_team.workspace_metadata'`.

- [ ] **Step 3: Implement metadata module**

Create `agent_team/workspace_metadata.py`:

```python
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class WorkspaceMetadata:
    project_name: str
    project_root: str
    worktree_path: str
    branch: str
    state_root: str
    updated_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, object], *, state_root: Path) -> "WorkspaceMetadata":
        return cls(
            project_name=str(payload.get("project_name") or state_root.name),
            project_root=str(payload.get("project_root") or ""),
            worktree_path=str(payload.get("worktree_path") or ""),
            branch=str(payload.get("branch") or ""),
            state_root=str(payload.get("state_root") or state_root.resolve()),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def refresh_workspace_metadata(*, state_root: Path, repo_root: Path) -> WorkspaceMetadata:
    state_root = state_root.resolve()
    repo_root = repo_root.resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    metadata = WorkspaceMetadata(
        project_name=repo_root.name,
        project_root=str(repo_root),
        worktree_path=str(repo_root),
        branch=_current_branch(repo_root),
        state_root=str(state_root),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    (state_root / "workspace.json").write_text(json.dumps(metadata.to_dict(), indent=2))
    return metadata


def load_workspace_metadata(state_root: Path) -> WorkspaceMetadata:
    state_root = state_root.resolve()
    metadata_path = state_root / "workspace.json"
    if not metadata_path.exists():
        return WorkspaceMetadata(
            project_name=state_root.name,
            project_root="",
            worktree_path="",
            branch="",
            state_root=str(state_root),
            updated_at="",
        )
    try:
        payload = json.loads(metadata_path.read_text())
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return WorkspaceMetadata.from_dict(payload, state_root=state_root)


def _current_branch(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()
```

- [ ] **Step 4: Add `.superpowers/` to `.gitignore`**

Modify `.gitignore`:

```gitignore
.superpowers/
```

- [ ] **Step 5: Refresh metadata from CLI entrypoint**

In `agent_team/cli.py`, import:

```python
from .workspace_metadata import refresh_workspace_metadata
```

Add this helper near the bottom of `agent_team/cli.py`:

```python
def _should_refresh_workspace_metadata(command: str) -> bool:
    return command not in {"board-snapshot", "serve-board"}
```

Modify `main()` after `args.state_root` is resolved and before `args.handler(args)`:

```python
    if _should_refresh_workspace_metadata(args.command):
        refresh_workspace_metadata(state_root=args.state_root, repo_root=args.repo_root)
```

- [ ] **Step 6: Run metadata tests to verify GREEN**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_workspace_metadata
```

Expected: `OK`.

- [ ] **Step 7: Run targeted CLI smoke test**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_cli.CliTests.test_start_session_bootstraps_session_from_raw_message
```

Expected: `OK`.

- [ ] **Step 8: Commit metadata slice**

```bash
git add .gitignore agent_team/workspace_metadata.py agent_team/cli.py tests/test_workspace_metadata.py
git commit -m "feat: record workspace metadata"
```

---

### Task 2: Board Snapshot Aggregation

**Files:**
- Create: `agent_team/board.py`
- Create: `tests/test_board.py`

- [ ] **Step 1: Write failing snapshot tests**

Create `tests/test_board.py`:

```python
import json
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
```

- [ ] **Step 2: Run board tests to verify RED**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_board
```

Expected: fail with `ModuleNotFoundError: No module named 'agent_team.board'`.

- [ ] **Step 3: Implement board snapshot builder**

Create `agent_team/board.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .harness_paths import _default_codex_home
from .models import GateResult, StageRunRecord
from .state import StateStore
from .workspace_metadata import WorkspaceMetadata, load_workspace_metadata


@dataclass(slots=True)
class BoardSnapshot:
    payload: dict[str, Any]
    state_roots: list[Path]


def build_board_snapshot(*, codex_home: Path | None = None) -> dict[str, Any]:
    return build_board_snapshot_with_roots(codex_home=codex_home).payload


def build_board_snapshot_with_roots(*, codex_home: Path | None = None) -> BoardSnapshot:
    home = codex_home or _default_codex_home()
    workspaces_root = home / "agent-team" / "workspaces"
    state_roots = [path for path in sorted(workspaces_root.glob("*")) if path.is_dir()]
    projects_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    stats = {
        "projects": 0,
        "worktrees": 0,
        "sessions": 0,
        "blocked": 0,
        "waiting_human": 0,
        "submitted_runs": 0,
    }

    for state_root in state_roots:
        metadata = load_workspace_metadata(state_root)
        project_key = (metadata.project_root, metadata.project_name)
        project = projects_by_key.setdefault(
            project_key,
            {
                "project_name": metadata.project_name,
                "project_root": metadata.project_root,
                "worktrees": [],
            },
        )
        worktree = _worktree_payload(metadata)
        store = StateStore(state_root)
        for session_id in _session_ids(state_root):
            session_payload = _session_payload(store, session_id)
            if session_payload is None:
                continue
            stats["sessions"] += 1
            if session_payload["current_state"] == "Blocked":
                stats["blocked"] += 1
            if session_payload["current_state"] in {"WaitForCEOApproval", "WaitForHumanDecision"}:
                stats["waiting_human"] += 1
            active_run = session_payload.get("active_run") or {}
            if active_run.get("state") == "SUBMITTED":
                stats["submitted_runs"] += 1
            worktree["sessions"].append(session_payload)
        worktree["session_count"] = len(worktree["sessions"])
        project["worktrees"].append(worktree)

    projects = list(projects_by_key.values())
    for project in projects:
        project["worktree_count"] = len(project["worktrees"])
    stats["projects"] = len(projects)
    stats["worktrees"] = sum(len(project["worktrees"]) for project in projects)

    return BoardSnapshot(
        payload={
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "projects": projects,
        },
        state_roots=state_roots,
    )


def is_allowed_artifact_path(path: Path, state_roots: list[Path]) -> bool:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False
    for state_root in state_roots:
        try:
            resolved.relative_to(state_root.expanduser().resolve())
            return True
        except ValueError:
            continue
    return False


def _worktree_payload(metadata: WorkspaceMetadata) -> dict[str, Any]:
    return {
        "worktree_path": metadata.worktree_path,
        "branch": metadata.branch,
        "state_root": metadata.state_root,
        "session_count": 0,
        "sessions": [],
    }


def _session_ids(state_root: Path) -> list[str]:
    sessions_dir = state_root / "sessions"
    if not sessions_dir.exists():
        return []
    return sorted(path.name for path in sessions_dir.iterdir() if path.is_dir(), reverse=True)


def _session_payload(store: StateStore, session_id: str) -> dict[str, Any] | None:
    try:
        session = store.load_session(session_id)
        summary = store.load_workflow_summary(session_id)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return None
    active_run = store.active_stage_run(session_id) or store.latest_stage_run(session_id)
    return {
        "session_id": session.session_id,
        "request": session.request,
        "created_at": session.created_at,
        "current_state": summary.current_state,
        "current_stage": summary.current_stage,
        "human_decision": summary.human_decision,
        "blocked_reason": summary.blocked_reason,
        "workflow_status": _workflow_status(summary.current_state),
        "active_run": _run_payload(active_run),
        "artifact_paths": dict(summary.artifact_paths),
    }


def _workflow_status(current_state: str) -> str:
    if current_state == "Done":
        return "done"
    if current_state == "Blocked":
        return "blocked"
    if current_state in {"WaitForCEOApproval", "WaitForHumanDecision"}:
        return "waiting_human"
    return "in_progress"


def _run_payload(run: StageRunRecord | None) -> dict[str, Any] | None:
    if run is None:
        return None
    gate_result = run.gate_result
    return {
        "run_id": run.run_id,
        "stage": run.stage,
        "state": run.state,
        "gate_status": gate_result.status if isinstance(gate_result, GateResult) else "",
        "gate_reason": gate_result.reason if isinstance(gate_result, GateResult) else "",
        "required_outputs": list(run.required_outputs),
        "required_evidence": list(run.required_evidence),
        "artifact_paths": dict(run.artifact_paths),
    }
```

- [ ] **Step 4: Run board tests to verify GREEN**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_board
```

Expected: `OK`.

- [ ] **Step 5: Commit snapshot slice**

```bash
git add agent_team/board.py tests/test_board.py
git commit -m "feat: build read-only board snapshot"
```

---

### Task 3: `board-snapshot` CLI

**Files:**
- Modify: `agent_team/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI snapshot test**

Add this test to `tests/test_cli.py`:

```python
    def test_board_snapshot_outputs_all_workspace_board_json(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as codex_home:
            env = os.environ.copy()
            env["CODEX_HOME"] = codex_home
            start_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "start-session",
                    "--message",
                    "执行这个需求：做一个只读看板",
                ],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(start_result.returncode, 0)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(repo_root),
                    "board-snapshot",
                    "--all-workspaces",
                ],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["stats"]["projects"], 1)
            self.assertEqual(payload["stats"]["sessions"], 1)
            self.assertEqual(payload["projects"][0]["project_name"], repo_root.name)
```

- [ ] **Step 2: Run CLI snapshot test to verify RED**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_cli.CliTests.test_board_snapshot_outputs_all_workspace_board_json
```

Expected: fail because `board-snapshot` does not exist.

- [ ] **Step 3: Add `board-snapshot` parser and handler**

In `agent_team/cli.py`, import:

```python
from .board import build_board_snapshot
```

Add parser before `review_parser`:

```python
    board_snapshot_parser = subparsers.add_parser(
        "board-snapshot",
        help="Print the read-only board snapshot as JSON.",
    )
    board_snapshot_parser.add_argument(
        "--all-workspaces",
        action="store_true",
        help="Aggregate every workspace under CODEX_HOME.",
    )
    board_snapshot_parser.set_defaults(handler=_handle_board_snapshot)
```

Add handler:

```python
def _handle_board_snapshot(args: argparse.Namespace) -> int:
    if not args.all_workspaces:
        raise SystemExit("board-snapshot currently requires --all-workspaces.")
    print(json.dumps(build_board_snapshot(), indent=2))
    return 0
```

Update `_should_refresh_workspace_metadata`:

```python
def _should_refresh_workspace_metadata(command: str) -> bool:
    return command not in {"board-snapshot", "serve-board"}
```

- [ ] **Step 4: Run CLI snapshot test to verify GREEN**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_cli.CliTests.test_board_snapshot_outputs_all_workspace_board_json
```

Expected: `OK`.

- [ ] **Step 5: Commit CLI snapshot slice**

```bash
git add agent_team/cli.py tests/test_cli.py
git commit -m "feat: expose board snapshot cli"
```

---

### Task 4: Read-Only Board HTTP Server

**Files:**
- Create: `agent_team/board_assets.py`
- Create: `agent_team/board_server.py`
- Create: `tests/test_board_server.py`
- Modify: `agent_team/cli.py`

- [ ] **Step 1: Write failing server tests**

Create `tests/test_board_server.py`:

```python
import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class BoardServerTests(unittest.TestCase):
    def test_board_server_serves_html_and_board_json(self) -> None:
        from agent_team.board_server import create_board_server
        from agent_team.state import StateStore
        from agent_team.workspace_metadata import refresh_workspace_metadata

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as codex_home:
            codex_home_path = Path(codex_home)
            state_root = codex_home_path / "agent-team" / "workspaces" / "workspace-a"
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

            self.assertIn("Agent Team Read-Only Board", html)
            self.assertIn("fetch('/api/board')", html)
            self.assertEqual(payload["stats"]["sessions"], 1)

    def test_board_server_rejects_artifact_paths_outside_state_roots(self) -> None:
        from agent_team.board_server import create_board_server
        from agent_team.state import StateStore
        from agent_team.workspace_metadata import refresh_workspace_metadata

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as codex_home:
            codex_home_path = Path(codex_home)
            state_root = codex_home_path / "agent-team" / "workspaces" / "workspace-a"
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
```

- [ ] **Step 2: Run server tests to verify RED**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_board_server
```

Expected: fail with `ModuleNotFoundError: No module named 'agent_team.board_server'`.

- [ ] **Step 3: Add embedded HTML asset**

Create `agent_team/board_assets.py`:

```python
BOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Team Read-Only Board</title>
  <style>
    :root {
      --ink: #14202b;
      --muted: #667788;
      --paper: #f7f1e6;
      --panel: #ffffff;
      --line: #ded5c4;
      --blue: #2f6f9f;
      --green: #3f8f5f;
      --yellow: #d8a026;
      --orange: #c56d2d;
      --red: #b74436;
      --deep-red: #7f1d1d;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 0%, rgba(216,160,38,.18), transparent 32rem),
        linear-gradient(135deg, #f7f1e6, #e9eef2);
    }
    header {
      padding: 22px 28px;
      border-bottom: 1px solid var(--line);
      background: rgba(255,255,255,.72);
      backdrop-filter: blur(10px);
    }
    h1 { margin: 0; font-size: 28px; }
    .subtitle { color: var(--muted); margin-top: 4px; }
    .stats {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
      padding: 16px 28px;
    }
    .stat {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
    }
    .stat b { display: block; font-size: 24px; }
    main {
      display: grid;
      grid-template-columns: 380px 1fr;
      gap: 18px;
      padding: 0 28px 28px;
    }
    aside, section {
      background: rgba(255,255,255,.82);
      border: 1px solid var(--line);
      border-radius: 18px;
      min-height: 560px;
      overflow: hidden;
    }
    .tree { padding: 16px; }
    .project, .worktree, .session {
      border-radius: 12px;
      padding: 10px;
      margin-bottom: 8px;
    }
    .project { background: #14202b; color: #f7f1e6; }
    .worktree { margin-left: 14px; background: #eef3f6; }
    .session { margin-left: 28px; background: #fff; border: 1px solid var(--line); cursor: pointer; }
    .session.active { border-color: var(--blue); box-shadow: 0 0 0 2px rgba(47,111,159,.16); }
    .detail { padding: 18px; }
    .timeline {
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 8px;
      margin: 16px 0;
    }
    .stage {
      padding: 10px;
      border-radius: 12px;
      text-align: center;
      background: #ece7dc;
      font-size: 12px;
    }
    .stage.current { background: #dbeafe; border: 1px solid var(--blue); }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      margin-bottom: 12px;
    }
    .pill { display: inline-block; padding: 4px 8px; border-radius: 999px; color: white; font-size: 12px; }
    .RUNNING, .SUBMITTED { background: var(--blue); }
    .VERIFYING { background: var(--orange); }
    .PASSED, .Done { background: var(--green); }
    .FAILED { background: var(--red); }
    .BLOCKED, .Blocked { background: var(--deep-red); }
    .WaitForCEOApproval, .WaitForHumanDecision { background: var(--yellow); color: #1b1308; }
    pre {
      white-space: pre-wrap;
      max-height: 300px;
      overflow: auto;
      background: #111827;
      color: #e5e7eb;
      padding: 12px;
      border-radius: 12px;
    }
    button.link {
      border: 0;
      background: transparent;
      color: var(--blue);
      cursor: pointer;
      padding: 0;
      font: inherit;
      text-decoration: underline;
    }
  </style>
</head>
<body>
  <header>
    <h1>Agent Team Read-Only Board</h1>
    <div class="subtitle">Project -> Worktree -> Session. Read-only. Polling every 5 seconds.</div>
  </header>
  <div id="stats" class="stats"></div>
  <main>
    <aside><div id="tree" class="tree"></div></aside>
    <section><div id="detail" class="detail"></div></section>
  </main>
  <script>
    let board = null;
    let selectedSessionId = null;
    const stages = ['Product', 'WaitForCEOApproval', 'Dev', 'QA', 'Acceptance', 'WaitForHumanDecision', 'Done'];

    async function loadBoard() {
      const response = await fetch('/api/board');
      board = await response.json();
      render();
    }

    function allSessions() {
      const sessions = [];
      for (const project of board?.projects || []) {
        for (const worktree of project.worktrees || []) {
          for (const session of worktree.sessions || []) {
            sessions.push({ project, worktree, session });
          }
        }
      }
      return sessions;
    }

    function render() {
      renderStats();
      renderTree();
      renderDetail();
    }

    function renderStats() {
      const stats = board?.stats || {};
      document.getElementById('stats').innerHTML = ['projects', 'worktrees', 'sessions', 'blocked', 'waiting_human', 'submitted_runs']
        .map(key => `<div class="stat"><b>${stats[key] || 0}</b><span>${key}</span></div>`).join('');
    }

    function renderTree() {
      const sessions = allSessions();
      if (!selectedSessionId && sessions.length) selectedSessionId = sessions[0].session.session_id;
      document.getElementById('tree').innerHTML = (board?.projects || []).map(project => `
        <div class="project"><b>${escapeHtml(project.project_name)}</b><br><small>${escapeHtml(project.project_root || 'legacy workspace')}</small></div>
        ${(project.worktrees || []).map(worktree => `
          <div class="worktree"><b>${escapeHtml(worktree.branch || 'unknown branch')}</b><br><small>${escapeHtml(worktree.worktree_path || worktree.state_root)}</small></div>
          ${(worktree.sessions || []).map(session => `
            <div class="session ${session.session_id === selectedSessionId ? 'active' : ''}" onclick="selectSession('${session.session_id}')">
              <b>${escapeHtml(shortText(session.request))}</b><br>
              <small>${escapeHtml(session.current_state)} · ${escapeHtml(session.active_run?.state || 'no run')}</small>
            </div>
          `).join('')}
        `).join('')}
      `).join('');
    }

    function renderDetail() {
      const match = allSessions().find(item => item.session.session_id === selectedSessionId) || allSessions()[0];
      if (!match) {
        document.getElementById('detail').innerHTML = '<div class="card">No sessions found.</div>';
        return;
      }
      selectedSessionId = match.session.session_id;
      const session = match.session;
      const run = session.active_run;
      document.getElementById('detail').innerHTML = `
        <h2>${escapeHtml(shortText(session.request, 90))}</h2>
        <div class="subtitle">${escapeHtml(match.project.project_name)} / ${escapeHtml(match.worktree.branch || 'unknown branch')} / ${escapeHtml(session.session_id)}</div>
        <div class="timeline">${stages.map(stage => `<div class="stage ${session.current_state === stage || session.current_stage === stage ? 'current' : ''}">${stage}</div>`).join('')}</div>
        <div class="card">
          <h3>Workflow</h3>
          <span class="pill ${session.current_state}">${escapeHtml(session.current_state)}</span>
          <p>current_stage: ${escapeHtml(session.current_stage)} · human_decision: ${escapeHtml(session.human_decision)}</p>
          ${session.blocked_reason ? `<p><b>blocked:</b> ${escapeHtml(session.blocked_reason)}</p>` : ''}
        </div>
        <div class="card">
          <h3>Active Run</h3>
          ${run ? `<span class="pill ${run.state}">${escapeHtml(run.state)}</span>
            <p>${escapeHtml(run.stage)} / ${escapeHtml(run.run_id)}</p>
            <p><b>Gate:</b> ${escapeHtml(run.gate_status || 'not verified')}</p>
            <p><b>Required outputs:</b> ${(run.required_outputs || []).map(escapeHtml).join(', ')}</p>
            <p><b>Required evidence:</b> ${(run.required_evidence || []).map(escapeHtml).join(', ')}</p>` : '<p>No active or latest run.</p>'}
        </div>
        <div class="card">
          <h3>Artifacts</h3>
          ${Object.entries(session.artifact_paths || {}).map(([key, path]) => `<p><button class="link" onclick="loadArtifact('${encodeURIComponent(path)}')">${escapeHtml(key)}</button><br><small>${escapeHtml(path)}</small></p>`).join('') || '<p>No artifacts.</p>'}
          <pre id="artifact-preview">Select an artifact to preview.</pre>
        </div>
        <p class="subtitle">Last refreshed: ${escapeHtml(board.generated_at || '')}</p>
      `;
    }

    async function loadArtifact(path) {
      const response = await fetch('/api/artifact?path=' + path);
      document.getElementById('artifact-preview').textContent = await response.text();
    }

    function selectSession(sessionId) {
      selectedSessionId = sessionId;
      render();
    }

    function shortText(value, max = 44) {
      const text = value || '';
      return text.length > max ? text.slice(0, max - 1) + '…' : text;
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[char]));
    }

    loadBoard();
    setInterval(loadBoard, 5000);
  </script>
</body>
</html>
"""
```

- [ ] **Step 4: Implement board server**

Create `agent_team/board_server.py`:

```python
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
```

- [ ] **Step 5: Add `serve-board` CLI**

In `agent_team/cli.py`, import:

```python
from .board_server import create_board_server
```

Add parser:

```python
    serve_board_parser = subparsers.add_parser(
        "serve-board",
        help="Serve the local read-only board.",
    )
    serve_board_parser.add_argument("--all-workspaces", action="store_true")
    serve_board_parser.add_argument("--host", default="127.0.0.1")
    serve_board_parser.add_argument("--port", type=int, default=8765)
    serve_board_parser.add_argument("--poll-interval", type=int, default=5)
    serve_board_parser.set_defaults(handler=_handle_serve_board)
```

Add handler:

```python
def _handle_serve_board(args: argparse.Namespace) -> int:
    if not args.all_workspaces:
        raise SystemExit("serve-board currently requires --all-workspaces.")
    server = create_board_server(host=args.host, port=args.port)
    print(f"board_url: http://{args.host}:{server.server_address[1]}")
    print(f"poll_interval_seconds: {args.poll_interval}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0
```

Note: `poll_interval` is printed for operator clarity. The HTML hardcodes 5 seconds in v1. If implementation needs runtime-configurable polling, add `?pollInterval=...` later; do not expand scope in v1.

- [ ] **Step 6: Run server tests to verify GREEN**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_board_server
```

Expected: `OK`.

- [ ] **Step 7: Commit server slice**

```bash
git add agent_team/board_assets.py agent_team/board_server.py agent_team/cli.py tests/test_board_server.py
git commit -m "feat: serve read-only board"
```

---

### Task 5: Docs And CLI Help Coverage

**Files:**
- Modify: `README.md`
- Modify: `docs/workflow-specs/2026-04-11-agent-team-cli-runtime-usage.md`
- Modify: `docs/workflow-specs/2026-04-11-agent-team-cli-runtime-flow.md`
- Modify: `tests/test_docs.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing docs and help tests**

In `tests/test_docs.py`, update `test_readme_documents_agent_team_cli_usage`:

```python
        self.assertIn("agent-team board-snapshot", readme)
        self.assertIn("agent-team serve-board", readme)
```

In `tests/test_cli.py`, add:

```python
    def test_cli_help_lists_readonly_board_commands(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("board-snapshot", result.stdout)
        self.assertIn("serve-board", result.stdout)
```

- [ ] **Step 2: Run docs/help tests to verify RED**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_docs.DocsTests.test_readme_documents_agent_team_cli_usage tests.test_cli.CliTests.test_cli_help_lists_readonly_board_commands
```

Expected: docs test fails until README is updated. CLI help may already pass if Task 3 and 4 are done.

- [ ] **Step 3: Update README**

Add to the command list:

```markdown
- `agent-team board-snapshot`
- `agent-team serve-board`
```

Add usage examples:

```markdown
输出只读看板 JSON：

```bash
agent-team board-snapshot --all-workspaces
```

启动本地只读看板：

```bash
agent-team serve-board --all-workspaces --port 8765 --poll-interval 5
```
```

Add this boundary note:

```markdown
只读看板只观察 runtime state，不提供 approve、verify、submit、rework 等写操作。
```

- [ ] **Step 4: Update runtime usage docs**

In `docs/workflow-specs/2026-04-11-agent-team-cli-runtime-usage.md`, add:

```markdown
## 只读看板

输出聚合 JSON：

```bash
agent-team board-snapshot --all-workspaces
```

启动本地看板：

```bash
agent-team serve-board --all-workspaces --port 8765 --poll-interval 5
```

看板按 `Project -> Worktree -> Session` 展示所有 workspace 的只读状态，每 5 秒轮询刷新。
```

- [ ] **Step 5: Update runtime flow docs**

In `docs/workflow-specs/2026-04-11-agent-team-cli-runtime-flow.md`, add under "当前事实来源":

```markdown
只读看板读取这些事实来源，但不写入任何 workflow state。
```

Add under command list:

```markdown
- `agent-team board-snapshot`
- `agent-team serve-board`
```

- [ ] **Step 6: Run docs/help tests to verify GREEN**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_docs.DocsTests.test_readme_documents_agent_team_cli_usage tests.test_cli.CliTests.test_cli_help_lists_readonly_board_commands
```

Expected: `OK`.

- [ ] **Step 7: Commit docs slice**

```bash
git add README.md docs/workflow-specs/2026-04-11-agent-team-cli-runtime-usage.md docs/workflow-specs/2026-04-11-agent-team-cli-runtime-flow.md tests/test_docs.py tests/test_cli.py
git commit -m "docs: document read-only board"
```

---

### Task 6: Full Verification

**Files:**
- No new files unless verification reveals a defect.

- [ ] **Step 1: Run full test suite**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Expected: all tests pass.

- [ ] **Step 2: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output and exit code `0`.

- [ ] **Step 3: Confirm `.superpowers/` is ignored**

Run:

```bash
git check-ignore -v .superpowers/
```

Expected: output includes `.gitignore` and `.superpowers/`.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only read-only board implementation, tests, and docs are changed.

- [ ] **Step 5: Commit any final fixes**

If Task 6 revealed fixups, commit them:

```bash
git add <changed-files>
git commit -m "fix: stabilize read-only board"
```

If no fixups exist, do not create an empty commit.

---

## Self-Review

- Spec coverage: Tasks cover workspace metadata, all-workspace aggregation, `board-snapshot`, `serve-board`, `/api/board`, `/api/artifact`, polling HTML, read-only boundaries, docs, and tests.
- Placeholder scan: No step depends on TBD behavior; every created module has a concrete responsibility and code shape.
- Type consistency: `WorkspaceMetadata`, `BoardSnapshot`, `build_board_snapshot`, `build_board_snapshot_with_roots`, `create_board_server`, `board-snapshot`, and `serve-board` are named consistently across tasks.
- Scope check: The plan keeps v1 local, read-only, file-backed, polling-based, and dependency-free.
