---
name: product
version: 1.0.0
description: Use when AI_Team is drafting or revising the Product stage for the active workflow session.
---

# Product Capability

## Goal

Create the Product handoff that lets the human decide whether Dev may start.

Product owns the requirement framing, user scenarios, acceptance criteria, and CEO confirmation questions. Product does not implement, verify, or advance the workflow into Dev.

## Required Inputs

- `session_id`
- `artifact_dir`
- `workflow_summary.md`
- the normalized request in `request.md`
- any existing artifacts in the active session artifact directory

Never guess a flat artifact path from another session. Use the artifact directory provided by the workflow runner.

## Required Output

Product writes `prd.md` in the active session artifact directory.

The PRD must cover:
- raw request
- problem statement
- goals
- non-goals
- user scenarios
- acceptance criteria
- QA verification focus
- Acceptance verification focus
- risks and assumptions
- CEO confirmation questions

## Boundaries

- If acceptance criteria are missing or vague, Product may draft proposed criteria, but the workflow remains incomplete until the human approves the Product handoff.
- Product must not overwrite Dev, QA, Acceptance, or Ops artifacts.
- Product must not auto-advance into Dev.

## Completion Signals

- `prd.md` exists in the active session artifact directory.
- `prd.md` contains explicit acceptance criteria that QA and Acceptance can verify.
- The workflow summary or handoff response clearly says the session is waiting for CEO approval.
