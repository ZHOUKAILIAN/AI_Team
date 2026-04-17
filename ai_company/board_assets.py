BOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI_Team Read-Only Board</title>
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
        linear-gradient(135deg, var(--paper), #e9eef2);
    }
    header {
      padding: 22px 28px;
      border-bottom: 1px solid var(--line);
      background: rgba(255,255,255,.72);
      backdrop-filter: blur(10px);
    }
    h1 { margin: 0; font-size: 28px; }
    h2, h3 { margin-top: 0; }
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
    .tree, .detail { padding: 18px; }
    .project, .worktree, .session {
      border-radius: 12px;
      padding: 10px;
      margin-bottom: 8px;
      word-break: break-word;
    }
    .project { background: var(--ink); color: var(--paper); }
    .worktree { margin-left: 14px; background: #eef3f6; }
    .session { margin-left: 28px; background: #fff; border: 1px solid var(--line); cursor: pointer; }
    .session.active { border-color: var(--blue); box-shadow: 0 0 0 2px rgba(47,111,159,.16); }
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
    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 16px 16px 0;
    }
    .filter {
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fff;
      color: var(--ink);
      cursor: pointer;
      font: inherit;
      font-size: 13px;
      padding: 6px 10px;
    }
    .filter.active {
      background: var(--ink);
      border-color: var(--ink);
      color: var(--paper);
    }
    .session-meta {
      color: var(--muted);
      display: block;
      margin-top: 4px;
    }
    @media (max-width: 860px) {
      .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      main { grid-template-columns: 1fr; }
      .timeline { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <header>
    <h1>AI_Team Read-Only Board</h1>
    <div class="subtitle">Project -> Worktree -> Session. Read-only. Polling every 5 seconds.</div>
  </header>
  <div id="stats" class="stats"></div>
  <main>
    <aside><div id="filters" class="filters"></div><div id="tree" class="tree"></div></aside>
    <section><div id="detail" class="detail"></div></section>
  </main>
  <script>
    let board = null;
    let selectedSessionId = null;
    let currentFilter = 'all';
    const stages = ['Product', 'WaitForCEOApproval', 'Dev', 'QA', 'Acceptance', 'WaitForHumanDecision', 'Done'];
    const filterDefinitions = [
      { key: 'all', label: 'All' },
      { key: 'active', label: 'Active' },
      { key: 'waiting_human', label: 'Waiting Human' },
      { key: 'has_run', label: 'Has Run' },
      { key: 'empty', label: 'Empty' }
    ];

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
      renderFilters();
      renderTree();
      renderDetail();
    }

    function renderStats() {
      const stats = board?.stats || {};
      const keys = ['projects', 'worktrees', 'sessions', 'blocked', 'waiting_human', 'submitted_runs'];
      document.getElementById('stats').innerHTML = keys
        .map(key => `<div class="stat"><b>${stats[key] || 0}</b><span>${key}</span></div>`).join('');
    }

    function renderFilters() {
      document.getElementById('filters').innerHTML = filterDefinitions.map(item => {
        const count = countSessionsForFilter(item.key);
        return `<button class="filter ${currentFilter === item.key ? 'active' : ''}" onclick="selectFilter('${item.key}')">${item.label} ${count}</button>`;
      }).join('');
    }

    function renderTree() {
      const visible = visibleSessions();
      if (!visible.some(item => item.session.session_id === selectedSessionId)) {
        selectedSessionId = visible.length ? visible[0].session.session_id : null;
      }
      const treeHtml = (board?.projects || []).map(project => {
        const worktreeHtml = (project.worktrees || []).map(worktree => {
          const sessions = (worktree.sessions || []).filter(sessionMatchesCurrentFilter);
          if (!sessions.length) return '';
          return `
          <div class="worktree"><b>${escapeHtml(worktree.branch || 'unknown branch')}</b><br><small>${escapeHtml(worktree.worktree_path || worktree.state_root)}</small></div>
          ${sessions.map(session => `
            <div class="session ${session.session_id === selectedSessionId ? 'active' : ''}" onclick="selectSession('${session.session_id}')">
              <b>${escapeHtml(shortText(session.request))}</b><br>
              <small>${escapeHtml(session.current_state)} / ${escapeHtml(session.active_run?.state || 'no run')}</small>
              <small class="session-meta">${escapeHtml(formatSessionMeta(session))}</small>
            </div>
          `).join('')}
        `;
        }).join('');
        if (!worktreeHtml) return '';
        return `
          <div class="project"><b>${escapeHtml(project.project_name)}</b><br><small>${escapeHtml(project.project_root || 'legacy workspace')}</small></div>
          ${worktreeHtml}
        `;
      }).join('');
      document.getElementById('tree').innerHTML = treeHtml || `<div class="card">No sessions match ${escapeHtml(currentFilterLabel())}.</div>`;
    }

    function renderDetail() {
      const sessions = visibleSessions();
      const match = sessions.find(item => item.session.session_id === selectedSessionId) || sessions[0];
      if (!match) {
        document.getElementById('detail').innerHTML = `<div class="card">No sessions match ${escapeHtml(currentFilterLabel())}.</div>`;
        return;
      }
      selectedSessionId = match.session.session_id;
      const session = match.session;
      const run = session.active_run;
      document.getElementById('detail').innerHTML = `
        <h2>${escapeHtml(shortText(session.request, 90))}</h2>
        <div class="subtitle">${escapeHtml(match.project.project_name)} / ${escapeHtml(match.worktree.branch || 'unknown branch')} / ${escapeHtml(formatSessionMeta(session))}</div>
        <div class="timeline">${stages.map(stage => `<div class="stage ${session.current_state === stage || session.current_stage === stage ? 'current' : ''}">${stage}</div>`).join('')}</div>
        <div class="card">
          <h3>Workflow</h3>
          <span class="pill ${session.current_state}">${escapeHtml(session.current_state)}</span>
          <p>current_stage: ${escapeHtml(session.current_stage)} / human_decision: ${escapeHtml(session.human_decision)}</p>
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
        <p class="subtitle">Last refreshed: ${escapeHtml(formatRefreshTime(board.generated_at))}</p>
      `;
    }

    async function loadArtifact(path) {
      const response = await fetch('/api/artifact?path=' + path);
      document.getElementById('artifact-preview').textContent = await response.text();
    }

    function visibleSessions() {
      return allSessions().filter(item => sessionMatchesCurrentFilter(item.session));
    }

    function sessionMatchesCurrentFilter(session) {
      return sessionMatchesFilter(session, currentFilter);
    }

    function sessionMatchesFilter(session, filterKey) {
      if (filterKey === 'empty') return isEmptySession(session);
      if (filterKey === 'has_run') return Boolean(session.active_run);
      if (filterKey === 'waiting_human') return session.workflow_status === 'waiting_human'
        || session.current_state === 'WaitForCEOApproval'
        || session.current_state === 'WaitForHumanDecision';
      if (filterKey === 'active') return !isEmptySession(session) && session.current_state !== 'Done';
      return true;
    }

    function isEmptySession(session) {
      return session.current_state === 'Intake' && !session.active_run;
    }

    function countSessionsForFilter(filterKey) {
      return allSessions().filter(item => sessionMatchesFilter(item.session, filterKey)).length;
    }

    function selectFilter(filterKey) {
      currentFilter = filterKey;
      render();
    }

    function selectSession(sessionId) {
      selectedSessionId = sessionId;
      render();
    }

    function currentFilterLabel() {
      return filterDefinitions.find(item => item.key === currentFilter)?.label || 'All';
    }

    function shortText(value, max = 44) {
      const text = value || '';
      return text.length > max ? text.slice(0, max - 3) + '...' : text;
    }

    function formatSessionMeta(session) {
      const createdAt = formatSessionDateTime(session.created_at);
      const id = shortSessionId(session.session_id);
      return createdAt ? `${createdAt} / ${id}` : id;
    }

    function formatSessionDateTime(value) {
      if (!value) return '';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return new Intl.DateTimeFormat(undefined, {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      }).format(date);
    }

    function shortSessionId(value) {
      const text = value || '';
      return text.length > 20 ? text.slice(0, 20) + '...' : text;
    }

    function formatRefreshTime(value) {
      if (!value) return '';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return new Intl.DateTimeFormat(undefined, {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      }).format(date);
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
