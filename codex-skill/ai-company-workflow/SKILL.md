---
name: ai-company-workflow
description: "Use when the user wants a requirement executed through the AI Company single-session state machine, especially with triggers like /company-run, 执行这个需求：..., or Run this requirement through the AI Company workflow: ..."
---

# AI Company Workflow

Use this skill when either of these is true:
- the current workspace contains the AI Company runtime
- the runtime was globally installed under `~/.codex/vendor/ai-team`

If the current workspace is this repository itself, prefer the project-local setup first:

```bash
./scripts/company-init.sh
./scripts/company-run.sh "<the user's original message>"
```

`company-init.sh` generates the project-local `.codex/` and `.agents/` helpers on demand and keeps them out of git.

## Trigger Phrases

Treat these as direct workflow execution requests:
- `/company-run <requirement>`
- `执行这个需求：<需求内容>`
- `按 AI Company 流程跑这个需求：<需求内容>`
- `按 AI Company 流程执行：<需求内容>`
- `Run this requirement through the AI Company workflow: <requirement>`
- `Execute this requirement: <requirement>`

## Execution

1. Keep the user's original message intact.
2. Prefer the installed helper script:

```bash
~/.codex/skills/ai-company-workflow/scripts/company-run.sh "<the user's original message>"
```

The helper script only bootstraps a session. It does not complete QA or Acceptance by itself.

3. Direct bootstrap command:

```bash
python3 -m ai_company start-session --message "<the user's original message>"
```

After bootstrap, continue the state machine in the current Codex session to produce the full artifact contract.

4. Follow the single-session state machine:
   `Intake` -> `ProductDraft` -> `WaitForCEOApproval` -> `Dev` -> `QA` -> `Acceptance` -> `WaitForHumanDecision`

5. Enforce artifact contract in `.ai_company_state/artifacts/<session_id>/`:

| Artifact | Description |
|----------|-------------|
| `prd.md` | Product requirements with acceptance criteria |
| `implementation.md` | Dev handoff with self-verification evidence |
| `qa_report.md` | QA findings with independently rerun verification |
| `acceptance_report.md` | Acceptance recommendation for CEO |
| `workflow_summary.md` | Session index and current state |
| `acceptance_contract.json` | Machine-readable acceptance/review contract captured from intake |
| `review_completion.json` | Required for review-driven flows; records whether the review is truly complete |

6. QA must independently rerun verification, missing evidence forces blocked.
7. Acceptance recommends while the human decides.
8. If QA, Acceptance, or a human feedback record identifies actionable rework, route it back to Product or Dev before treating the workflow as complete.

## Evidence Rules

**QA** must independently rerun critical verification — Dev's self-verification is not sufficient proof.

**Acceptance** must validate product-level outcomes against the PRD — technical inference is not a substitute.

**Missing evidence = blocked** — no "soft pass" or "provisional accepted".

**Learning overlays** must capture one reusable lesson plus explicit completion signals for the next run.

Review-driven workflows must persist `acceptance_contract.json` at intake and keep `review_completion.json` current until the review is explicitly complete.

For page-root visual parity or `<= 0.5px` Figma reviews, require `runtime_screenshot`, `overlay_diff`, and `page_root_recursive_audit` evidence before Acceptance can recommend go.

The native-node policy excludes host-owned nodes such as `wechat_native_capsule` from business diffs; verify safe-area avoidance instead of recreating them in product code.

Host-tool or local-environment changes are denied by default. Require explicit user approval before restarting external tools or mutating local configuration.

deterministic runtime output is workflow metadata only, not real QA/Acceptance evidence.

Human feedback can enter the same loop through `python3 -m ai_company record-feedback ...`.

## If The Request Targets This Workspace

Continue after session bootstrap:
- inspect and implement in the real repository
- execute real verification against the runnable path when feasible
- collect concrete evidence for QA and Acceptance decisions
- route actionable QA, Acceptance, or human feedback into structured findings for the correct owner
- if evidence is missing, report blocked instead of accepted

## If The Runtime Is Missing

Do not pretend the workflow ran. State that neither the current workspace nor `~/.codex/vendor/ai-team` contains the AI Company runtime, and point the user to run:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ZHOUKAILIAN/AI_Team/main/scripts/install-codex-ai-team.sh)
```
