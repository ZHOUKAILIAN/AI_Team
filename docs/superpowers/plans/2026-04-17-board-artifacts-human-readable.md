# Board Artifacts Human-Readable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the read-only board `Artifacts` area from a path list into human-readable artifact cards grouped by business output and runtime metadata.

**Architecture:** Keep this as a frontend-only rendering change inside the embedded board HTML. Reuse existing `/api/board` and `/api/artifact` data and safety rules. Add JavaScript mapping helpers that translate artifact keys into Chinese titles, descriptions, categories, and filenames.

**Tech Stack:** Python standard-library HTTP server, embedded HTML/CSS/JavaScript string, `unittest`.

---

## File Structure

- Modify: `agent_team/board_assets.py`
  - Add artifact metadata mapping helpers.
  - Render artifact cards by group.
  - Update preview header when an artifact is selected.
- Modify: `tests/test_board_server.py`
  - Assert the served HTML includes the artifact rendering helpers and human-readable Chinese labels.

## Task 1: Human-Readable Artifact Cards

**Files:**
- Modify: `tests/test_board_server.py`
- Modify: `agent_team/board_assets.py`

- [ ] **Step 1: Write failing HTML assertions**

In `tests/test_board_server.py`, extend `test_board_server_serves_html_and_board_json` with these assertions:

```python
self.assertIn("function renderArtifactSections", html)
self.assertIn("function artifactMetadataFor", html)
self.assertIn("产品方案 / PRD", html)
self.assertIn("运行时元数据", html)
self.assertIn("预览内容", html)
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_board_server.BoardServerTests.test_board_server_serves_html_and_board_json
```

Expected: fail because the HTML still renders a raw artifact path list.

- [ ] **Step 3: Implement artifact card rendering**

In `agent_team/board_assets.py`:

- Replace the raw `Object.entries(session.artifact_paths || {})` list with `renderArtifactSections(session)`.
- Add `artifactMetadataFor(key, path)` returning category, title, description, filename, and path.
- Add `renderArtifactSections(session)` grouping cards into `业务产物`, `运行时元数据`, and `其他产物`.
- Change `loadArtifact(path)` to `loadArtifact(path, title)` and update `#artifact-preview-title`.
- Keep full path as subdued helper text, not the primary label.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_board_server
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add agent_team/board_assets.py tests/test_board_server.py
git commit -m "feat: render readable board artifacts"
```

## Verification

After implementation, run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_board_server
git diff --check
```
