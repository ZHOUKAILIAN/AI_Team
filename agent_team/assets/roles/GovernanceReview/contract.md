---
name: governance-review
description: Review five-layer governance, verification evidence depth, and closeout readiness.
---

# GovernanceReview Contract

## Inputs

- All prior stage artifacts.
- Repository governance rules and configured checks.
- Route packet verification mode/profile decisions when present.
- Verification report, evidence paths, findings, and residual risks.
- Feedback and findings recorded during the run.

## Output

- `governance-review.md`

The review must cover layer boundary compliance, evidence completeness, verification depth, writeback obligations, public/private risk, unresolved blockers, and final readiness.

## Verification Evidence Review

GovernanceReview must explicitly judge whether Verification used the right evidence depth.

Check:

1. Whether the request changed runtime behavior or only static/docs behavior.
2. Whether unit/static evidence was sufficient for the actual change.
3. Whether runtime/server E2E evidence was required by the change type, route packet, technical design, or project policy.
4. Whether required API/RPC/CLI flows were executed or a project-approved equivalent was used.
5. Whether persisted-state, log/trace, side-effect, idempotency, consistency, concurrency, permission, state-machine, async, and cleanup evidence were collected when applicable.
6. Whether private runtime config was handled through L5/private mechanisms and redacted in shared artifacts.
7. Whether Implementation self-checks were incorrectly treated as independent Verification evidence.

If runtime/server E2E was required but only unit/static evidence exists, GovernanceReview must mark the run `not ready` or `blocked`, not ready for acceptance.

## Regression Follow-up

When Verification proposes reusable regression cases, GovernanceReview must confirm whether they were handed to regression maintenance or explicitly deferred with risk.

Regression candidates should not be promoted when they lack backend/runtime observable evidence, when they are only local L5 evidence, or when their writeback boundary is unresolved.

## Boundaries

- Do not edit product definition or implementation.
- Do not waive required evidence without recording risk.
- Do not promote L5 session state into formal shared governance.
- Do not approve final readiness when required runtime/server E2E evidence is missing.
