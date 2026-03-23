from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from .models import Finding, SessionRecord, StageOutput, StageRecord

VALID_ROLE_NAMES = {"Product", "Dev", "QA", "Acceptance", "Ops"}


class StateStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure_layout(self) -> None:
        for directory in (
            self.root,
            self.root / "artifacts",
            self.root / "memory",
            self.root / "sessions",
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def create_session(self, request: str) -> SessionRecord:
        self.ensure_layout()
        session_id = self._next_session_id(request)
        artifact_dir = self.root / "artifacts" / session_id
        session_dir = self.root / "sessions" / session_id
        stages_dir = session_dir / "stages"

        artifact_dir.mkdir(parents=True, exist_ok=True)
        stages_dir.mkdir(parents=True, exist_ok=True)

        session = SessionRecord(
            session_id=session_id,
            request=request,
            created_at=datetime.now(UTC).isoformat(),
            session_dir=session_dir,
            artifact_dir=artifact_dir,
        )
        self._write_json(session_dir / "session.json", session.to_dict())
        (artifact_dir / "request.md").write_text(f"# Workflow Request\n\n{request.strip()}\n")
        return session

    def record_stage(self, session: SessionRecord, output: StageOutput) -> StageRecord:
        stage_slug = output.stage.lower()
        stages_dir = session.session_dir / "stages"
        artifact_path = session.artifact_dir / output.artifact_name
        journal_path = stages_dir / f"{stage_slug}_journal.md"
        findings_path = stages_dir / f"{stage_slug}_findings.json"
        metadata_path = stages_dir / f"{stage_slug}.json"

        artifact_path.write_text(output.artifact_content)
        journal_path.write_text(output.journal)
        self._write_json(findings_path, [finding.to_dict() for finding in output.findings])

        stage_record = StageRecord(
            stage=output.stage,
            artifact_name=output.artifact_name,
            artifact_path=artifact_path,
            journal_path=journal_path,
            findings_path=findings_path,
            acceptance_status=output.acceptance_status,
        )
        self._write_json(metadata_path, stage_record.to_dict())
        return stage_record

    def save_review(self, session: SessionRecord, content: str) -> Path:
        review_path = session.session_dir / "review.md"
        review_path.write_text(content)
        return review_path

    def update_session(
        self,
        session: SessionRecord,
        *,
        stage_records: list[StageRecord],
        findings: list[Finding],
        acceptance_status: str,
    ) -> None:
        payload = session.to_dict()
        payload["acceptance_status"] = acceptance_status
        payload["updated_at"] = datetime.now(UTC).isoformat()
        payload["stage_records"] = [record.to_dict() for record in stage_records]
        payload["findings"] = [finding.to_dict() for finding in findings]
        self._write_json(session.session_dir / "session.json", payload)

    def apply_learning(self, finding: Finding) -> None:
        if finding.target_stage not in VALID_ROLE_NAMES:
            return

        learning_dir = self.root / "memory" / finding.target_stage
        learning_dir.mkdir(parents=True, exist_ok=True)

        if finding.lesson:
            self._append_unique_section(
                learning_dir / "lessons.md",
                "Learned Lessons",
                (
                    f"## {self._timestamp()}\n"
                    f"- issue: {finding.issue}\n"
                    f"- source_stage: {finding.source_stage}\n"
                    f"- severity: {finding.severity}\n"
                    f"- lesson: {finding.lesson}\n"
                ),
                finding.lesson,
            )

        if finding.proposed_context_update:
            self._append_unique_section(
                learning_dir / "context_patch.md",
                "Context Patches",
                (
                    f"## {self._timestamp()}\n"
                    f"{finding.proposed_context_update}\n"
                ),
                finding.proposed_context_update,
            )

        if finding.proposed_skill_update:
            self._append_unique_section(
                learning_dir / "skill_patch.md",
                "Skill Patches",
                (
                    f"## {self._timestamp()}\n"
                    f"{finding.proposed_skill_update}\n"
                ),
                finding.proposed_skill_update,
            )

        findings_log = learning_dir / "findings.jsonl"
        with findings_log.open("a") as handle:
            handle.write(json.dumps({"applied_at": self._timestamp(), **finding.to_dict()}) + "\n")

    def latest_session_id(self) -> str | None:
        sessions_dir = self.root / "sessions"
        if not sessions_dir.exists():
            return None

        candidates = sorted(path.name for path in sessions_dir.iterdir() if path.is_dir())
        return candidates[-1] if candidates else None

    def read_review(self, session_id: str | None = None) -> str:
        target_session = session_id or self.latest_session_id()
        if not target_session:
            raise FileNotFoundError("No workflow session exists yet.")

        review_path = self.root / "sessions" / target_session / "review.md"
        if not review_path.exists():
            raise FileNotFoundError(f"Review not found for session {target_session}.")
        return review_path.read_text()

    def _append_unique_section(self, path: Path, title: str, content: str, marker: str) -> None:
        existing = path.read_text() if path.exists() else f"# {title}\n\n"
        if marker in existing:
            return

        updated = existing.rstrip() + "\n\n" + content.strip() + "\n"
        path.write_text(updated)

    def _timestamp(self) -> str:
        return datetime.now(UTC).isoformat()

    def _write_json(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload, indent=2))

    def _next_session_id(self, request: str) -> str:
        base = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{_slugify(request)}"
        candidate = base
        suffix = 1

        while (self.root / "sessions" / candidate).exists() or (self.root / "artifacts" / candidate).exists():
            suffix += 1
            candidate = f"{base}-{suffix}"

        return candidate


def artifact_name_for_stage(stage: str) -> str:
    return {
        "Product": "prd.md",
        "Dev": "tech_spec.md",
        "QA": "qa_report.md",
        "Acceptance": "acceptance_report.md",
        "Ops": "release_notes.md",
    }.get(stage, f"{stage.lower()}.md")


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned[:40] or "session"
