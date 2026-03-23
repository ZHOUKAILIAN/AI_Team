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

Treat the returned workflow `acceptance_status` as workflow metadata only. The default local runtime uses a deterministic backend, so its QA and Acceptance outputs do not count as real repository verification.

If the request targets code in the current workspace, continue after the workflow run instead of stopping:
- create an isolated branch/worktree before editing when the current worktree is dirty or the user explicitly asked for a new branch
- inspect the actual repository, implement the requirement, and verify the real code path
- run real QA as technical verification:
  - for server-side changes, start the relevant service(s) when feasible and verify the requirement through the real request path or full end-to-end chain
  - if the user already specified the verification platform, treat that as the platform choice instead of asking again; phrases such as `Mini Program`, `小程序`, or `miniprogram` mean Mini Program verification, and phrases such as `Web`, `网页`, or `browser-use` mean Web verification
  - for frontend changes, use `miniprogram` for Mini Program flows and `browser-use` for Web flows
  - treat tests and suites as supporting evidence, not the entire verification story when a runnable surface exists
- run real Acceptance as product-level validation:
  - ignore implementation details and judge only the product behavior
  - if the user already specified the verification platform, do not ask again; carry that platform choice into Acceptance
  - operate the final user-facing surface with `miniprogram` for Mini Program flows and `browser-use` for Web flows
  - compare the result against the original pain point, user scenario, and expected user-visible behavior
- if product-level evidence is blocked by missing credentials, external systems, or unavailable platforms, report the block and do not claim real acceptance

Then summarize:
- the generated `session_id`
- the workflow `acceptance_status`
- the `review.md` path
- any downstream findings and learned memory updates
- the real QA commands and results
- the real product-level Acceptance decision and any remaining gaps

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
   - If the user has not already specified the verification platform, **ask which platforms to verify (A: Mini Program, B: Web, C: Both) and temporarily pause for their response.**
   - If the user already specified `Mini Program`, `小程序`, or `miniprogram`, treat that as selecting Mini Program verification and use `miniprogram`.
   - If the user already specified `Web`, `网页`, or `browser-use`, treat that as selecting Web verification and use `browser-use`.
   - Test the feature on the selected platforms. Use `miniprogram` for Mini Program flows, `browser-use` for Web flows, and CLI tests as supporting evidence. If it fails, fix the code (revert briefly to Dev role mindset) until it passes.
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
