---
name: ai-company-workflow
description: "Use when the user wants a requirement executed through the AI Company Product -> Dev -> QA -> Acceptance loop, especially with triggers like /company-run, 执行这个需求：..., or Run this requirement through the AI Company workflow: ..."
---

# AI Company Workflow

Use this skill when either of these is true:
- the current workspace contains the AI Company runtime
- the runtime was globally installed under `~/.codex/vendor/ai-team`

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
2. Prefer the installed helper script for deterministic execution:

```bash
~/.codex/skills/ai-company-workflow/scripts/company-run.sh "<the user's original message>"
```

3. Treat the returned workflow `acceptance_status` as **workflow metadata only**. The default vendor runtime uses a deterministic backend, so its QA and Acceptance artifacts do **not** count as real code/browser/test verification.
4. If the request targets code in the current workspace, continue after the workflow run instead of stopping:
- if the current git worktree is dirty or the user asked for a new branch, create an isolated branch/worktree before editing
- inspect the actual repository, find the root cause, and implement the requirement end-to-end
- run **real QA** as technical verification with concrete evidence:
  - for server-side changes, start the relevant service(s) when feasible and verify the requirement through the real request path or full end-to-end chain, not only unit tests or static inspection
  - for frontend changes, use the platform-appropriate real interaction tool: use `minipro` or an equivalent mini-program automation tool for Mini Program flows, and use Playwright, `browser-use`, or an equivalent real-browser tool for Web flows
  - use targeted tests and relevant suites as supporting evidence, not as the only verification when a real runnable surface exists
- run **real Acceptance** as **product-level acceptance**:
  - do not focus on implementation details
  - operate the product through the final user-facing surface, using `minipro` or an equivalent mini-program automation tool for Mini Program flows, and Playwright, `browser-use`, or an equivalent real-browser tool for Web flows
  - judge only whether the original pain point, user scenario, and expected user-visible behavior are satisfied
- if product-level evidence is missing because credentials, external services, or platforms are unavailable, say so explicitly and mark Acceptance as blocked or provisional instead of accepted
5. Summarize both the workflow output and the real execution evidence:
- `session_id`
- workflow `acceptance_status`
- `review.md` path
- downstream findings
- learned memory/context/skill updates, if any
- real QA commands and results
- real product-level Acceptance decision and any remaining gaps

## If The Runtime Is Missing

Do not pretend the workflow ran. State that neither the current workspace nor `~/.codex/vendor/ai-team` contains the AI Company runtime, and point the user to run:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ZHOUKAILIAN/AI_Team/main/scripts/install-codex-ai-team.sh)
```
