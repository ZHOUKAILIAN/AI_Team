# Agent Team Feedback Learning Loop Design

Date: 2026-04-10

## Summary

This design upgrades the single-session Agent Team workflow so downstream failures become actionable rework inputs instead of recommendation-only dead ends. The workflow will keep `QA failed/blocked -> Dev rework` as an explicit runtime transition, add `Acceptance recommended_no_go/blocked -> structured findings -> Product/Dev` routing, and provide a first-class path for human feedback to be normalized into the same learning pipeline.

The design also tightens runtime learning overlays so `lessons.md`, `context_patch.md`, and `skill_patch.md` encode reusable rules and completion signals rather than vague summaries. The learning format must follow the intent of `skill-standard`: precise meaning, portable guidance, and explicit success criteria.

## Goals

- Make `QA failed/blocked` route back to `Dev` in runtime behavior, not only in skill text.
- Make `Acceptance recommended_no_go/blocked` produce structured findings that can drive Product or Dev rework.
- Add a CLI entrypoint for human feedback that writes a session-scoped record and applies normalized learning overlays.
- Standardize learning overlay content so it is explicit, reusable, and suitable for future role loading.
- Preserve the existing file-based artifact model and `Finding`-driven learning contract.

## Non-Goals

- Do not build a background autonomous worker outside the active Codex session.
- Do not replace the human `Go/No-Go` decision with an automated approval.
- Do not redesign the whole workflow around true multi-agent infrastructure.
- Do not absorb arbitrary free-form feedback directly into learned memory without normalization.

## Problems In The Current Runtime

1. The default orchestrator runs stages linearly and does not re-enter `Dev` after `QA` returns defects.
2. `Acceptance` can recommend `recommended_no_go` or `blocked`, but the runtime does not emit rework findings from that result.
3. Learning overlays are only as good as the incoming `Finding`; there is no standardized formatter to keep learned rules crisp and reusable.
4. Human feedback can be stored as raw request text, but there is no explicit feedback intake path that converts it into structured learning.

## Proposed Workflow Changes

### Updated State Intent

```text
Intake
  -> ProductDraft
  -> WaitForCEOApproval
  -> Dev
  -> QA
      -> Dev                  (failed or blocked with actionable defects)
      -> Acceptance           (passed)
      -> Blocked              (no actionable path)
  -> Acceptance
      -> WaitForHumanDecision (recommended_go)
      -> Dev/Product          (recommended_no_go or blocked with actionable findings)
      -> Blocked              (no actionable path)
  -> WaitForHumanDecision
```

### Runtime Rules

- `QA` findings remain the primary technical rework signal. When `QA` returns findings, the orchestrator must increment the QA round and re-enter `Dev` with those findings available.
- `Acceptance` must be able to emit structured findings for:
  - implementation or validation gaps routed to `Dev`
  - requirement or acceptance-criteria gaps routed to `Product`
- `Acceptance` may still stop at `WaitForHumanDecision` when it recommends `recommended_go` with sufficient evidence.
- Human feedback uses the same `Finding` model and never bypasses normalization.

## Feedback Normalization Model

### Input Channels

- `QA` stage outputs
- `Acceptance` stage outputs
- human feedback via a dedicated CLI command

### Normalized `Finding`

Each learning-worthy issue must resolve to:

- `source_stage`
- `target_stage`
- `issue`
- `severity`
- `lesson`
- `proposed_context_update`
- `proposed_skill_update`
- `evidence`

### Routing Heuristics

- Product scope mismatch, unclear acceptance criteria, or missing user scenario coverage -> `Product`
- implementation bug, missing verification evidence, broken user-visible behavior, or regression gap -> `Dev`
- feedback that cannot identify an actionable owner remains recorded but does not write outside valid role memory

## Learning Overlay Standard

The runtime formatter must turn findings into overlays with these properties:

- Semantically clear: each entry states one issue and one reusable rule.
- Goal-oriented: entries describe what future runs must achieve, not shell commands.
- Portable: entries avoid repo-root-specific paths.
- Completion-signal aware: entries make the expected verification or done condition explicit.

### lessons.md

Purpose: preserve short reusable lessons.

Format per entry:

```md
## <timestamp>
- source: <source_stage>
- severity: <severity>
- issue: <issue>
- lesson: <single reusable lesson>
```

### context_patch.md

Purpose: extend role context with explicit constraints or review focus.

Format per entry:

```md
## <timestamp>
Constraint: <clear future constraint>
Completion signal: <observable condition for considering the issue addressed>
```

### skill_patch.md

Purpose: extend role skill behavior with reusable, non-command-specific guidance.

Format per entry:

```md
## <timestamp>
Goal: <what the role must achieve in similar cases>
Completion signal: <what evidence must exist before the role claims success>
```

## CLI Changes

Add a human-feedback command:

```text
python3 -m agent_team record-feedback \
  --session-id <session_id> \
  --source-stage Acceptance \
  --target-stage Dev \
  --issue "<issue>" \
  --lesson "<lesson>" \
  --context-update "<context rule>" \
  --skill-update "<skill rule>" \
  --severity high \
  --evidence "<optional evidence>"
```

Expected behavior:

- append the normalized finding to the session metadata
- write the finding to the target role learning overlay
- persist a feedback record under the session directory for auditability

## Files Expected To Change

- `agent_team/cli.py`
- `agent_team/orchestrator.py`
- `agent_team/backend.py`
- `agent_team/state.py`
- `agent_team/models.py`
- `tests/test_cli.py`
- `tests/test_orchestrator.py`
- `tests/test_state.py`
- `QA/SKILL.md`
- `Acceptance/SKILL.md`
- `Dev/SKILL.md`
- `README.md`
- `README_zh.md`
- `codex-skill/agent-team-workflow/SKILL.md`
- `SKILL.md`

## Testing Strategy

- Add orchestrator tests for `QA -> Dev` rework loops.
- Add orchestrator or backend tests for `Acceptance` feedback routing.
- Add state tests for standardized overlay formatting and feedback recording.
- Add CLI tests for the new human feedback command.
- Run targeted unit tests for the changed modules.

## Risks

- The repo already contains unstaged user changes, so edits must stay tightly scoped.
- Acceptance routing can overfit if heuristic mapping is too broad; tests should cover both Product and Dev targets.
- Learning overlay deduplication must remain stable so repeated feedback does not explode file size.
