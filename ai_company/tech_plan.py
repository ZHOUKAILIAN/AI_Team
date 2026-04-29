from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .alignment import AlignmentDraft


CONFIRMED_TECH_PLAN_NAME = "technical_plan.json"


@dataclass(slots=True)
class TechPlanDraft:
    approach_summary: str
    affected_modules: list[str]
    dependencies: list[str]
    implementation_steps: list[str]
    risks: list[str]
    testing_strategy: str
    clarifying_questions: list[str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TechPlanDraft":
        approach_summary = str(payload.get("approach_summary", "")).strip()
        if not approach_summary:
            raise ValueError("approach_summary is required")

        implementation_steps = _string_list(payload.get("implementation_steps", []))
        if not implementation_steps:
            raise ValueError("implementation_steps must contain at least one item")

        testing_strategy = str(payload.get("testing_strategy", "")).strip()
        if not testing_strategy:
            raise ValueError("testing_strategy is required")

        return cls(
            approach_summary=approach_summary,
            affected_modules=_string_list(payload.get("affected_modules", [])),
            dependencies=_string_list(payload.get("dependencies", [])),
            implementation_steps=implementation_steps,
            risks=_string_list(payload.get("risks", [])),
            testing_strategy=testing_strategy,
            clarifying_questions=_string_list(payload.get("clarifying_questions", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_tech_plan_json(raw: str) -> TechPlanDraft:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"technical plan output is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("technical plan output must be a JSON object")
    return TechPlanDraft.from_dict(payload)


def render_tech_plan_for_terminal(draft: TechPlanDraft) -> str:
    lines = [
        "Technical approach:",
        f"- {draft.approach_summary}",
        "",
        "Affected modules:",
    ]
    lines.extend(f"- {item}" for item in draft.affected_modules)
    lines.append("")
    lines.append("Dependencies:")
    lines.extend(f"- {item}" for item in draft.dependencies)
    lines.append("")
    lines.append("Implementation steps:")
    lines.extend(f"- {item}" for item in draft.implementation_steps)
    lines.append("")
    lines.append("Risks:")
    lines.extend(f"- {item}" for item in draft.risks)
    lines.append("")
    lines.append("Testing strategy:")
    lines.append(f"- {draft.testing_strategy}")
    if draft.clarifying_questions:
        lines.append("")
        lines.append("Clarifying questions:")
        lines.extend(f"- {item}" for item in draft.clarifying_questions)
    return "\n".join(lines)


def tech_plan_prompt(
    *,
    repo_root: Path,
    confirmed_alignment: AlignmentDraft,
    repo_structure: str,
    previous_plan: str = "",
    user_revision: str = "",
) -> str:
    parts = [
        "You are the Tech Lead role for AI_Team.",
        "Analyze the codebase and produce a concrete technical implementation plan.",
        "Return strict JSON only. Do not wrap it in markdown.",
        "",
        "Required JSON shape:",
        "{",
        '  "approach_summary": "Brief overview of the technical approach",',
        '  "affected_modules": ["src/auth/login.ts", "src/components/Profile.tsx"],',
        '  "dependencies": ["react@18", "zustand"],',
        '  "implementation_steps": ["1. Add auth hook", "2. Create login form component"],',
        '  "risks": ["Database migration may affect existing users"],',
        '  "testing_strategy": "Unit tests for auth hook, E2E for login flow",',
        '  "clarifying_questions": ["Should we support third-party OAuth?"]',
        "}",
        "",
        "Repository root:",
        str(repo_root),
        "",
        "Confirmed requirement:",
        json.dumps(confirmed_alignment.to_dict(), ensure_ascii=False, indent=2),
        "",
        "Repository structure:",
        repo_structure,
        "",
        "Constraints:",
        "- Prefer minimal changes over large refactors.",
        "- Consider existing patterns in the codebase.",
        "- Flag risks even if you think they are unlikely.",
        "",
        "---",
        "Your analysis will be reviewed by a human before any code is written.",
        "Be thorough and specific; vague plans lead to bad implementations.",
    ]
    if previous_plan.strip():
        parts.extend(["", "Previous plan for revision:", previous_plan.strip()])
    if user_revision.strip():
        parts.extend(["", "User revision request:", user_revision.strip()])
    return "\n".join(parts)


def save_confirmed_tech_plan(session_dir: Path, draft: TechPlanDraft) -> Path:
    path = session_dir / CONFIRMED_TECH_PLAN_NAME
    path.write_text(json.dumps(draft.to_dict(), ensure_ascii=False, indent=2))
    return path


def load_confirmed_tech_plan(session_dir: Path) -> TechPlanDraft | None:
    path = session_dir / CONFIRMED_TECH_PLAN_NAME
    if not path.exists():
        return None
    return parse_tech_plan_json(path.read_text())


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
