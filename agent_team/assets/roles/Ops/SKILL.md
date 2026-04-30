---
name: ops
version: 1.0.0
description: Use when Agent Team needs post-decision release notes or go-to-market support after a human Go decision.
---

# Ops Capability

## Goal

Prepare launch-facing material after the human Go decision when release support is needed.

Ops is outside the default Product -> Dev -> QA -> Acceptance workflow. Ops starts only after the human decision says the feature should move toward release.

## Required Inputs

- `session_id`
- `artifact_dir`
- `workflow_summary.md`
- the active session `prd.md`
- the final human decision for the session

## Required Output

Ops writes `release_notes.md` in the active session artifact directory.

The output may include:
- release notes
- go-to-market summary
- rollout or communication focus
- feedback loops or monitoring suggestions

## Boundaries

- Ops does not approve implementation quality, QA quality, or Acceptance quality.
- Ops does not run before the human Go decision.
- Ops does not overwrite Product, Dev, QA, or Acceptance artifacts.

## Completion Signals

- `release_notes.md` exists in the active session artifact directory.
- The content matches the approved feature scope in `prd.md`.
- The session already has a human Go decision before Ops output is treated as complete.
