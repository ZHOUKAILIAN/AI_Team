---
name: acceptance
description: Produce final AI acceptance recommendation from product, verification-depth, and governance evidence.
---

# Acceptance Contract

## Inputs

- All prior stage artifacts.
- Verification report and evidence summary.
- GovernanceReview readiness judgment.
- Acceptance contract derived from the original request, if present.

## Output

- `acceptance-report.md`

The report must include recommendation, evidence summary, unmet criteria, residual risk, verification-depth adequacy, and whether a final human decision is ready.

## Verification-Depth Gate

Acceptance must not make human review look easier than the evidence supports.

Before recommending Go/No-Go, check:

1. Whether Verification produced independent evidence rather than relying on Implementation self-checks.
2. Whether unit/static-only verification was justified for the change type.
3. Whether runtime/server E2E evidence was collected when the change affected API behavior, persistence, async work, side effects, permissions, idempotency, consistency, concurrency, state machines, or external contracts.
4. Whether GovernanceReview agreed that the verification depth was sufficient.
5. Whether blockers, missing private config, missing service profile, or missing test data remain.
6. Whether residual risks are small enough for human acceptance to be lightweight.

If required runtime/server E2E evidence is missing, recommend `No-Go` or `Needs verification`, not `Go`.

## Boundaries

- Do not claim final human approval.
- Do not skip SessionHandoff.
- Do not ignore governance blockers.
- Do not hide missing verification depth behind a positive recommendation.
