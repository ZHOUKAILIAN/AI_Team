# AI Company Runtime State

This directory stores the persistent runtime state for the workflow engine.

## Layout
- `artifacts/<session_id>/`: all stage deliverables for one workflow run
- `sessions/<session_id>/`: journals, findings, review, and session metadata
- `memory/<Role>/`: learned overlays written back from downstream findings

## Learning Model
Base role definitions stay in the repository root folders such as `Product/` and `Dev/`.
Runtime learning does not overwrite those seed files directly. Instead it appends:
- `lessons.md`
- `context_patch.md`
- `skill_patch.md`

The orchestrator loads those overlay files on the next run to strengthen the effective role profile while keeping the original role prompts auditable.
