---
name: ai-company-workflow
version: 1.0.0
description: Use when the user wants to run a requirement through the AI_Team single-session workflow, especially with /company-run or equivalent natural-language workflow triggers.
---

# AI_Team Workflow

## Goal

Run one requirement through the AI_Team handoff model without collapsing the work into a single Dev-only execution path.

The authoritative state model is:

`Intake -> ProductDraft -> WaitForCEOApproval -> Dev -> QA -> Acceptance -> WaitForHumanDecision`

Product owns the PRD, Dev owns implementation, QA owns independent verification, Acceptance recommends, and the human decides.

## When To Use

- `/company-run <requirement>`
- `执行这个需求：<需求内容>`
- `按 AI Company 流程跑这个需求：<需求内容>`
- `按 AI Company 流程执行：<需求内容>`
- `Run this requirement through the AI Company workflow: <requirement>`
- `Execute this requirement: <requirement>`

Use this skill only for AI_Team workflow execution. Do not use it for one-off code edits that the user did not ask to run through the multi-role workflow.

## Workflow Isolation Contract

- AI_Team is the stage controller for the active session.
- Generic methodology skills may assist inside a stage.
- Generic methodology skills must not change the AI_Team stage order, skip CEO approval, replace QA with Dev self-verification, replace Acceptance with code review, or add a mandatory planning gate after an approved PRD already exists.
- Role-specific skills define stage goals, required artifacts, boundaries, and completion signals.
- The workflow stops at `WaitForCEOApproval` after Product and at `WaitForHumanDecision` after Acceptance until the human gives the next decision.

## Available assets

- `./scripts/company-init.sh`: project-scoped setup helper for local Codex agents and the local run skill.
- `./scripts/company-run.sh`: session bootstrap helper for this repository.
- `.codex/agents/*.toml`: generated local agents for Product, Dev, QA, and Acceptance.
- `.agents/skills/ai-team-run/SKILL.md`: generated local run skill for project-root execution.
- `ai_company/cli.py`: runtime module that exposes the `ai_company start-session` bootstrap entrypoint.
- `.ai_company_state/artifacts/<session_id>/`: session-scoped handoff artifacts.
- `.ai_company_state/sessions/<session_id>/`: journals, findings, stage metadata, and `review.md`.

The helper scripts bootstrap metadata only. deterministic runtime output is workflow metadata only, not real QA/Acceptance evidence.

## Artifact Contract

Every active session maintains these artifacts under the provided session artifact directory:

| Artifact | Completion Meaning |
|----------|--------------------|
| `prd.md` | Product requirements, user scenarios, and acceptance criteria are ready for CEO review |
| `implementation.md` | Dev handoff records changes, self-verification evidence, commands, results, limitations, and rework mapping |
| `qa_report.md` | QA records independently rerun evidence and a decision of `passed`, `failed`, or `blocked` |
| `acceptance_report.md` | Acceptance records `recommended_go`, `recommended_no_go`, or `blocked` for the human decision |
| `workflow_summary.md` | Current state, current stage, and artifact paths are traceable |
| `acceptance_contract.json` | Machine-readable acceptance/review contract captured from intake when constraints exist |
| `review_completion.json` | Review-driven sessions declare whether required artifacts, dimensions, evidence, and criteria are covered |

## Stage Outcomes

- Product completes only when `prd.md` contains explicit acceptance criteria and the workflow is waiting for CEO approval.
- Dev completes only when `implementation.md` includes self-verification evidence and any QA, Acceptance, or human-feedback rework mapping.
- QA completes only when `qa_report.md` contains independently rerun verification evidence; missing evidence forces blocked.
- Acceptance recommends while the human decides; Acceptance never owns the final Go/No-Go.
- Actionable QA, Acceptance, or human-feedback findings route back to Product or Dev with a reusable lesson and completion-signal language.

## Evidence Rules

- Dev may use implementation methodology and self-verification inside Dev, but Dev evidence must not replace QA evidence.
- QA must independently rerun verification against the runnable path when feasible.
- Acceptance validates user-visible product behavior against the PRD, not implementation intent.
- Missing evidence = blocked.
- Review-driven workflows keep `review_completion.json` current until the review is explicitly complete.
- Page-root visual parity or `<= 0.5px` Figma reviews require `runtime_screenshot`, `overlay_diff`, and `page_root_recursive_audit` before Acceptance can recommend go.
- The native-node policy excludes host-owned nodes such as `wechat_native_capsule` from business diffs; verify safe-area avoidance instead.
- Host-tool or local-environment changes require explicit user approval before QA or Acceptance proceeds.
- Human feedback can enter the same learning loop through `record-feedback`.

## Completion Signals

- Product handoff is complete when `prd.md` exists in the session artifact directory and the workflow summary shows `WaitForCEOApproval`.
- Dev handoff is complete when `implementation.md` contains change summary, changed files, self-verification evidence, commands executed, command result summary, known limitations, QA regression checklist, and rework mapping when applicable.
- QA handoff is complete when `qa_report.md` maps PRD criteria to independently rerun evidence and records `passed`, `failed`, or `blocked`.
- Acceptance handoff is complete when `acceptance_report.md` records `recommended_go`, `recommended_no_go`, or `blocked`, and any declared review contract is satisfied or explicitly blocked.
- The AI_Team workflow is not done until the human records the Go/No-Go decision.

## Continue after session bootstrap:

- inspect and implement in the real repository
- execute real verification against the runnable path when feasible
- collect concrete evidence for QA and Acceptance decisions
- route actionable QA, Acceptance, and human-feedback findings back to the correct role
- if evidence is missing, report blocked instead of accepted
