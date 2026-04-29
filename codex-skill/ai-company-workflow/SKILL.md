---
name: ai-company-workflow
description: Use when the user wants a requirement executed through the AI_Team single-session state machine, especially with /company-run, 执行这个需求：, or equivalent workflow triggers.
---

# AI_Team CLI Runtime Workflow

## Goal

Run a user requirement through the AI_Team multi-role workflow while preserving stage ownership, artifact handoff, and human approval boundaries.

The authoritative state model is:

`Intake -> ProductDraft -> WaitForCEOApproval -> Dev -> QA -> Acceptance -> WaitForHumanDecision`

Product writes the PRD, Dev implements, QA independently verifies, Acceptance recommends, and the human decides.

## When To Use

- `/company-run <requirement>`
- `执行这个需求：<需求内容>`
- `按 AI Company 流程跑这个需求：<需求内容>`
- `按 AI Company 流程执行：<需求内容>`
- `Run this requirement through the AI Company workflow: <requirement>`
- `Execute this requirement: <requirement>`

Use this skill when the active workspace contains the AI_Team runtime or the installed skill has access to a vendored AI_Team runtime. If no runtime is available, state that the workflow cannot run and point the user to the repository installation instructions.

## Workflow Isolation Contract

- AI_Team is the stage controller for the active session.
- Generic methodology skills may assist inside a stage.
- Generic methodology skills must not change the AI_Team stage order, skip CEO approval, replace QA with Dev self-verification, replace Acceptance with code review, or add a mandatory planning gate after an approved PRD already exists.
- Role-specific skills define stage goals, required artifacts, boundaries, and completion signals.
- The workflow stops at `WaitForCEOApproval` after Product and at `WaitForHumanDecision` after Acceptance until the human gives the next decision.

## Available assets

- `scripts/company-run.sh`: skill-bundled bootstrap helper; the helper script only bootstraps a session and does not complete QA or Acceptance by itself.
- project runtime helpers: optional workspace-local setup and session bootstrap helpers when the current workspace is the AI_Team runtime repository.
- runtime CLI: exposes `ai-team dev` for human terminal workflows, plus session bootstrap, state lookup, stage contract generation, stage result submission, and feedback recording.
- generated local agents: optional Product, Dev, QA, and Acceptance agents for project-scoped execution.
- generated local run skill: optional `ai-team-run` entrypoint for project-root workflow runs.

Read available helper assets before choosing the bootstrap path. Prefer `run-requirement` so the runtime acquires, executes, submits, verifies, and advances stages instead of relying on conversational follow-through. A passed stage must have a complete runtime trace.

## Terminal Usage

For human-operated terminal workflows, prefer `ai-team dev`. It prompts for the requirement, confirms acceptance criteria, asks for technical plan confirmation, then can delegate Product / Dev / QA / Acceptance execution through `codex exec` while preserving runtime gates.

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
- Actionable QA, Acceptance, or human feedback route back to Product or Dev before the workflow is treated as complete.

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
- Memory retrieval is keyword-first: use CLI search over raw/extracted/graph memory and include relevant hits in the stage contract; reserve graph/AI reasoning for weak implicit relationships.
- deterministic runtime output is workflow metadata only, not real QA/Acceptance evidence.

## Completion Signals

- Product handoff is complete when `prd.md` exists in the session artifact directory and the workflow summary shows `WaitForCEOApproval`.
- Dev handoff is complete when `implementation.md` contains change summary, changed files, self-verification evidence, commands executed, command result summary, known limitations, QA regression checklist, and rework mapping when applicable.
- QA handoff is complete when `qa_report.md` maps PRD criteria to independently rerun evidence and records `passed`, `failed`, or `blocked`.
- Acceptance handoff is complete when `acceptance_report.md` records `recommended_go`, `recommended_no_go`, or `blocked`, and any declared review contract is satisfied or explicitly blocked.
- The AI_Team workflow is not done until the human records the Go/No-Go decision.

## Continue after runtime driver bootstrap:

- use `ai-team run-requirement --session-id <id>` to continue an existing session after human approval
- inspect and implement in the real repository through the active stage executor
- execute real verification against the runnable path when feasible
- collect concrete evidence for QA and Acceptance decisions through stage-result evidence
- route actionable QA, Acceptance, or human feedback into structured findings for the correct owner
- if evidence is missing, report blocked instead of accepted
