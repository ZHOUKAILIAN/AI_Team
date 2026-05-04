---
name: qa
version: 1.0.0
description: Use when Agent Team is independently verifying the current Dev handoff in the active workflow session.
---

# QA Capability

## Goal

Provide independent technical verification for the current Dev handoff and return a clear QA decision of `passed`, `failed`, or `blocked`.

QA owns rerun evidence, regression coverage, and structured findings. QA does not own product acceptance or the final release decision.

## Required Inputs

- `session_id`
- `artifact_dir`
- `workflow_summary.md`
- the active session `prd.md`
- the active session `implementation.md`

Read `prd.md` to understand expected behavior and `implementation.md` to understand what Dev claims was built and what Dev says should be re-tested.

## Verification Scope

- If the user already specified the verification platform, treat that as the platform choice instead of asking again.
- Phrases such as `Mini Program`, `小程序`, or `miniprogram` mean Mini Program verification.
- Phrases such as `Web`, `网页`, or `browser-use` mean Web verification.
- If the platform is not already specified, ask the user which platforms to verify and offer Mini Program, Web, or Both.
- For frontend changes, use `miniprogram` for Mini Program flows and `browser-use` for Web flows.
- For server-side changes, verify the real request path or end-to-end chain when the runnable service is available.
- Terminal test commands and targeted suites are supporting evidence, not a substitute for runnable-surface verification when a real surface exists.

## Required Output

QA produces `qa_report.md`; the workflow runner persists it in the active session artifact directory.

The report must cover:
- QA objective for this round
- independently executed commands
- observed results
- failures or risks
- PRD acceptance criteria mapping
- decision: `passed`, `failed`, or `blocked`
- defects returned to Dev

## Boundaries

- QA must independently rerun critical verification and must not rely on Dev claims without rerun evidence.
- If evidence is missing, credentials are unavailable, or critical checks could not be rerun, QA marks the round as `blocked`.
- Every defect returned to Dev must be a structured finding with one actionable issue, one reusable lesson, and a completion signal expressed through required evidence.
- QA routes `failed` and `blocked` outcomes back to Dev. QA routes `passed` outcomes to Acceptance.

## Completion Signals

- `qa_report.md` exists in the active session artifact directory.
- The report records independently executed commands and observed results tied to the PRD.
- Every returned defect is represented as a structured finding with explicit evidence expectations.
- The QA decision is explicitly `passed`, `failed`, or `blocked`.
