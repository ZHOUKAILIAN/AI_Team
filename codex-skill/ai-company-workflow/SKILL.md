---
name: ai-company-workflow
description: Use when the user wants a requirement executed through the AI Company Product -> Dev -> QA -> Acceptance loop, especially with triggers like /company-run, 执行这个需求：..., or Run this requirement through the AI Company workflow: ...
---

# AI Company Workflow

Use this skill only when the current workspace contains the AI Company runtime:
- `ai_company/cli.py`
- `Product/`
- `Dev/`
- `QA/`
- `Acceptance/`

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
2. Run the runtime from the repository root:

```bash
python3 -m ai_company agent-run --message "<the user's original message>" --print-review
```

3. Summarize:
- `session_id`
- `acceptance_status`
- `review.md` path
- downstream findings
- learned memory/context/skill updates, if any

## If The Runtime Is Missing

Do not pretend the workflow ran. State that the current workspace does not contain the AI Company runtime and point the user to install or open the repository that includes:
- `ai_company/`
- role folders such as `Product/` and `Dev/`
