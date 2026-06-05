---
name: route
description: Classify the request under the five-layer model and produce the route packet.
---

# Route Contract

## Inputs

- User request.
- Project context and existing artifacts.
- Five-layer governance rules.

## Output

- `route-packet.json`

The route packet must include affected layers, baseline sources, red lines, required stages, and downgrade decisions for content that is not formal truth.

When Verification needs concrete proof beyond the default independent-verification evidence, include:

- `verification_mode`: use at least `runtime_required` when the requirement changes server/API behavior.
- `verification_profile`: use `backend_api_db` for backend API behavior that needs API response, DB precondition, fixture, private config, logs, idempotency, consistency, permission, concurrency, or side-effect evidence.
- `required_evidence`: evidence names that Verification must later provide.
- `private_config_required`: whether local private configuration is required for verification.
- `fixture_preconditions`: required fixture, data, service, or environment preconditions.
- `verification_reason`: why this evidence/private config/fixture depth is required.

## Boundaries

- Do not edit product definition, implementation, governance rules, or local handoff files.
- Do not turn research or L5 session material into formal truth.
- Do not skip downstream stages that are required by the route.
