---
name: acceptance
version: 1.0.0
description: Use when AI_Team is producing the final AI acceptance recommendation for the active workflow session.
---

# Acceptance Capability

## Goal

Validate the user-visible product outcome against the PRD and produce the final AI recommendation for the human Go/No-Go decision.

Acceptance owns product-level validation. Acceptance is not a repeat of QA and is not the final approver.

## Required Inputs

- `session_id`
- `artifact_dir`
- `workflow_summary.md`
- the active session `prd.md`
- the latest `qa_report.md`
- `implementation.md` as supporting context only
- `acceptance_contract.json` when present
- `review_completion.json` for review-driven sessions

Read `prd.md` to establish the business goal, `qa_report.md` to confirm what QA independently reran, and `implementation.md` only as supporting context for the final user-visible behavior.

## Verification Scope

- If the user already specified the verification platform, treat that as the platform choice instead of asking again.
- Phrases such as `Mini Program`, `小程序`, or `miniprogram` mean Mini Program verification.
- Phrases such as `Web`, `网页`, or `browser-use` mean Web verification.
- If the platform is not already specified, ask the user which platforms to verify and offer Mini Program, Web, or Both.
- Use `miniprogram` for Mini Program flows and `browser-use` for Web flows when those surfaces are part of the acceptance scope.
- If the product-level surface cannot be exercised because credentials, environments, or external systems are unavailable, the recommendation is `blocked`.
- Consult the runtime native-node policy before filing business-side visual defects. Platform-hosted nodes such as `wechat_native_capsule` are excluded from business diffs and should be checked for safe-area avoidance and surrounding alignment.

## Required Output

Acceptance writes `acceptance_report.md` in the active session artifact directory.

The report must cover:
- acceptance inputs
- criterion-by-criterion judgment
- product-level observations
- remaining risks
- recommendation: `recommended_go`, `recommended_no_go`, or `blocked`
- recommendation to CEO

## Boundaries

- Judge user-visible behavior, not implementation detail.
- Do not restart external tools, edit host-app configuration, or mutate the local environment unless the workflow contract or the user has given explicit user approval in the current session.
- For page-root visual parity or Figma tolerance work, do not recommend `recommended_go` without `runtime_screenshot`, `overlay_diff`, and `page_root_recursive_audit`.
- For review-driven sessions, do not recommend `recommended_go` while `review_completion.json` remains incomplete, unresolved, or does not cover the declared acceptance contract.
- If the recommendation is `recommended_no_go` or an actionable `blocked`, emit structured findings with reusable lessons and explicit completion-signal language that route the work back to Product or Dev.
- Acceptance returns an AI recommendation only and then waits for the human Go/No-Go decision.

## Completion Signals

- `acceptance_report.md` exists in the active session artifact directory.
- The report explicitly records `recommended_go`, `recommended_no_go`, or `blocked`.
- Product-level observations are tied to the PRD and the exercised user-facing surface.
- Review-driven sessions cover `review_completion.json`, required evidence, and unresolved items before `recommended_go`.
- Any returned Acceptance finding includes structured findings, required evidence, and completion-signal language.
