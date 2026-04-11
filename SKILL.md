---
name: ai-company-workflow
version: 1.0.0
description: |
  The end-to-end single-session orchestrator for AI_Company. Use this when the user invokes /company-run
  or gives an agent-friendly trigger such as "执行这个需求：..." or
  "Run this requirement through the AI Company workflow: ...".
---

## Skill Dispatch Protocol

> Applies to the orchestrator and all role agents at every stage.

**Core rule: before executing any stage, identify and load the matching role skill.**

1. **On task received**: check for a matching skill (Product / Dev / QA / Acceptance / Ops). Load it first, then execute.
2. **1% rule**: if there is even a 1% chance a skill applies, invoke it. No exceptions.
3. **Priority**: explicit user instructions > skill rules > default behavior.
4. **Red flags** — these thoughts mean stop and check:
   - "This stage is simple, no skill needed"
   - "I already know this skill"
   - "Let me just do it first"
5. **Invocation order**: orchestration skills (dispatch, review) before execution skills (Product, Dev, QA).

### State Machine

```
Intake -> ProductDraft -> WaitForCEOApproval -> Dev <-> QA -> Acceptance -> WaitForHumanDecision -> Done
```

---

# /ai-company-workflow Agent-Friendly Mode

When `/company-run` is invoked, or the user gives an agent-friendly trigger, run the single-session workflow bootstrap.

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

## State Machine

The workflow state machine:
`Intake` -> `ProductDraft` -> `WaitForCEOApproval` -> `Dev` -> `QA` -> `Acceptance` -> `WaitForHumanDecision`

## Project-Scoped Codex Setup

This repository supports optional project-local Codex helpers generated on demand:
- agents: `.codex/agents/*.toml`
- run skill: `.agents/skills/ai-team-run/SKILL.md`

Generate them once per clone with:

```bash
./scripts/company-init.sh
```

Use `./scripts/company-run.sh` as the project-local shell fallback after initialization.

These hidden files are gitignored and should not be committed.

## Artifact Contract (Required)

Every session must maintain this contract under `.ai_company_state/artifacts/<session_id>/`:

| Artifact | Description |
|----------|-------------|
| `prd.md` | Product requirements with acceptance criteria |
| `implementation.md` | Dev handoff with self-verification evidence |
| `qa_report.md` | QA findings with independently rerun verification |
| `acceptance_report.md` | Acceptance recommendation for CEO |
| `workflow_summary.md` | Session index and current state |
| `acceptance_contract.json` | Machine-readable acceptance/review contract captured from intake |
| `review_completion.json` | Required for review-driven flows; declares whether every required artifact, evidence item, and criterion is covered |

## Role Requirements

- **Product**: write explicit acceptance criteria before Dev starts
- **Dev**: document self-verification, not a replacement for QA
- **QA**: independently rerun verification, missing evidence forces blocked
- QA must independently rerun verification.
- **Acceptance**: product-level validation, recommends while human decides
- Acceptance recommends while the human decides.
- **Acceptance and QA findings**: route actionable rework back to Product or Dev with a reusable lesson and explicit completion-signal language
- Deterministic local runtime output cannot replace real QA or Acceptance evidence
- deterministic runtime output is workflow metadata only, not real QA/Acceptance evidence

## Feedback Learning

- If `QA` fails or blocks with actionable defects, the workflow must return those findings to `Dev`.
- If `Acceptance` recommends `recommended_no_go` or an actionable `blocked`, convert that outcome into structured findings that target `Product` or `Dev`.
- Human feedback can be normalized into the same learning loop with `python3 -m ai_company record-feedback ...`.
- Learning overlays in `.ai_company_state/memory/<Role>/` must store reusable lessons, portable constraints, and explicit completion signals.
- Review-driven workflows must persist `acceptance_contract.json` at intake and keep `review_completion.json` current until the review is explicitly complete.
- For page-root visual parity or `<= 0.5px` Figma reviews, the required evidence set is `runtime_screenshot`, `overlay_diff`, and `page_root_recursive_audit`.
- The native-node policy excludes host-owned nodes such as `wechat_native_capsule` from business diffs; verify safe-area avoidance instead of asking Dev to recreate them.
- Host-tool or local-environment changes are denied by default. Require explicit user approval before restarting external tools or mutating local configuration.

## If The Request Targets This Workspace

Continue after session bootstrap:
- inspect and implement in the real repository
- execute real verification against the runnable path when feasible
- collect concrete evidence for QA and Acceptance decisions
- route actionable QA, Acceptance, and human-feedback findings back to the correct role before declaring the workflow done
- if evidence is missing, report blocked instead of accepted
