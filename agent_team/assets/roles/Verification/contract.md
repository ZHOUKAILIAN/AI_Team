---
name: verification
description: Independently verify implementation with the required evidence depth and produce a verification report.
---

# Verification Contract

## Inputs

- `technical-design.md`
- `implementation.md`
- Upstream L1/L3 deltas and current repository checks.
- Route packet fields such as `verification_mode`, `service_profile`, required stages, red lines, and unresolved questions when present.
- Project verification recipes, test fixtures, service profiles, private runtime config, and stage skills when available.

## Output

- `verification-report.md`

The report must include commands run, observed results, evidence paths or summaries, findings, target stages, residual risk, and a clear `passed / partial / failed / blocked` conclusion.

## Verification Depth

Verification is not limited to unit tests.

Use the narrowest evidence depth that can honestly prove the change, but do not accept unit tests as sufficient when the request affects runtime behavior.

### Unit/static verification is sufficient only when

- The change is documentation-only, formatting-only, or pure static configuration with no runtime behavior change.
- The change is fully covered by deterministic unit tests and has no API, persistence, async, cache, permission, state-machine, integration, or external contract effect.
- The route packet or verification report explicitly records why runtime verification is not applicable.

### Runtime/server E2E verification is required when the change affects

- API/RPC/CLI behavior or request/response contracts.
- Database writes, reads, migrations, persisted state, search indexes, files, or generated artifacts.
- Queues, workers, outbox, webhooks, cache invalidation, scheduled jobs, notifications, or other side effects.
- Auth, permissions, ownership, tenant isolation, public/private data exposure, or secret handling.
- Idempotency, retry, duplicate callback/submit, consistency invariants, counters, balances, inventory, rewards, coupons, or limited resources.
- Concurrency, race conditions, locking, transactions, rollback, state transitions, or terminal states.

When runtime/server E2E is required, Verification must execute declared API/RPC/CLI flows or a project-approved equivalent and collect independent evidence. Implementation self-checks can be cited as background but cannot satisfy this contract.

## Required Evidence

For each applicable verification item, collect evidence from the authoritative layer:

1. command/test/API call executed, including working directory and relevant non-secret environment/profile
2. request and response summary or output
3. persisted-state evidence such as database/query/cache/file/outbox/search-index result when applicable
4. log/trace/audit evidence when applicable
5. side-effect evidence for queue, worker, webhook, email, notification, generated artifact, or scheduled job when applicable
6. idempotency, consistency, concurrency, permission, state-machine, or async evidence when applicable
7. cleanup result or reason cleanup was not needed

Do not print raw secrets, cookies, authorization headers, database passwords, private tokens, or private transcripts. If private runtime data is needed, use the project’s L5/private configuration mechanism and report only redacted evidence.

## Blockers

Return `blocked` instead of pretending to pass when:

- Required private runtime config, service profile, credentials, database access, or test data is missing.
- The service cannot be started or a required healthcheck cannot be observed.
- The project has no safe way to prepare required test data.
- Runtime verification is required but only unit/static evidence is available.
- Evidence cannot be collected independently from Implementation.

## Boundaries

- Do not edit implementation files.
- Do not accept Implementation self-verification as independent evidence.
- Do not mark unresolved findings as passed.
- Do not write directly to production data.
- Prefer read-only database checks. If test data mutation is required, use declared API flows or project-approved test fixtures, not ad-hoc database edits.
- Do not downgrade runtime/server E2E to unit-only verification without recording the reason and residual risk.
