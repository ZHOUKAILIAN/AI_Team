from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from .models import WorkflowSummary
from .state import StateStore
from .status import build_status_overview


DEFAULT_PANEL_HOST = "127.0.0.1"
DEFAULT_PANEL_PORT = 8765


def build_panel_snapshot(
    store: StateStore,
    session_id: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    session = store.load_session(session_id)
    summary = store.load_workflow_summary(session_id)
    events = store.read_session_events(session_id)
    contract = _read_json_artifact(summary.artifact_paths.get("acceptance_contract", ""))
    review_completion = _read_json_artifact(summary.artifact_paths.get("review_completion", ""))

    required_evidence = list(contract.get("required_evidence", []))
    evidence_provided = list(review_completion.get("evidence_provided", []))
    pending_evidence = [item for item in required_evidence if item not in evidence_provided]

    session_payload = _read_json(session.session_dir / "session.json")
    stage_records = list(session_payload.get("stage_records", []))

    return {
        "overview": build_status_overview(summary=summary, state_root=store.root, repo_root=repo_root),
        "session": {
            "session_id": session.session_id,
            "request": session.request,
            "raw_message": session.raw_message or "",
            "created_at": session.created_at,
            "session_dir": str(session.session_dir),
            "artifact_dir": str(session.artifact_dir),
            "state_root": str(store.root),
        },
        "state": summary.to_dict(),
        "operator": {
            "current_action": _current_action(summary),
            "next_action": _next_action(summary),
            "blocked_reason": summary.blocked_reason,
            "latest_event": events[-1] if events else None,
        },
        "evidence": {
            "required": required_evidence,
            "provided": evidence_provided,
            "pending": pending_evidence,
            "acceptance_criteria": list(contract.get("acceptance_criteria", [])),
            "unresolved_items": list(review_completion.get("unresolved_items", [])),
        },
        "artifacts": _artifact_rows(summary),
        "stages": stage_records,
        "events": events,
    }


def list_panel_sessions(store: StateStore) -> dict[str, list[dict[str, Any]]]:
    if not store.root.exists():
        return {"active": [], "archived": []}

    active_sessions: list[dict[str, Any]] = []
    archived_sessions: list[dict[str, Any]] = []
    for session_dir in sorted(store.root.iterdir(), reverse=True):
        if not session_dir.is_dir() or not (session_dir / "session.json").exists():
            continue
        session_payload = _read_json(session_dir / "session.json")
        if not session_payload:
            continue
        session_id = session_dir.name
        try:
            summary = store.load_workflow_summary(session_id)
        except FileNotFoundError:
            summary = WorkflowSummary(
                session_id=session_id,
                runtime_mode="unknown",
                current_state="unknown",
                current_stage="unknown",
            )
        session_row = {
            "session_id": session_id,
            "request": session_payload.get("request", ""),
            "created_at": session_payload.get("created_at", ""),
            "current_state": summary.current_state,
            "current_stage": summary.current_stage,
            "acceptance_status": summary.acceptance_status,
            "blocked_reason": summary.blocked_reason,
            "archived": summary.current_state == "Done",
        }
        if session_row["archived"]:
            archived_sessions.append(session_row)
        else:
            active_sessions.append(session_row)
    return {"active": active_sessions, "archived": archived_sessions}


def render_panel_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Agent Team Runtime Panel</title>
  <style>
    :root {
      --bg: #101820;
      --panel: #f8efe0;
      --panel-soft: #fff9ed;
      --ink: #17202a;
      --muted: #6b6258;
      --line: #d9cbb9;
      --accent: #d44a2f;
      --accent-2: #27746f;
      --good: #27746f;
      --warn: #b36b00;
      --bad: #b32525;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 10%, rgba(212, 74, 47, 0.35), transparent 28rem),
        radial-gradient(circle at 90% 0%, rgba(39, 116, 111, 0.34), transparent 30rem),
        linear-gradient(135deg, #101820 0%, #1d2830 54%, #3c2c24 100%);
      font-family: "Avenir Next", "Trebuchet MS", sans-serif;
    }
    .shell {
      display: grid;
      grid-template-columns: 22rem minmax(0, 1fr);
      gap: 1rem;
      padding: 1rem;
      min-height: 100vh;
    }
    aside, main {
      border: 1px solid rgba(248, 239, 224, 0.46);
      border-radius: 1.25rem;
      background: rgba(248, 239, 224, 0.94);
      box-shadow: 0 1.5rem 4rem rgba(0, 0, 0, 0.28);
    }
    aside {
      padding: 1rem;
      overflow: auto;
    }
    main {
      padding: 1.25rem;
      overflow: hidden;
    }
    h1, h2, h3, p { margin-top: 0; }
    h1 {
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(2rem, 4vw, 4.5rem);
      line-height: 0.94;
      letter-spacing: -0.06em;
      margin-bottom: 0.6rem;
    }
    h2 {
      font-size: 0.9rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 0.75rem;
    }
    .session {
      display: block;
      width: 100%;
      text-align: left;
      border: 1px solid var(--line);
      border-radius: 0.9rem;
      background: var(--panel-soft);
      padding: 0.85rem;
      margin-bottom: 0.7rem;
      cursor: pointer;
    }
    .session.active { border-color: var(--accent); box-shadow: inset 0.25rem 0 0 var(--accent); }
    .session strong, .metric strong { display: block; }
    .session span, .metric span, .path, .meta { color: var(--muted); font-size: 0.86rem; }
    .session-group { margin-bottom: 1.2rem; }
    .session-group:last-child { margin-bottom: 0; }
    .session-group h3 {
      margin: 0 0 0.6rem;
      font-size: 0.8rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 18rem;
      gap: 1rem;
      align-items: stretch;
      margin-bottom: 1rem;
    }
    .action {
      border-radius: 1.25rem;
      padding: 1.2rem;
      background: linear-gradient(135deg, #fff9ed 0%, #f5ddc5 100%);
      border: 1px solid var(--line);
    }
    .action p { font-size: 1.15rem; line-height: 1.45; }
    .metrics {
      display: grid;
      gap: 0.75rem;
    }
    .metric {
      border-radius: 1rem;
      border: 1px solid var(--line);
      background: var(--panel-soft);
      padding: 0.85rem;
    }
    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 1rem;
    }
    section {
      border-radius: 1rem;
      border: 1px solid var(--line);
      background: rgba(255, 249, 237, 0.82);
      padding: 1rem;
      min-width: 0;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      background: #ead6bd;
      color: var(--ink);
      padding: 0.35rem 0.65rem;
      margin: 0 0.35rem 0.35rem 0;
      font-size: 0.85rem;
    }
    .pill.pending { background: #f4cf9f; color: #6b3900; }
    .pill.good { background: #b9d9d4; color: #153d3a; }
    .blocked { color: var(--bad); font-weight: 700; }
    .timeline {
      display: grid;
      gap: 0.7rem;
      max-height: 28rem;
      overflow: auto;
    }
    .event {
      border-left: 0.25rem solid var(--accent-2);
      padding-left: 0.75rem;
    }
    .event.blocked, .event.feedback_recorded { border-left-color: var(--bad); }
    .artifact {
      display: grid;
      gap: 0.2rem;
      padding: 0.65rem 0;
      border-bottom: 1px solid var(--line);
    }
    .artifact:last-child { border-bottom: 0; }
    code {
      word-break: break-all;
      background: rgba(16, 24, 32, 0.08);
      padding: 0.15rem 0.25rem;
      border-radius: 0.25rem;
    }
    @media (max-width: 900px) {
      .shell, .hero, .grid { grid-template-columns: 1fr; }
      aside { max-height: 20rem; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <h2>Sessions</h2>
      <div id="sessions">Loading...</div>
    </aside>
    <main>
      <div class="hero">
        <div class="action">
          <h1>Agent Team Runtime Panel</h1>
          <h2>Current Action</h2>
          <p id="current-action">Loading session...</p>
          <p id="blocked"></p>
        </div>
        <div class="metrics">
          <div class="metric"><span>Project</span><strong id="project">-</strong></div>
          <div class="metric"><span>Role</span><strong id="role">-</strong></div>
          <div class="metric"><span>Status</span><strong id="status">-</strong></div>
        </div>
      </div>
      <div class="grid">
        <section>
          <h2>Next Action</h2>
          <p id="next-action">-</p>
          <h2>Evidence</h2>
          <div id="evidence"></div>
        </section>
        <section>
          <h2>Recent Events</h2>
          <div class="timeline" id="events"></div>
        </section>
        <section>
          <h2>Artifacts</h2>
          <div id="artifacts"></div>
        </section>
        <section>
          <h2>Request</h2>
          <p id="request"></p>
        </section>
      </div>
    </main>
  </div>
  <script>
    const params = new URLSearchParams(location.search);
    let selectedSessionId = params.get("session_id");

    async function loadSessions() {
      const response = await fetch("/api/sessions");
      const sessions = await response.json();
      const activeSessions = sessions.active || [];
      const archivedSessions = sessions.archived || [];
      const allSessions = [...activeSessions, ...archivedSessions];
      const container = document.getElementById("sessions");
      if (!allSessions.length) {
        container.textContent = "No sessions yet.";
        return;
      }
      const selectedStillExists = allSessions.some(session => session.session_id === selectedSessionId);
      if (!selectedSessionId || !selectedStillExists) {
        selectedSessionId = (activeSessions[0] || archivedSessions[0]).session_id;
      }
      container.innerHTML = renderSessionGroup("Active", activeSessions)
        + renderSessionGroup("Archived", archivedSessions);
      container.querySelectorAll("button").forEach(button => {
        button.addEventListener("click", () => {
          selectedSessionId = button.dataset.sessionId;
          params.set("session_id", selectedSessionId);
          history.replaceState(null, "", `?${params.toString()}`);
          loadSessions();
          loadSnapshot();
        });
      });
      await loadSnapshot();
    }

    function renderSessionGroup(title, sessions) {
      if (!sessions.length) return "";
      return `
        <div class="session-group">
          <h3>${escapeHtml(title)}</h3>
          ${sessions.map(session => `
            <button class="session ${session.session_id === selectedSessionId ? "active" : ""}"
                    data-session-id="${session.session_id}">
              <strong>${escapeHtml(session.current_stage)} · ${escapeHtml(session.current_state)}</strong>
              <span>${escapeHtml(session.request || session.session_id)}</span>
            </button>`).join("")}
        </div>`;
    }

    async function loadSnapshot() {
      if (!selectedSessionId) return;
      const query = new URLSearchParams({session_id: selectedSessionId});
      const response = await fetch(`/api/session?${query.toString()}`);
      const snapshot = await response.json();
      document.getElementById("current-action").textContent = snapshot.overview.text;
      document.getElementById("next-action").textContent = snapshot.operator.next_action;
      document.getElementById("project").textContent = snapshot.overview.project;
      document.getElementById("role").textContent = snapshot.overview.role;
      document.getElementById("status").textContent = snapshot.overview.status;
      document.getElementById("request").textContent = snapshot.session.request;
      document.getElementById("blocked").innerHTML = snapshot.operator.blocked_reason
        ? `<span class="blocked">${escapeHtml(snapshot.operator.blocked_reason)}</span>`
        : "";
      renderEvidence(snapshot.evidence);
      renderEvents(snapshot.events);
      renderArtifacts(snapshot.artifacts);
    }

    function renderEvidence(evidence) {
      const rows = [];
      for (const item of evidence.required) {
        const pending = evidence.pending.includes(item);
        rows.push(`<span class="pill ${pending ? "pending" : "good"}">${escapeHtml(item)}</span>`);
      }
      if (evidence.unresolved_items.length) {
        rows.push(`<p class="blocked">${escapeHtml(evidence.unresolved_items.join("; "))}</p>`);
      }
      document.getElementById("evidence").innerHTML = rows.join("") || "<span class='meta'>No explicit evidence contract.</span>";
    }

    function renderEvents(events) {
      document.getElementById("events").innerHTML = events.slice(-20).reverse().map(event => `
        <div class="event ${escapeHtml(event.kind)}">
          <strong>${escapeHtml(event.kind)} · ${escapeHtml(event.stage || event.state || "")}</strong>
          <div>${escapeHtml(event.message || "")}</div>
          <span class="meta">${escapeHtml(event.at || "")}</span>
        </div>`).join("") || "<span class='meta'>No events yet.</span>";
    }

    function renderArtifacts(artifacts) {
      document.getElementById("artifacts").innerHTML = artifacts.map(item => `
        <div class="artifact">
          <strong>${escapeHtml(item.name)} ${item.exists ? "" : "(missing)"}</strong>
          <code>${escapeHtml(item.path)}</code>
        </div>`).join("") || "<span class='meta'>No artifacts yet.</span>";
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
      }[char]));
    }

    loadSessions();
    setInterval(loadSnapshot, 2000);
  </script>
</body>
</html>
"""


def create_panel_server(
    store: StateStore,
    *,
    session_id: str | None = None,
    repo_root: Path | None = None,
    host: str = DEFAULT_PANEL_HOST,
    port: int = DEFAULT_PANEL_PORT,
) -> ThreadingHTTPServer:
    handler = _build_handler(store=store, default_session_id=session_id, repo_root=repo_root)
    return ThreadingHTTPServer((host, port), handler)


def run_panel_server(
    store: StateStore,
    *,
    session_id: str | None = None,
    repo_root: Path | None = None,
    host: str = DEFAULT_PANEL_HOST,
    port: int = DEFAULT_PANEL_PORT,
    open_browser: bool = False,
) -> None:
    server = create_panel_server(store, session_id=session_id, repo_root=repo_root, host=host, port=port)
    selected_session = session_id or store.latest_session_id()
    query = f"?{urlencode({'session_id': selected_session})}" if selected_session else ""
    url = f"http://{server.server_address[0]}:{server.server_address[1]}/{query}"
    print(f"panel_url: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_handler(store: StateStore, default_session_id: str | None, repo_root: Path | None):
    class PanelRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._send_text(render_panel_html(), content_type="text/html; charset=utf-8")
                return
            if parsed.path == "/api/sessions":
                self._send_json(list_panel_sessions(store))
                return
            if parsed.path == "/api/session":
                query = parse_qs(parsed.query)
                requested_session = query.get("session_id", [default_session_id or store.latest_session_id()])[0]
                if not requested_session:
                    self._send_json({"error": "No workflow session exists yet."}, status=404)
                    return
                try:
                    self._send_json(build_panel_snapshot(store, requested_session, repo_root=repo_root))
                except FileNotFoundError as error:
                    self._send_json({"error": str(error)}, status=404)
                return
            self._send_json({"error": "Not found."}, status=404)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, payload: object, *, status: int = 200) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, payload: str, *, content_type: str, status: int = 200) -> None:
            body = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return PanelRequestHandler


def _current_action(summary: WorkflowSummary) -> str:
    if summary.blocked_reason:
        return f"{summary.current_stage} is blocked and needs evidence or rework before progress can continue."
    return {
        "Intake": "Intake captured the request. Product should draft the PRD and acceptance criteria next.",
        "ProductDraft": "Product is drafting or has drafted the PRD for CEO approval.",
        "WaitForCEOApproval": "Waiting for CEO approval before Dev starts implementation.",
        "Dev": "Dev should implement the approved PRD and submit the implementation bundle.",
        "QA": "QA should independently verify Dev output and submit evidence-backed findings.",
        "Acceptance": "Acceptance should validate the product outcome against the PRD and evidence contract.",
        "WaitForHumanDecision": "Waiting for the human Go/No-Go decision.",
    }.get(summary.current_state, f"{summary.current_stage} is active.")


def _next_action(summary: WorkflowSummary) -> str:
    if summary.blocked_reason:
        return f"Resolve blocker: {summary.blocked_reason}"
    if summary.current_state in {"Intake", "ProductDraft"}:
        return "Run Product with the current stage contract, then submit Product result."
    if summary.current_state == "WaitForCEOApproval":
        return "Review PRD, then record human decision: go, no-go, or rework."
    if summary.current_state == "Dev":
        return "Run Dev against the approved PRD and submit implementation evidence."
    if summary.current_state == "QA":
        return "Run QA independently and submit QA result with rerun evidence."
    if summary.current_state == "Acceptance":
        return "Run Acceptance and submit recommendation plus required review artifacts."
    if summary.current_state == "WaitForHumanDecision":
        return "Record the final human Go/No-Go decision."
    return "Inspect the latest event and workflow summary before continuing."


def _artifact_rows(summary: WorkflowSummary) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in sorted(summary.artifact_paths):
        path = summary.artifact_paths[name]
        rows.append({"name": name, "path": path, "exists": Path(path).exists()})
    return rows


def _read_json_artifact(path_value: str) -> dict[str, Any]:
    if not path_value:
        return {}
    return _read_json(Path(path_value))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
