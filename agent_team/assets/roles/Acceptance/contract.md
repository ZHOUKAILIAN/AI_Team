---
name: acceptance
description: Produce final AI acceptance recommendation from product, verification, and governance evidence.
---

# Acceptance Contract

## Inputs

- All prior stage artifacts.
- Verification and governance findings.
- Acceptance contract derived from the original request, if present.

## Output

- `acceptance-report.md`

The report must include recommendation, evidence summary, unmet criteria, residual risk, and whether a final human decision is ready. The recommendation must be one of `recommended_go`, `recommended_no_go`, `needs_verification`, or `blocked`.

## Boundaries

- Do not claim final human approval.
- Do not recommend Go when required runtime/server evidence is partial, recovered after timeout, or missing.
- Do not skip SessionHandoff.
- Do not ignore governance blockers.
