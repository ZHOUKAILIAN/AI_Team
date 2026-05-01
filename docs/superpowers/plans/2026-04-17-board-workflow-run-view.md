# Board Workflow Run View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the board detail view from a stage strip plus raw fields into a human-readable workflow run board.

**Architecture:** Keep the change inside the embedded board HTML and derive workflow explanations from the existing session snapshot fields. Add frontend helpers to produce a bottleneck summary and node cards for the fixed workflow stages without changing the backend API.

**Tech Stack:** Python standard-library HTTP server, embedded HTML/CSS/JavaScript string, `unittest`.

---

## File Structure

- Modify: `tests/test_board_server.py`
  - Assert the served HTML includes workflow run helpers and human-readable legacy run messaging.
- Modify: `agent_team/board_assets.py`
  - Replace the current detail header section with a bottleneck summary and workflow run board.
  - Add helper functions that map snapshot data into workflow node cards, statuses, explanations, and next actions.

## Task 1: Workflow Run Board

**Files:**
- Modify: `tests/test_board_server.py`
- Modify: `agent_team/board_assets.py`

- [ ] **Step 1: Write failing HTML assertions**

Extend `test_board_server_serves_html_and_board_json` with:

```python
self.assertIn("function renderWorkflowRunBoard", html)
self.assertIn("function renderBottleneckSummary", html)
self.assertIn("function workflowNodesFor", html)
self.assertIn("还没有可跟踪的 QA run", html)
self.assertIn("当前 bottleneck", html)
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_board_server.BoardServerTests.test_board_server_serves_html_and_board_json
```

Expected: fail because the page still renders the old stage-strip-focused detail view.

- [ ] **Step 3: Implement the workflow run board**

In `agent_team/board_assets.py`:

- Add CSS for a bottleneck banner and workflow node grid.
- Replace the current timeline-first detail block with:
  - `renderBottleneckSummary(session)`
  - `renderWorkflowRunBoard(session)`
- Add `workflowNodesFor(session)` for the fixed stages:
  - `Product`
  - `WaitForCEOApproval`
  - `Dev`
  - `QA`
  - `Acceptance`
  - `WaitForHumanDecision`
  - `Done`
- Add helper functions to derive:
  - human-readable node status
  - node owner
  - node reason
  - node deliverables
  - next action text
- For legacy sessions whose current stage has no run, surface human text like:
  - `当前阶段已经进入 QA，但还没有可跟踪的 QA run`

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_board_server
```

Expected: `OK`.

- [ ] **Step 5: Run formatting verification**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add agent_team/board_assets.py tests/test_board_server.py
git commit -m "feat: render workflow run board"
```
