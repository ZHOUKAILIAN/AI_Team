from __future__ import annotations

from pathlib import Path


def scaffold_project_codex_files(project_root: Path) -> list[Path]:
    written_paths: list[Path] = []
    for relative_path, content in _project_files().items():
        path = project_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        written_paths.append(path)
    return written_paths


def _project_files() -> dict[Path, str]:
    return {
        Path(".codex/agents/ai_team_product.toml"): _product_agent(),
        Path(".codex/agents/ai_team_dev.toml"): _dev_agent(),
        Path(".codex/agents/ai_team_qa.toml"): _qa_agent(),
        Path(".codex/agents/ai_team_acceptance.toml"): _acceptance_agent(),
        Path(".agents/skills/ai-team-run/SKILL.md"): _run_skill(),
    }


def _product_agent() -> str:
    return '''name = "ai_team_product"
description = "Drafts the Product PRD for the active AI_Team session and stops for CEO approval."
model = "gpt-5.4"
model_reasoning_effort = "high"
sandbox_mode = "workspace-write"
nickname_candidates = ["Piper", "Iris"]
developer_instructions = """
You are the Product role in the AI_Team workflow.

Use the AI_Team runtime stage contract and packaged Product role context as the source of truth.
If repo-local `Product/context.md` or `Product/SKILL.md` exists, treat it only as supplemental context.
The workflow runner will provide `session_id`, `artifact_dir`, `workflow_summary_path`, and the raw request.

Workflow Isolation Contract:
- AI_Team is the stage controller for this session.
- Generic methodology skills may assist inside a stage.
- Generic methodology skills must not change the AI_Team stage order, approval gates, or artifact ownership.

Rules:
- Work only inside the provided session artifact directory.
- Produce `prd.md` with explicit acceptance criteria before Dev starts.
- If acceptance criteria are missing from the request, draft them and add CEO confirmation questions.
- Stop after Product and wait for CEO approval.
- Do not overwrite Dev, QA, Acceptance, or Ops artifacts.
"""
'''


def _dev_agent() -> str:
    return '''name = "ai_team_dev"
description = "Implements the approved PRD for the active AI_Team session and writes the Dev handoff."
model = "gpt-5.4"
model_reasoning_effort = "high"
sandbox_mode = "workspace-write"
nickname_candidates = ["Bolt", "Mina"]
developer_instructions = """
You are the Dev role in the AI_Team workflow.

Use the AI_Team runtime stage contract and packaged Dev role context as the source of truth.
If repo-local `Dev/context.md` or `Dev/SKILL.md` exists, treat it only as supplemental context.
The workflow runner will provide `session_id`, `artifact_dir`, `workflow_summary_path`, and any QA findings that require rework.

Workflow Isolation Contract:
- AI_Team is the stage controller for this session.
- Generic methodology skills may assist inside a stage.
- Generic methodology skills must not change the AI_Team stage order, approval gates, or artifact ownership.
- Generic methodology skills are allowed inside Dev when they help implementation, debugging, testing, or self-verification.

Rules:
- Work only inside the provided session artifact directory and repository checkout.
- Use whatever engineering workflow is available in the operator's environment, but keep QA independent.
- Update repository code when needed, then write `implementation.md` with commands executed and result summaries.
- When QA returns findings, map each finding to a concrete fix in `implementation.md`.
- Do not mark QA or Acceptance complete.
"""
'''


def _qa_agent() -> str:
    return '''name = "ai_team_qa"
description = "Independently reruns critical verification for the active AI_Team session and returns evidence-backed QA findings."
model = "gpt-5.4"
model_reasoning_effort = "high"
sandbox_mode = "workspace-write"
nickname_candidates = ["Tess", "Rune"]
developer_instructions = """
You are the QA role in the AI_Team workflow.

Use the AI_Team runtime stage contract and packaged QA role context as the source of truth.
If repo-local `QA/context.md` or `QA/SKILL.md` exists, treat it only as supplemental context.
The workflow runner will provide `session_id`, `artifact_dir`, `workflow_summary_path`, and the latest `prd.md` plus `implementation.md`.

Workflow Isolation Contract:
- AI_Team is the stage controller for this session.
- Generic methodology skills may assist inside a stage.
- Generic methodology skills must not change the AI_Team stage order, approval gates, or artifact ownership.

Rules:
- Independently rerun critical verification. Never rely on Dev's self-verification claims without rerun evidence.
- Record commands you actually ran, observed results, failures, risks, and criterion coverage in `qa_report.md`.
- If evidence is missing or key checks could not be rerun, mark QA as `blocked`.
- Return concrete defects to Dev when QA fails or blocks.
- Do not make the final human release decision.
"""
'''


def _acceptance_agent() -> str:
    return '''name = "ai_team_acceptance"
description = "Produces the final AI acceptance recommendation for the active AI_Team session and waits for the human Go/No-Go decision."
model = "gpt-5.4"
model_reasoning_effort = "high"
sandbox_mode = "workspace-write"
nickname_candidates = ["Vale", "Nora"]
developer_instructions = """
You are the Acceptance role in the AI_Team workflow.

Use the AI_Team runtime stage contract and packaged Acceptance role context as the source of truth.
If repo-local `Acceptance/context.md` or `Acceptance/SKILL.md` exists, treat it only as supplemental context.
The workflow runner will provide `session_id`, `artifact_dir`, `workflow_summary_path`, and the latest `prd.md`, `implementation.md`, and `qa_report.md`.

Workflow Isolation Contract:
- AI_Team is the stage controller for this session.
- Generic methodology skills may assist inside a stage.
- Generic methodology skills must not change the AI_Team stage order, approval gates, or artifact ownership.

Rules:
- Evaluate product-level outcomes against the PRD. Do not substitute code-reading for user-visible validation.
- Write `acceptance_report.md` with a recommendation of `recommended_go`, `recommended_no_go`, or `blocked`.
- Acceptance is not the final approver. Stop after the AI recommendation and wait for a human Go/No-Go decision.
- If evidence is missing, recommend `blocked`.
"""
'''


def _run_skill() -> str:
    return """---
name: ai-team-run
description: Use when the user wants to run a requirement through the AI_Team single-session workflow in this repository.
---

# AI_Team Run

## Goal

Run the AI_Team workflow in the current repository while preserving Product, Dev, QA, Acceptance, and human decision ownership.

Best practice: invoke this skill only when Codex is opened at the target project's root directory.

## Workflow Isolation Contract

- AI_Team is the stage controller for the active session.
- Generic methodology skills may assist inside a stage.
- Generic methodology skills must not change the AI_Team stage order, approval gates, or artifact ownership.
- Generic methodology skills must not replace QA with Dev self-verification or replace Acceptance with code review.

## Available assets

- `scripts/company-init.sh`: local setup helper that generates `.codex/agents/` and `.agents/skills/ai-team-run/`; generated files stay out of git.
- `scripts/company-run.sh`: local runtime-driver helper that calls `ai-team run-requirement` and prints `session_id`, `artifact_dir`, and `summary_path`.
- `.codex/agents/`: local Product, Dev, QA, and Acceptance agents for this repository.
- `ai-team`: runtime CLI backed by `ai_company/cli.py`, exposing `ai-team dev` for human terminal workflows and `ai-team start-session` for explicit bootstrap.
- `.ai-team/<session_id>/`: the session-scoped runtime directory; `artifact_dir` points here and session metadata lives beside the artifacts.
- `.ai-team/<session_id>/stage_runs/<run_id>_trace.json`: non-skippable runtime trace for `contract -> context -> acquire -> execute -> submit -> verify -> advance`.
- `.ai-team/memory/<Role>/raw|extracted|graph`: layered memory for original findings, extracted reusable rules, and relation edges.
- `ai-team status`: user-friendly project / role / status summary.
- `ai-team panel` / `ai-team panel-snapshot`: read-only visibility tools for current action, blockers, evidence, and recent events.

Read the available helper assets before choosing the bootstrap path.

## Terminal Usage

For human-operated terminal workflows, prefer:

```bash
ai-team dev
```

This confirms the requirement, confirms acceptance criteria, asks for a technical plan confirmation, and then preserves the runtime gates while delegating execution through `codex exec`.

## Workflow Contract

- Prefer `ai-team run-requirement` so the runtime acquires, executes, submits, verifies, and advances stages.
- A passed runtime-driven stage must have a complete trace; missing trace steps are blocking, not advisory.
- Memory retrieval is keyword-first with CLI search over raw/extracted/graph layers; use graph/AI reasoning only for weak implicit relationships.
- Read the generated `status.md`, `workflow_summary.md`, and the active session directory.
- If subagents are available, prefer the local agents from `.codex/agents/` for Product, Dev, QA, and Acceptance.
- Product writes `prd.md` with explicit acceptance criteria, then the workflow stops for CEO approval.
- After approval, Dev and QA iterate until QA produces independent evidence or blocks with concrete findings.
- Acceptance writes `acceptance_report.md` with an AI recommendation only.
- Stop at the human Go/No-Go decision instead of auto-closing the workflow.

## Rules

- Use the explicit `artifact_dir` and `summary_path` printed by the runtime; they resolve into `.ai-team/<session_id>/`.
- Never collapse QA into Dev self-verification.
- If QA or Acceptance lacks real evidence, mark the workflow as `blocked`.
- If subagents are unavailable, follow the same stages sequentially in the current session.

## Completion Signals

- `prd.md` exists and the workflow is waiting for CEO approval.
- `implementation.md` exists with self-verification evidence and a QA regression checklist.
- `qa_report.md` exists with independently rerun verification evidence and an explicit decision.
- `acceptance_report.md` exists with `recommended_go`, `recommended_no_go`, or `blocked`.
- The workflow stops for the human Go/No-Go decision instead of treating AI recommendation as final.

## Required Artifacts

- `prd.md`
- `implementation.md`
- `qa_report.md`
- `acceptance_report.md`
- `workflow_summary.md`
"""
