from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


CONFIRMED_ALIGNMENT_NAME = "confirmed_alignment.json"


@dataclass(slots=True)
class AlignmentCriterion:
    id: str
    criterion: str
    verification: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AlignmentCriterion":
        criterion_id = str(payload.get("id", "")).strip()
        criterion = str(payload.get("criterion", "")).strip()
        verification = str(payload.get("verification", "")).strip()
        if not criterion_id:
            raise ValueError("acceptance_criteria item is missing id")
        if not criterion:
            raise ValueError(f"acceptance_criteria {criterion_id} is missing criterion")
        if not verification:
            raise ValueError(f"acceptance_criteria {criterion_id} is missing verification")
        return cls(id=criterion_id, criterion=criterion, verification=verification)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class AlignmentDraft:
    requirement_understanding: list[str]
    acceptance_criteria: list[AlignmentCriterion]
    clarifying_questions: list[str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AlignmentDraft":
        understanding = _string_list(payload.get("requirement_understanding", []))
        if not understanding:
            raise ValueError("requirement_understanding must contain at least one item")

        criteria_payload = payload.get("acceptance_criteria", [])
        if not isinstance(criteria_payload, list) or not criteria_payload:
            raise ValueError("acceptance_criteria must contain at least one item")
        criteria = [
            AlignmentCriterion.from_dict(item if isinstance(item, dict) else {})
            for item in criteria_payload
        ]

        return cls(
            requirement_understanding=understanding,
            acceptance_criteria=criteria,
            clarifying_questions=_string_list(payload.get("clarifying_questions", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_understanding": list(self.requirement_understanding),
            "acceptance_criteria": [item.to_dict() for item in self.acceptance_criteria],
            "clarifying_questions": list(self.clarifying_questions),
        }


def parse_alignment_json(raw: str) -> AlignmentDraft:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"alignment output is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("alignment output must be a JSON object")
    return AlignmentDraft.from_dict(payload)


def render_alignment_for_terminal(draft: AlignmentDraft) -> str:
    lines = ["Requirement understanding:"]
    lines.extend(f"- {item}" for item in draft.requirement_understanding)
    lines.append("")
    lines.append("Acceptance criteria:")
    for item in draft.acceptance_criteria:
        lines.append(f"{item.id}. {item.criterion}")
        lines.append(f"   Verification: {item.verification}")
    if draft.clarifying_questions:
        lines.append("")
        lines.append("Clarifying questions:")
        lines.extend(f"- {item}" for item in draft.clarifying_questions)
    return "\n".join(lines)


def alignment_prompt(
    *,
    raw_request: str,
    previous_alignment: str = "",
    user_revision: str = "",
) -> str:
    parts = [
        "You are the Phase 1 Intake/Product alignment role for Agent Team.",
        "Align the user's requirement and draft measurable acceptance criteria.",
        "Focus only on requirement understanding and acceptance criteria.",
        "Return strict JSON only. Do not wrap it in markdown.",
        "",
        "Required JSON shape:",
        "{",
        '  "requirement_understanding": ["..."],',
        '  "acceptance_criteria": [{"id": "AC1", "criterion": "...", "verification": "..."}],',
        '  "clarifying_questions": ["..."]',
        "}",
        "",
        "Raw request:",
        raw_request.strip(),
    ]
    if previous_alignment.strip():
        parts.extend(["", "Previous alignment JSON:", previous_alignment.strip()])
    if user_revision.strip():
        parts.extend(["", "User revision:", user_revision.strip()])
    return "\n".join(parts)


def save_confirmed_alignment(session_dir: Path, draft: AlignmentDraft) -> Path:
    path = session_dir / CONFIRMED_ALIGNMENT_NAME
    path.write_text(json.dumps(draft.to_dict(), ensure_ascii=False, indent=2))
    return path


def load_confirmed_alignment(session_dir: Path) -> AlignmentDraft | None:
    path = session_dir / CONFIRMED_ALIGNMENT_NAME
    if not path.exists():
        return None
    return parse_alignment_json(path.read_text())


def acceptance_criteria_strings(draft: AlignmentDraft) -> list[str]:
    return [
        f"{item.id}: {item.criterion} Verification: {item.verification}"
        for item in draft.acceptance_criteria
    ]


def confirmed_request_text(raw_request: str, draft: AlignmentDraft) -> str:
    rendered = render_alignment_for_terminal(draft)
    return f"{raw_request.strip()}\n\nConfirmed alignment:\n{rendered}\n"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
