---
name: verification
description: Independently verify implementation and produce a verification report.
---

# Verification Contract

## Inputs

- `technical-design.md`
- `implementation.md`
- Upstream L1/L3 deltas and current repository checks.

## Output

- `verification-report.md`

The report must include commands run, observed results, evidence paths or summaries, findings, target stages, and residual risk.

For partial or blocked runtime evidence, keep the stage machine state explicit:

- Use `verification_conclusion: needs_verification` when evidence is incomplete but the implementation is not proven wrong.
- Use `release_recommendation: needs_verification` when Acceptance must not recommend Go yet.
- Include report sections for `verified`, `not_verified`, `blocked_by`, `risk_if_release`, and `next_evidence_needed`.
- For `backend_api_db`, audit API response, DB precondition, fixture precondition, private config summary, and any routed risks such as logs, idempotency, consistency, permission, concurrency, or side effects.

## Boundaries

- Do not edit implementation files.
- Do not accept Implementation self-verification as independent evidence.
- Do not mark unresolved findings as passed.
