---
name: build-e2e
version: 1.0.0
description: |
  The end-to-end autonomous orchestrator for AI_Company. Use this when the user invokes /build-e2e
  or gives an agent-friendly natural-language trigger such as "执行这个需求：..." or
  "Run this requirement through the AI Company workflow: ...".
---
# /build-e2e Capability And agent-friendly Mode

When the `/build-e2e` command is invoked, or the user gives an agent-friendly trigger, you are initiating the **End-to-End Autonomous Execution Mode**.

## agent-friendly Triggers

Treat the following as direct workflow execution requests:
- `/company-run <requirement>`
- `执行这个需求：<需求内容>`
- `按 AI Company 流程跑这个需求：<需求内容>`
- `按 AI Company 流程执行：<需求内容>`
- `Run this requirement through the AI Company workflow: <requirement>`
- `Execute this requirement: <requirement>`

For agent-friendly requests, do not ask the user to reformat the request into a CLI command. Extract the requirement and run:

```bash
python3 -m ai_company agent-run --message "<the user's original message>" --print-review
```

Then summarize:
- the generated `session_id`
- the `acceptance_status`
- the `review.md` path
- any downstream findings and learned memory updates

## Procedure:
You will sequentially act out the roles of Product -> Dev -> QA -> Ops -> Acceptance without stopping for user input between stages (unless explicitly blocked/failed).

1. **Step 1: Product Stage**
   - Read `Product/context.md`.
   - Ask the user to clarify the feature request.
   - Write the PRD to `.ai_company_state/artifacts/prd.md` and *immediately proceed*.

2. **Step 2: Dev Stage**
   - Read `Dev/context.md`.
   - Build the feature based strictly on `.ai_company_state/artifacts/prd.md`.
   - Output summary to `.ai_company_state/artifacts/dev_notes.md` and *immediately proceed*.

3. **Step 3: QA Stage**
   - Read `QA/context.md`.
   - **Ask the user which platforms to verify (A: Mini Program, B: Web, C: Both) and temporarily pause for their response.**
   - Test the feature on the selected platforms. Use `gstack browse` or CLI tests. If it fails, fix the code (revert briefly to Dev role mindset) until it passes.
   - Write `.ai_company_state/artifacts/qa_report.md` and *immediately proceed*.

4. **Step 4: Ops Stage**
   - Read `Ops/context.md`.
   - Generate `.ai_company_state/artifacts/release_notes.md` based on what was shipped.
   - *Immediately proceed*.

5. **Step 5: Acceptance Stage (Final User Check)**
   - Read `Acceptance/context.md`.
   - Summarize the entire journey, show the Release Notes, and confirm testing passed securely on the selected platforms.
   - **STOP** and ask the human CEO for the final Go/No-Go acceptance.

> [!WARNING]
> If at any point during Steps 1-4 you are critically blocked (e.g., missing an API key, uncertain about a highly ambiguous architectural choice that cannot be guessed), you MUST temporarily break the autonomous flow, alert the user with `STATUS: BLOCKED`, and ask for guidance.
