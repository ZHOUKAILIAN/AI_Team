---
name: build-e2e
version: 1.0.0
description: |
  The end-to-end single-session orchestrator for AI_Company. Use this when the user invokes /build-e2e
  or gives an agent-friendly trigger such as "执行这个需求：..." or
  "Run this requirement through the AI Company workflow: ...".
---
# /build-e2e Capability And Agent-Friendly Mode

When `/build-e2e` is invoked, or the user gives an agent-friendly trigger, run the single-session workflow bootstrap.

## Agent-Friendly Triggers

Treat the following as direct workflow execution requests:
- `/company-run <requirement>`
- `执行这个需求：<需求内容>`
- `按 AI Company 流程跑这个需求：<需求内容>`
- `按 AI Company 流程执行：<需求内容>`
- `Run this requirement through the AI Company workflow: <requirement>`
- `Execute this requirement: <requirement>`

For agent-friendly requests, do not ask the user to reformat into CLI syntax. Keep the original message and run:

```bash
python3 -m ai_company start-session --message "<the user's original message>"
```

deterministic runtime output is workflow metadata only, not real QA/Acceptance evidence.

## Single-Session State Machine

The real workflow state machine is:
`Intake` -> `ProductDraft` -> `WaitForCEOApproval` -> `Dev` -> `QA` -> `Acceptance` -> `WaitForHumanDecision`

## Artifact Contract (Required)

Every session must maintain this contract under `.ai_company_state/artifacts/`:
- `prd.md`
- `implementation.md`
- `qa_report.md`
- `acceptance_report.md`
- `workflow_summary.md`

## Role Requirements

- QA must independently rerun verification, missing evidence forces blocked.
- Acceptance recommends while the human decides.
- Deterministic local runtime output cannot replace repository-level QA or product-level Acceptance evidence.

## If The Request Targets This Workspace

Continue after session bootstrap:
- inspect and implement in the real repository
- execute real verification against the runnable path when feasible
- collect concrete evidence for QA and Acceptance decisions
- if evidence is missing, report blocked instead of accepted
