# agent-team-runtime Remaining Issues

Date: 2026-05-20

This document records runtime issues that were exposed during the RW-001 first-round validation but are intentionally deferred while we first fix the protocol-key / evidence-name mismatch.

## Current focus

Fix first:

- Models must not author protocol keys.
- Evidence keys must be runtime/framework-owned.
- Required evidence uses exact match.
- `self_verification_check` / `self_verification_semantics` must not satisfy required `self_verification`.
- Model-generated sub-checks should go into `metadata.checks`, `summary`, `command`, or other value fields.
- Preferred input shape: `evidence_by_name`, where runtime owns the map keys and the model fills each value object.

## Deferred issues

### ISSUE-001 — GovernanceReview caution vs blocking handling

Observed: `GovernanceReview` could pass gate but still stop workflow because findings were treated too broadly as blockers.

Expected:

- `critical` / `high` / `blocking` / `error` findings block.
- `medium` / `low` / `info` findings become cautions and continue to Acceptance.
- `passed_with_cautions` should be a non-blocking state.

Status: implemented in PR #31. Medium/low/info findings continue as `passed_with_cautions` and must remain documented for later alignment; critical/high/blocking/error findings still block.

### ISSUE-002 — CLI blocked diagnostics are misleading

Observed: CLI could report that a stage did not advance or required evidence was missing even when gate status was already `PASSED`.

Expected:

- Gate failure, state-transition failure, executor failure, and caution-only results must be reported separately.
- Gate `PASSED` should not be described as normal gate failure.
- Medium/low/info findings must not appear as blocking points.

Status: implemented in PR #31. Gate-passed state-transition problems are reported separately, and medium/low/info findings are shown as notes instead of blockers.

### ISSUE-003 — Codex executor CLI argument compatibility

Observed: runtime-generated Codex commands used arguments unsupported by the installed Codex CLI, such as:

- `--ignore-rules`
- `--disable plugins`
- `--output-schema` in some command modes
- `--json` in some command modes

Expected:

- Detect Codex CLI version/capabilities before building command.
- Only include supported flags.
- Record actual command, codex version, skipped flags, and reason in runtime metadata.

Status: currently worked around by `/root/ride-workbench/.agt/codex-exec-compat.sh`; not fixed in runtime source.

### ISSUE-004 — Provider/model smoke test and metadata

Observed:

- Old Codex config used `https://code.ppchat.vip/v1` and failed with 401.
- New smartingredients config works for `gpt-5.4`.
- `gpt-5.2-codex` returned 502 on both responses and chat-completions APIs.

Expected:

- Runtime should run a lightweight provider/model smoke test before long sessions.
- Runtime should record provider, base URL, wire API, model, and smoke-test result.
- Diagnostics should distinguish provider failure from model route failure.

Status: not implemented in runtime.

### ISSUE-005 — dry-run false confidence / prompt leakage

Observed: dry-run produced synthetic or instruction-like artifacts but workflow summary could look successful.

Expected:

- dry-run outputs must be marked synthetic/non-authoritative.
- dry-run can validate flow shape, not feature quality.
- CLI/UI summaries must make dry-run quality limitations explicit.

Status: not implemented.

### ISSUE-006 — executor exit code vs stage_result conflict

Observed: executor could exit non-zero while a parseable stage result claimed `status = completed` or `acceptance_status = accepted`.

Expected:

Expose separate statuses:

- `executor_status`
- `result_parse_status`
- `gate_status`
- `state_transition_status`

Do not collapse every conflict into generic stage failure.

Status: implemented in PR #31 as conservative conflict handling. Executor non-zero + parsed `completed` stage result is marked `executor_result_conflict` and blocks instead of flowing as a normal pass.

### ISSUE-007 — Rework feedback / attempt refresh clarity

Observed: feedback may not have been clearly injected into the next prompt, or later diagnostics may have mixed old/new attempt state.

Expected:

- Rework feedback must be recorded in prompt trace.
- Every attempt should have independent result/gate/diagnostic records.
- UI/CLI should show which attempt a diagnostic belongs to.
- Current attempt should not be confused with historical failed attempts.

Status: implemented in PR #31. Runtime trace records attempt/stage_run and actionable feedback count/details; prompt bundle paths are stored on the stage run; CLI blocked diagnostics show stage_run_id, attempt, and latest execution context source.

### ISSUE-008 — Runtime state vs product deliverable boundary

Observed: worktree includes `.agt/`, `.agt/_runtime/`, `.agt/local/`, `.agt/memory/`, and project governance files.

Expected:

- Runtime state should not be treated as product runtime code.
- Product deliverables and governance docs should be separated from local runtime traces.
- Suggested commit split:
  - product files: `README.md`, `.gitignore`, `package.json`, `pnpm-workspace.yaml`
  - governance docs: `agt-control/project/*.md`
  - exclude `.agt/_runtime` and local run state from product commits

Status: pending repository cleanup/commit decision.

### ISSUE-009 — Missing StageCandidate / StageVerdict layering

Observed: model output, gate result, and state transition are still tightly coupled.

Expected future shape:

```text
Model output
→ StageCandidate
→ protocol validation
→ objective validation
→ semantic/governance validation
→ StageVerdict
→ state machine transition
```

State machine should consume only runtime-validated verdict/events.

Status: design captured in `docs/workflow-specs/2026-05-19-protocol-owned-output-contract.md`; implementation deferred.

### ISSUE-010 — Lightweight model output format counters

Observed: it is hard to tell how many times the model returned output that did not match runtime expectations.

Expected:

- Keep this lightweight: only record counts, not detailed per-error trace files.
- Store aggregate counts in `workflow_summary.json` under `model_output_format_stats`.
- Count invalid JSON/protocol parse failures, unsupported fields, runtime-controlled fields, missing required evidence, derived evidence keys, repair attempts, and repair successes.

Status: implemented as lightweight counters in PR #31.

## Next alignment topic

After the evidence-key mismatch is fixed and tested, align on the design for the deferred issues before implementing them.
