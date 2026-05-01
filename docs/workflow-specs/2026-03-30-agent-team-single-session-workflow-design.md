# Agent Team Single-Session Workflow Design

Date: 2026-03-30

## Summary

This design replaces the current "deterministic template backend" execution model with a single-session workflow state machine that runs inside the active Codex conversation. The same Codex session will serially act as `Product -> Dev <-> QA -> Acceptance`, while stage outputs are persisted as explicit handoff files under `.agent-team/<session_id>/`.

The goal is not to simulate a non-existent `agent_team` runtime. The goal is to make Agent Team work reliably in Codex as it actually exists today:

- one active Codex session
- strong engineering discipline inside the active Codex session
- no native multi-agent company abstraction

In this design, Agent Team owns workflow governance, role boundaries, approvals, and release gates. The `Dev` stage may use whatever engineering workflow is available in the operator's environment, while `QA` and `Acceptance` remain explicit downstream gates that must independently justify their conclusions with real evidence.

## Goals

- Make Agent Team run as a real single-session, multi-role workflow in Codex.
- Require acceptance criteria to be explicit before implementation starts.
- Stop after `Product` so the human CEO can approve the PRD and acceptance criteria.
- Allow `Dev` to use any available engineering workflow as an internal implementation discipline.
- Require `QA` to independently rerun critical verification instead of accepting `Dev` evidence at face value.
- Require `Acceptance` to perform product-level validation against the PRD and produce a recommendation, not the final human decision.
- Persist every stage handoff as auditable files.
- Support automatic `Dev <-> QA` looping until the work passes or becomes blocked.

## Non-Goals

- Do not introduce a true multi-agent runtime.
- Do not depend on Codex having an `agent_team` concept.
- Do not treat code reading, assumptions, or template text as test evidence.
- Do not auto-approve final release or deployment.
- Do not reintroduce `Ops` into the main workflow in this iteration.

## Key Decisions

### 1. Final Acceptance Model

Acceptance mode is `B`:

- `AI Acceptance` produces a recommendation
- the human CEO must make the final `Go/No-Go`

The workflow is not complete until the human decision is recorded.

### 2. Acceptance Criteria Must Exist Before Dev Starts

Acceptance criteria must be explicit in `prd.md` before the workflow is allowed to enter `Dev`.

If the user did not provide them initially, `Product` may draft them, but the workflow must stop for CEO confirmation before implementation begins.

### 3. Evidence Gate Is Strict

If `QA` or `Acceptance` lacks real evidence, the result must be `blocked`.

No fallback statuses such as "soft pass", "likely passed", or "provisional accepted" are allowed in the default workflow.

### 4. QA Must Be Independent

`Dev` can and should use its own engineering methodology, but `QA` cannot treat `Dev`'s self-verification as sufficient proof. `QA` must independently rerun critical verification and document that evidence in its own report.

### 5. Handoff Is File-Based

The workflow does not pass hidden role memory as the primary handoff channel. It passes explicit stage artifacts:

- `prd.md`
- `implementation.md`
- `qa_report.md`
- `acceptance_report.md`
- `workflow_summary.md`

This keeps the workflow auditable and compatible with a single-session Codex model.

## Workflow State Machine

### States

1. `Intake`
2. `ProductDraft`
3. `WaitForCEOApproval`
4. `Dev`
5. `QA`
6. `Acceptance`
7. `WaitForHumanDecision`
8. `Done`
9. `Blocked`

### State Transitions

```text
Intake
  -> ProductDraft

ProductDraft
  -> WaitForCEOApproval

WaitForCEOApproval
  -> ProductDraft             (if CEO requests changes)
  -> Dev                      (if CEO approves)

Dev
  -> QA

QA
  -> Dev                      (if failed with actionable defects)
  -> Acceptance               (if passed)
  -> Blocked                  (if evidence or environment prevents reliable conclusion)

Acceptance
  -> WaitForHumanDecision
  -> Blocked                  (if product-level evidence is unavailable)

WaitForHumanDecision
  -> Done                     (if CEO chooses Go or No-Go)

Blocked
  -> Done                     (workflow ends blocked)
```

### Loop Policy

The `Dev <-> QA` loop has no fixed retry count. It continues as long as there are actionable defects and progress is still possible. The loop ends only when one of these becomes true:

- `QA` passes
- the workflow is blocked by missing prerequisites
- the human explicitly intervenes

## Stage Contracts

### Intake

Inputs:

- raw user request

Outputs:

- normalized request
- new `session_id`
- initialized artifact directory
- initial `workflow_summary.md`

Responsibilities:

- detect workflow trigger phrases
- preserve the user's original intent
- carry forward any user-provided acceptance criteria

### ProductDraft

Inputs:

- raw request
- normalized request
- any user-provided acceptance criteria

Outputs:

- `prd.md`

Responsibilities:

- define the problem and scope
- make acceptance criteria explicit
- define how QA should verify the result
- define how Acceptance should judge the result

Restrictions:

- Product does not implement code
- Product cannot auto-approve its own PRD

### WaitForCEOApproval

Inputs:

- `prd.md`

Outputs:

- CEO approval decision

Responsibilities:

- pause the workflow
- ask for explicit approval or changes

Restrictions:

- Dev cannot start before approval

### Dev

Inputs:

- approved `prd.md`
- latest QA findings, if present

Outputs:

- code changes in the repository
- `implementation.md`

Responsibilities:

- implement the approved scope
- use rigorous engineering discipline for implementation work
- document exactly what changed and how it was self-verified

Restrictions:

- Dev self-verification is not equivalent to QA sign-off

### QA

Inputs:

- approved `prd.md`
- latest `implementation.md`

Outputs:

- `qa_report.md`

Responsibilities:

- independently rerun critical verification
- compare actual behavior against PRD expectations
- identify regressions and defects
- either pass, fail, or block the workflow

Restrictions:

- QA cannot pass without real evidence
- QA cannot rely only on code reading
- QA cannot simply quote Dev's results without rerunning key checks

### Acceptance

Inputs:

- approved `prd.md`
- latest `implementation.md`
- latest `qa_report.md`

Outputs:

- `acceptance_report.md`

Responsibilities:

- validate product behavior against business intent and acceptance criteria
- focus on user-visible outcomes, not internal implementation details
- produce a recommendation for the CEO

Restrictions:

- Acceptance is not the final approver
- Acceptance cannot recommend `Go` without real product-level evidence

### WaitForHumanDecision

Inputs:

- `acceptance_report.md`

Outputs:

- human decision: `go`, `no_go`, or `blocked`

Responsibilities:

- stop and wait for the CEO's final decision

## Artifact Contracts

All stage artifacts live under:

```text
.agent-team/<session_id>/
```

### workflow_summary.md

Purpose:

- single-page workflow index
- current state snapshot
- stage status summary

Required fields:

- `session_id`
- `current_state`
- `current_stage`
- `prd_status`
- `dev_status`
- `qa_status`
- `acceptance_status`
- `human_decision`
- `qa_round`
- `blocked_reason`
- artifact paths

### prd.md

Required sections:

- raw request
- problem statement
- goals
- non-goals
- user scenarios
- acceptance criteria
- QA verification focus
- Acceptance verification focus
- risks and assumptions
- CEO confirmation questions

Gate:

- missing or vague acceptance criteria blocks transition to `Dev`

### implementation.md

Required sections:

- implementation target
- change summary
- changed files
- self-verification evidence
- commands executed
- command result summary
- known limitations
- QA regression checklist
- QA finding to fix mapping, if this is a rework round

Gate:

- Dev must document exactly what it ran

### qa_report.md

Required sections:

- QA objective for this round
- independently executed commands
- observed results
- failures or risks
- PRD acceptance criteria mapping
- decision: `passed`, `failed`, or `blocked`
- defects returned to Dev

Gate:

- QA cannot mark `passed` without independent verification evidence

### acceptance_report.md

Required sections:

- acceptance inputs
- criterion-by-criterion judgment
- product-level observations
- remaining risks
- recommendation: `recommended_go`, `recommended_no_go`, or `blocked`
- recommendation to CEO

Gate:

- Acceptance cannot recommend `Go` without product-level evidence

## Evidence Rules

### Evidence That Counts

- commands that were actually run
- command outputs summarized faithfully
- real request/response results
- real UI or flow observations
- explicit logs, failures, return values, or artifact paths
- reproducible steps with concrete outcomes

### Evidence That Does Not Count

- code-reading alone
- "should work"
- "looks correct"
- "tests probably cover it"
- copied claims from another stage without rerunning
- template text that is not tied to actual execution

### QA Evidence Rule

`QA` must independently rerun critical verification. It may use `Dev`'s notes to decide what to test, but it must produce its own evidence.

### Acceptance Evidence Rule

`Acceptance` must evaluate product-level outcomes against the PRD. It must not substitute technical inference for user-visible validation.

## Relationship With Dev Methodology

Agent Team is intentionally neutral about the operator's Dev methodology, personal skills, or local setup.

### Agent Team Owns

- workflow control
- role boundaries
- handoff artifacts
- approval pauses
- QA and Acceptance gates
- final human decision pause

### Operator-Specific Dev Methodology Owns

- Dev-stage engineering discipline
- debugging rigor when technical issues are found
- self-verification inside implementation work
- verification discipline before claiming fixes
- any personal skill or tool configuration loaded by the operator's Codex environment

### Boundary Rule

Any Dev-side engineering workflow can strengthen implementation quality, but it does not collapse the downstream workflow. `QA` and `Acceptance` remain separate mandatory gates.

## Runtime Integration Plan

### Current Problem

The existing Python runtime hardcodes `DeterministicBackend()` and produces template artifacts instead of real multi-stage execution. That is useful for demos and storage, but it does not satisfy the intended workflow behavior.

### Proposed Runtime Split

#### 1. Skill Layer

The `agent-team-workflow` skill becomes the real workflow executor inside the active Codex session.

It will:

- parse trigger phrases
- create or load a workflow session
- execute the state machine
- write stage artifacts
- stop at approval points

#### 2. Persistence Layer

The Python runtime remains as a persistence and review helper.

It may continue to provide:

- session ID creation
- artifact directory creation
- review generation
- history inspection

It must no longer be treated as the authority for real QA or Acceptance outcomes.

#### 3. Future Backend Layer

If a true executable role backend is added later, it can plug into the same artifact and state model. This design does not block that future evolution.

## Migration Plan

### Phase 1

- update root `SKILL.md`
- update installed `codex-skill/agent-team-workflow/SKILL.md`
- define the new state machine behavior in the skill
- write explicit artifact templates
- make the workflow run in the current Codex session

### Phase 2

- downgrade `DeterministicBackend` from "executor" to "storage/demo helper"
- update `agent_team` review output to reflect real stage statuses
- align runtime terminology with the new file set

### Phase 3

- optionally add a true backend abstraction for richer automation
- optionally restore `Ops` outside the core delivery loop

## Risks

- The role separation still depends on prompt discipline because Codex remains a single session.
- If artifact templates are too loose, the workflow will regress back to vague status reporting.
- If approval pauses are not enforced mechanically, Dev may start before the PRD is approved.
- If QA does not explicitly rerun commands, the workflow will silently collapse back into Dev self-verification.

## Safeguards

- enforce required file sections
- enforce state transitions
- enforce approval pauses
- enforce explicit evidence rules
- enforce `blocked` as the default when evidence is missing

## Acceptance For This Design

This design is acceptable when all of the following are true:

- Agent Team can run as a single-session workflow in Codex without assuming native multi-agent support
- acceptance criteria must be explicit before Dev starts
- the workflow stops after Product for CEO approval
- Dev may use its own methodology, but QA remains independent
- QA failure automatically returns work to Dev
- missing evidence forces `blocked`
- Acceptance gives a recommendation, not final release authority
- the human CEO remains the final `Go/No-Go` decision maker
