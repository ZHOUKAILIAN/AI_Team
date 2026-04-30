# Agent Team Enforced Stage Gates Design

Date: 2026-04-17

## Goal

Strengthen Agent Team from a workflow that can control stage order into a runtime that can enforce stage completion. The runtime must own state truth, evidence requirements, and transition eligibility instead of trusting worker claims.

## Summary

The current runtime already has stronger control-plane structure than Ralph-style loops:

- explicit `StageMachine`
- machine-readable `StageContract`
- human wait states
- structured stage-result bundles
- review gates for acceptance-specific workflows

What it lacks is enforcement between "worker submitted a result" and "workflow may advance."

Today, stage ordering is enforced, but stage completion is still too trust-based. A worker can submit a syntactically valid bundle, and the runtime can advance even when required evidence is missing or weak. The missing piece is a mandatory gatekeeper layer plus explicit per-stage run states.

This design adds:

1. a stage-run lifecycle separate from the high-level workflow stage
2. a general gatekeeper that validates outputs and evidence before advancement
3. explicit transition rules that prevent workers from self-certifying completion
4. machine-readable run records and evidence manifests as first-class runtime artifacts

The result should preserve the current Agent Team architecture:

- `agent-team` remains the controller
- Codex remains the executor
- role assets remain prompt material
- human approval remains required where policy already demands it

## Problems In The Current Runtime

### 1. Stage order is enforced, but stage completion is not strongly enforced

`StageMachine.advance()` correctly blocks illegal sequence changes and wait-state bypasses, but it assumes the submitted bundle is already trustworthy enough to advance the workflow.

That means the system currently answers:

- "Is this the right stage?"
- "Is this the right contract?"

But not strongly enough:

- "Did this stage actually produce all required outputs?"
- "Did it attach the evidence required to claim completion?"
- "Did QA independently verify, or just restate Dev's claim?"
- "Did Acceptance cover every requested acceptance criterion?"

### 2. Evidence requirements are present, but too weakly bound to transitions

`StageContract.evidence_requirements` currently carries coarse string labels such as `self_verification` or `independent_verification`. This is useful as intent, but insufficient as a hard transition gate.

The runtime needs structured evidence schemas, not only abstract evidence labels.

### 3. No explicit run-state lifecycle exists inside a stage

The current model jumps directly from:

`current_stage = Dev`

to:

`submit-stage-result -> StageMachine.advance() -> current_stage = QA`

There is no first-class representation for:

- stage acquired
- worker currently running
- result submitted but not yet verified
- gate failed
- stage blocked on missing approval or environment mutation

Without this, the runtime cannot make "not yet verified" a real state.

### 4. Worker submission and runtime verification are still coupled too loosely

A worker bundle is both:

- the candidate output
- the de facto trigger for transition

Those concerns should be separated. Submission should create a candidate result. Only gate success should authorize workflow advancement.

### 5. Concurrency and repeated submissions are under-specified

The current runtime does not define a hard stage-run lock. If multiple executors or repeated submissions target the same stage, the runtime lacks a canonical active run identity that determines which result is valid.

## Design Goals

- Make stage completion runtime-enforced instead of worker-asserted.
- Preserve the existing stage-level workflow and human approval model.
- Add the minimum new state required to make verification explicit and auditable.
- Keep all control-plane facts file-based and machine-readable.
- Avoid redesigning the whole system into a distributed event-sourced platform.

## Non-Goals

- Do not replace human `Go/No-Go` decisions with automation.
- Do not build a fully autonomous multi-agent scheduler in this change.
- Do not redesign role assets or rewrite the existing stage machine from scratch.
- Do not require a background daemon or external database.

## Proposed Model

### 1. Separate Workflow Stage From Stage Run

Keep the existing high-level workflow stage machine:

`Intake -> Product -> WaitForCEOApproval -> Dev -> QA -> Acceptance -> WaitForHumanDecision -> Done`

Add a second, lower-level lifecycle for each executable stage run:

`READY -> RUNNING -> SUBMITTED -> VERIFYING -> PASSED | FAILED | BLOCKED`

Meaning:

- `READY`: the runtime is ready for this stage to be executed
- `RUNNING`: a worker has explicitly acquired the stage run
- `SUBMITTED`: the worker has submitted a candidate result bundle
- `VERIFYING`: the runtime is evaluating gates against the candidate result
- `PASSED`: the candidate result satisfied all required gates
- `FAILED`: the candidate result failed contract or evidence gates
- `BLOCKED`: the stage cannot proceed without external approval or blocker resolution

Only `PASSED` may call `StageMachine.advance()`.

### 2. Introduce A General Gatekeeper

Add a general `Gatekeeper` layer between candidate result submission and workflow advancement.

The gatekeeper should evaluate three categories:

1. `ContractGate`
2. `EvidenceGate`
3. `VerificationGate`

#### ContractGate

Validates:

- current stage matches expected stage
- `contract_id` matches current compiled contract
- required outputs exist
- forbidden actions were not declared or implied
- bundle structure is complete enough to be evaluated

This gate is the structural boundary.

#### EvidenceGate

Validates:

- all required evidence entries exist
- evidence items use supported kinds
- evidence manifests contain the required fields
- stage-specific requirements are satisfied

Examples:

- Dev must include self-verification evidence
- QA must include independent verification evidence
- Acceptance must include coverage of requested acceptance criteria

This gate is the proof boundary.

#### VerificationGate

Validates:

- evidence is not merely declared but sufficient to support the claimed status
- runtime review-completion artifacts are present where required
- environment mutation policies are respected
- optional command or artifact rechecks may run where policy allows

This gate is the confidence boundary.

### 3. Worker Results Become Candidate Results

Workers should no longer be able to submit a bundle that directly advances the workflow.

Instead:

- worker submits a candidate result
- runtime persists it under the active stage run
- runtime evaluates gates
- only if gates pass does the runtime mark the stage run `PASSED`
- then and only then does the workflow summary advance

This preserves executor autonomy while keeping transition authority in the runtime.

### 4. Strengthen Evidence Requirements Into Schemas

The current `evidence_requirements: list[str]` should evolve into structured stage evidence schemas.

Suggested model:

```json
{
  "stage": "Dev",
  "required_evidence": [
    {
      "name": "self_verification",
      "required": true,
      "allowed_kinds": ["command", "artifact", "report"],
      "required_fields": ["summary"],
      "minimum_items": 1
    }
  ]
}
```

This can remain backward-compatible by preserving the high-level string label while compiling it into a richer schema at contract-build time.

### 5. Add First-Class Stage Run Records

Each stage execution attempt should create a `StageRunRecord`.

Suggested fields:

- `run_id`
- `session_id`
- `stage`
- `round_index`
- `contract_id`
- `state`
- `worker`
- `started_at`
- `submitted_at`
- `verified_at`
- `required_outputs`
- `required_evidence`
- `provided_evidence`
- `gate_result`
- `blocked_reason`

This gives the runtime an auditable history of attempts, not only final stage artifacts.

### 6. Add Evidence Records

Evidence should become first-class metadata, not only prose embedded in journals.

Suggested evidence fields:

- `name`
- `kind`
- `summary`
- `artifact_path`
- `command`
- `exit_code`
- `producer`
- `created_at`

Supported kinds can begin with:

- `command`
- `artifact`
- `report`
- `screenshot`
- `diff`
- `review_completion`

### 7. Preserve Existing Human Decision Boundaries

The following current policy remains unchanged:

- Product completion still routes to `WaitForCEOApproval`
- final go/no-go still routes through `record-human-decision`
- Acceptance still cannot replace the final human decision

This design strengthens technical completion gates, not business authority boundaries.

## CLI Changes

### 1. Add `agent-team acquire-stage-run`

Purpose:

- lock the active stage for execution
- create a `StageRunRecord`
- move the stage run from `READY` to `RUNNING`

Output should include:

- `run_id`
- `stage`
- `contract_id`
- `contract_path`

### 2. Change `agent-team submit-stage-result`

Current meaning:

- store bundle
- advance workflow

New meaning:

- store candidate bundle for the active run
- move stage run to `SUBMITTED`
- optionally trigger verification
- do not directly advance workflow unless gates pass

### 3. Add `agent-team verify-stage-result`

Purpose:

- run the gatekeeper against the active stage run
- emit machine-readable gate results
- move run to `PASSED`, `FAILED`, or `BLOCKED`
- if `PASSED`, then call `StageMachine.advance()`

This can later be folded into `submit-stage-result --verify`, but a separate command is clearer during rollout.

### 4. Add `agent-team step`

Purpose:

- tell Codex or an operator exactly what the runtime expects next

Suggested output:

```json
{
  "session_id": "session-001",
  "current_state": "Dev",
  "stage": "Dev",
  "stage_run_state": "READY",
  "action": "acquire_stage_run",
  "requires_human_decision": false,
  "contract_path": "/repo/.agent-team/session-001/contracts/dev.json"
}
```

This command turns runtime state into an explicit next action, which is the biggest practical gap between the current runtime and a stronger harness.

## File Layout Changes

Under `.agent-team/<session_id>/`, add:

```text
contracts/
  product_round_1.json
  dev_round_1.json
  qa_round_1.json
  acceptance_round_1.json
runs/
  product_round_1.json
  dev_round_1.json
  qa_round_1.json
  acceptance_round_1.json
evidence/
  dev_round_1/
    manifest.json
    test-output.txt
    lint-output.txt
    typecheck-output.txt
  qa_round_1/
    manifest.json
  acceptance_round_1/
    review_completion.json
```

Keep existing stage artifacts and workflow summary files. This design extends the artifact model; it does not replace it.

## Stage-Specific Enforcement Rules

### Product

Required to pass:

- PRD artifact exists
- explicit acceptance criteria exist
- contract-required artifacts exist

May not:

- directly trigger Dev without human approval

### Dev

Required to pass:

- implementation artifact exists
- self-verification evidence exists
- required command/report artifacts exist when demanded by contract

Examples of valid evidence:

- test command output
- typecheck command output
- lint command output
- commit or diff summary

Dev may submit a candidate result, but cannot mark itself complete.

### QA

Required to pass:

- independent verification evidence exists
- findings are explicitly empty or explicitly recorded

QA must not rely only on Dev's self-verification claim. If QA produces findings, the workflow routes back to Dev as it does today.

### Acceptance

Required to pass:

- acceptance coverage is explicit
- required review artifacts exist
- review-completion gate passes

Acceptance may recommend `go`, `no-go`, or `blocked`, but still cannot finalize the workflow.

## Runtime Transition Rules

The runtime should enforce:

1. no stage result may be submitted without an active `RUNNING` stage run
2. no stage run may enter `PASSED` unless all required gates pass
3. no workflow stage may advance unless the active stage run is `PASSED`
4. `FAILED` and `BLOCKED` runs must be recorded and preserved
5. a new run for the same stage/round may only be opened from a valid retry state

## Recommended Code Changes

### `agent_team/models.py`

Add:

- `StageRunRecord`
- `EvidenceRecord`
- `GateIssue`
- `GateResult`

### `agent_team/state.py`

Add:

- active run lookup
- run creation and update helpers
- evidence manifest persistence
- gate result persistence

### `agent_team/stage_contracts.py`

Upgrade evidence requirements from labels to schemas while preserving the current public contract shape where needed.

### `agent_team/review_gates.py`

Refactor into a more general gatekeeper module:

- keep current acceptance-specific review completion logic
- add contract and evidence gates
- return structured gate results instead of mutating only stage output

### `agent_team/cli.py`

Add:

- `acquire-stage-run`
- `verify-stage-result`
- `step`

Change:

- `submit-stage-result` so it stores a candidate result before advancement logic

### `agent_team/stage_machine.py`

Keep the existing high-level workflow transition logic, but make it callable only after gate success.

This file should remain the high-level workflow authority, not absorb low-level evidence validation.

## Migration Strategy

### Phase 1: Introduce Run Records Without Changing Workflow Semantics

- add `StageRunRecord`
- create run metadata alongside current behavior
- preserve current stage advancement semantics temporarily

### Phase 2: Require Active Run For Submission

- `submit-stage-result` must target an active run
- start enforcing `READY -> RUNNING -> SUBMITTED`

### Phase 3: Add Gatekeeper And Block Advancement On Failure

- `submit-stage-result` stores the candidate result
- `verify-stage-result` decides `PASSED/FAILED/BLOCKED`
- only `PASSED` may call `StageMachine.advance()`

### Phase 4: Add `step` For Harness Control

- Codex and operators query the runtime for the exact next action
- this becomes the primary harness entrypoint after `start-session`

## Risks

- Adding run states without clear CLI ergonomics could make the runtime feel heavier before it feels safer.
- Over-specifying evidence schemas too early could create unnecessary friction for simple stages.
- If `VerificationGate` tries to rerun too much automatically, it may overreach into environment mutation or tool-availability issues.

## Design Decisions

1. `verify-stage-result` should be explicit in the first implementation. A later `submit-stage-result --verify` shortcut can be added after the gate behavior stabilizes.
2. Dev evidence should require structured evidence immediately. Command evidence must include command text and exit code. Artifact-only evidence is acceptable only when the contract explicitly allows an artifact or report evidence kind.
3. Dev, QA, and Acceptance should all receive minimal strict schemas from day one. The schemas can be small, but each must prevent a stage from passing with only free-form prose.

## Recommendation

Adopt this design incrementally, starting with explicit stage-run records and a gatekeeper that blocks advancement when evidence is missing.

The key architectural decision is:

`worker submits candidate result`

not:

`worker submits completion`

That single shift is what turns the current runtime from stage-aware into truly enforcement-driven.
