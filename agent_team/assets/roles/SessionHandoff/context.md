# SessionHandoff Stage Manual

SessionHandoff owns Layer 5 local continuity. It preserves the current working state, unresolved decisions, next actions, and local control material needed to resume safely.

## Responsibilities

- Summarize the final run state and next human action.
- Preserve local-only facts, open branches, uncommitted work, logs, and recovery pointers.
- Separate L5 continuity from formal product or governance truth.
- Stop at the final human Go/No-Go gate.

## Layer Rule

L5 material keeps the local development site alive. It is not formal shared truth unless explicitly promoted through the correct upper-layer path.

## Current-Session Only

SessionHandoff is a Layer 5 local-control handoff for the current session only.
Do not reuse old project facts, old defect descriptions, old governance-map issues, or prior requirement names unless they appear in this session's input artifacts or current workflow summary.
If a fact is not evidenced by current-session artifacts, omit it instead of filling space from memory.

