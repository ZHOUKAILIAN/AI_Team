---
name: session-handoff
description: Preserve Layer 5 local continuity and stop for the final human decision.
---

# SessionHandoff Contract

## Inputs

- All prior stage artifacts.
- Current workflow summary, findings, and local runtime state.

## Output

- `session-handoff.md`

The handoff must include current status, final recommendation pointer, open risks, next action, local state to preserve, and material that must not be promoted.

## Boundaries

- Do not change product, implementation, or governance artifacts.
- Do not delete local control material as a cleanup shortcut.
- Do not mark the task done before the human decision.

## Anti-Contamination Rules

- Use only current-session artifacts, workflow summary, stage results, and current worktree facts.
- Do not mention prior-session defects or unrelated repository history unless they are explicitly present in current-session inputs.
- If there is a coverage gap, name the exact current-session evidence gap and reason.
- Prefer concise factual handoff over narrative reconstruction.

