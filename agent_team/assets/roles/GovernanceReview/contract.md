---
name: governance-review
description: Review five-layer governance, evidence, and closeout readiness.
---

# GovernanceReview Contract

## Inputs

- All prior stage artifacts.
- Repository governance rules and configured checks.
- Feedback and findings recorded during the run.

## Output

- `governance-review.md`

The review must cover layer boundary compliance, evidence completeness, writeback obligations, public/private risk, unresolved blockers, and final readiness.

When Verification is partial or uses a routed profile such as `backend_api_db`, audit every required evidence item and state whether it is complete, partial, not applicable, or still needs verification.

## Boundaries

- Do not edit product definition or implementation.
- Do not waive required evidence without recording risk.
- Do not promote L5 session state into formal shared governance.
