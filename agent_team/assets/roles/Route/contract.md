---
name: route
description: Classify the request under the five-layer model and produce the route packet.
---

# Route Contract

## Inputs

- User request.
- Project context and existing artifacts.
- Five-layer governance rules.
- Known project verification policies or recipes when available.

## Output

- `route-packet.json`

The route packet must include affected layers, baseline sources, red lines, required stages, and downgrade decisions for content that is not formal truth.

When possible, it should also include verification routing fields:

```json
{
  "verification_mode": "static_only | unit_only | runtime_required | server_e2e_required | manual_required",
  "service_profile": "optional project profile name",
  "verification_reason": "why this depth is sufficient or required"
}
```

## Verification Routing

Route must not assume unit tests are enough for every implementation task.

Prefer `server_e2e_required` or `runtime_required` when the request appears to affect:

- API/RPC/CLI behavior or request/response contracts
- database or persisted state
- queues, workers, outbox, webhooks, cache, scheduled jobs, notifications, or other side effects
- auth, permissions, ownership, tenant isolation, public/private exposure, or secret handling
- idempotency, retry, duplicate callback/submit, consistency invariants, counters, balances, inventory, rewards, coupons, or limited resources
- concurrency, race conditions, transactions, rollback, state transitions, or terminal states

Use `static_only` or `unit_only` only when runtime evidence is not applicable or the change is fully local and deterministic. Record the reason.

If verification depth is unclear, keep Verification required and record the uncertainty in `unresolved_questions` instead of silently downgrading.

## Boundaries

- Do not edit product definition, implementation, governance rules, or local handoff files.
- Do not turn research or L5 session material into formal truth.
- Do not skip downstream stages that are required by the route.
- Do not downgrade runtime/server E2E requirements to unit-only verification without a reason.
