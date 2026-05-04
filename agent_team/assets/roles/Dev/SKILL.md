---
name: dev
version: 1.0.0
description: Use when Agent Team is executing or reworking the Dev stage for the active workflow session.
---

# Dev Capability

## Goal

Implement the approved Product and TechPlan handoffs or close returned findings, then produce a Dev handoff that QA can independently verify.

## Required Inputs

- `session_id`
- `artifact_dir`
- `workflow_summary.md`
- the approved `prd.md`
- the approved `technical_plan.md`
- the latest QA, Acceptance, or human-feedback findings when this is a rework round

If this is a QA rework round, read the latest `qa_report.md` first. If this is an Acceptance or human-feedback rework round, read the returned finding payload first and map each issue to a concrete Product-facing fix.

## Allowed Methodology

- Use rigorous engineering discipline inside Dev.
- Generic methodology skills are allowed inside Dev when they help implementation, self-review, debugging, testing, or self-verification.
- Generic methodology skills must not replace QA, must not replace Acceptance, and must not change the Agent Team stage order or approval gates.
- Review your own changed code after implementation and before final self-verification.
- Treat self-verification as Dev evidence, not as a replacement for QA.

## Required Output

Dev produces `implementation.md`; the workflow runner persists it in the active session artifact directory.

The handoff must include:
- implementation target
- change summary
- changed files
- self code review notes
- self-verification evidence
- commands executed
- command result summary
- known limitations
- QA regression checklist
- QA finding to fix mapping when this is a QA rework round
- user-visible closure evidence for every Acceptance or human-feedback issue

## Boundaries

- Write the actual repository changes needed for the current Dev task.
- Keep changes traceable to the active session.
- Return control to QA through the workflow runner instead of asking the user whether QA should start.

## Completion Signals

- Repository changes or an explicit no-code explanation match the current Dev scope.
- `implementation.md` exists in the active session artifact directory.
- `implementation.md` contains self code review notes covering reviewed files, issues fixed, and residual risks.
- `implementation.md` contains self-verification evidence, commands executed, command result summary, and a QA regression checklist.
- Every QA, Acceptance, or human-feedback issue for this round is mapped to a concrete fix and closure signal in the Dev handoff.
