# Agent Team Review Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist review contracts at intake, block incomplete review-only workflows from closing, block unapproved host environment mutations, and align the local `figma-restoration-review` skill with those gates.

**Architecture:** Add a structured acceptance contract to intake/session state, introduce a completion-gate evaluator that runs after Acceptance, and update the local Figma review skill so its output contract matches the Agent Team runtime. Keep the changes additive and backwards-compatible for existing deterministic flows.

**Tech Stack:** Python 3, unittest, Markdown skills/docs

---

### Task 1: Acceptance Contract Persistence

**Files:**
- Modify: `agent_team/models.py`
- Modify: `agent_team/intake.py`
- Modify: `agent_team/state.py`
- Test: `tests/test_intake.py`
- Test: `tests/test_state.py`

- [ ] Add failing tests for parsing and persisting structured acceptance contracts.
- [ ] Run the new tests and confirm they fail for the missing contract behavior.
- [ ] Implement the minimal parsing and persistence changes.
- [ ] Re-run the focused tests until they pass.

### Task 2: Completion And Environment Gates

**Files:**
- Create: `agent_team/completion_gate.py`
- Modify: `agent_team/models.py`
- Modify: `agent_team/orchestrator.py`
- Modify: `agent_team/review.py`
- Modify: `agent_team/workflow_summary.py`
- Test: `tests/test_completion_gate.py`
- Test: `tests/test_orchestrator.py`

- [ ] Add failing tests for missing review artifacts, missing runtime evidence, and blocked host-environment mutation.
- [ ] Run the focused tests and confirm the failures are caused by absent gates.
- [ ] Implement the gate evaluator and wire it into the orchestrator summary/review.
- [ ] Re-run the focused tests until they pass.

### Task 3: Docs, CLI, And Skill Contract Parity

**Files:**
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `SKILL.md`
- Modify: `Acceptance/SKILL.md`
- Modify: `codex-skill/agent-team-workflow/SKILL.md`
- Test: `tests/test_docs.py`
- Test: `tests/test_skill_package.py`

- [ ] Add failing assertions for acceptance contracts, completion gates, and environment mutation policy.
- [ ] Run the doc/skill tests and confirm the gaps fail.
- [ ] Update the docs and skills to match the runtime contract.
- [ ] Re-run the tests until they pass.

### Task 4: Local `figma-restoration-review` Skill Hardening

**Files:**
- Modify: `/Users/zhoukailian/Desktop/mySelf/skills/figma-restoration-review/SKILL.md`
- Modify: `/Users/zhoukailian/Desktop/mySelf/skills/figma-restoration-review/skill.json`

- [ ] Patch the skill text so geometry tolerance, native-node exclusions, unresolved items, and review-only boundaries are unambiguous.
- [ ] Re-read the final skill and verify the contradictions are gone.

### Task 5: Final Verification

**Files:**
- Test: `tests/test_cli.py`
- Test: `tests/test_intake.py`
- Test: `tests/test_completion_gate.py`
- Test: `tests/test_orchestrator.py`
- Test: `tests/test_state.py`
- Test: `tests/test_docs.py`
- Test: `tests/test_skill_package.py`
- Test: `tests/test_review.py`

- [ ] Run the focused suites for the new contract and gate behavior.
- [ ] Run the broader regression suite for Agent Team.
- [ ] Summarize what changed, which gaps are now enforced by code, and any remaining manual boundaries.
