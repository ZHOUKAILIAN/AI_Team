from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .models import Finding

MEMORY_LAYER_NAMES = ("raw", "extracted", "graph")


@dataclass(slots=True)
class MemoryMatch:
    layer: str
    path: str
    line_number: int
    preview: str

    def to_dict(self) -> dict[str, object]:
        return {
            "layer": self.layer,
            "path": self.path,
            "line_number": self.line_number,
            "preview": self.preview,
        }


@dataclass(slots=True)
class MemoryRetrievalResult:
    role_name: str
    query: str
    strategy: str
    matches: list[MemoryMatch] = field(default_factory=list)

    def to_markdown(self) -> str:
        if not self.matches:
            return ""
        lines = [f"- strategy: {self.strategy}", f"- query: {self.query}"]
        for match in self.matches:
            lines.append(f"- [{match.layer}] {match.path}:{match.line_number} {match.preview}")
        return "\n".join(lines)


def record_learning_layers(*, learning_dir: Path, finding: Finding, recorded_at: str) -> None:
    for layer in MEMORY_LAYER_NAMES:
        (learning_dir / layer).mkdir(parents=True, exist_ok=True)

    _append_jsonl(
        learning_dir / "raw" / "findings.jsonl",
        {
            "record_type": "finding",
            "recorded_at": recorded_at,
            "finding": finding.to_dict(),
        },
    )
    if finding.lesson:
        _append_unique_section(
            learning_dir / "extracted" / "lessons.md",
            "Extracted Lessons",
            (
                f"## {recorded_at}\n"
                f"- issue: {finding.issue}\n"
                f"- source: {finding.source_stage}\n"
                f"- severity: {finding.severity}\n"
                f"- lesson: {finding.lesson}\n"
            ),
            finding.lesson,
        )
    if finding.proposed_context_update:
        _append_unique_section(
            learning_dir / "extracted" / "context_patch.md",
            "Extracted Context Patches",
            (
                f"## {recorded_at}\n"
                f"Constraint: {finding.proposed_context_update}\n"
                f"Completion signal: {_completion_signal_for_finding(finding)}\n"
            ),
            finding.proposed_context_update,
        )
    if finding.proposed_skill_update:
        _append_unique_section(
            learning_dir / "extracted" / "skill_patch.md",
            "Extracted Skill Patches",
            (
                f"## {recorded_at}\n"
                f"Goal: {finding.proposed_skill_update}\n"
                f"Completion signal: {_completion_signal_for_finding(finding)}\n"
            ),
            finding.proposed_skill_update,
        )

    graph_path = learning_dir / "graph" / "relations.jsonl"
    _append_jsonl(
        graph_path,
        {
            "edge": f"{finding.source_stage}->{finding.target_stage}",
            "source": finding.source_stage,
            "target": finding.target_stage,
            "issue": finding.issue,
            "severity": finding.severity,
            "recorded_at": recorded_at,
        },
    )
    if finding.lesson:
        _append_jsonl(
            graph_path,
            {
                "edge": "issue->lesson",
                "issue": finding.issue,
                "lesson": finding.lesson,
                "recorded_at": recorded_at,
            },
        )
    if finding.required_evidence:
        _append_jsonl(
            graph_path,
            {
                "edge": "issue->required_evidence",
                "issue": finding.issue,
                "required_evidence": list(finding.required_evidence),
                "recorded_at": recorded_at,
            },
        )
    if _completion_signal_for_finding(finding):
        _append_jsonl(
            graph_path,
            {
                "edge": "issue->completion_signal",
                "issue": finding.issue,
                "completion_signal": _completion_signal_for_finding(finding),
                "recorded_at": recorded_at,
            },
        )


def retrieve_role_memory(
    *,
    state_root: Path,
    role_name: str,
    query: str,
    max_results: int = 8,
) -> MemoryRetrievalResult:
    role_dir = state_root / "memory" / role_name
    if not role_dir.exists() or not query.strip():
        return MemoryRetrievalResult(role_name=role_name, query=query, strategy="keyword_cli")

    matches = _cli_keyword_search(role_dir=role_dir, query=query, max_results=max_results)
    strategy = "keyword_cli"
    if not matches:
        matches = _python_keyword_search(role_dir=role_dir, query=query, max_results=max_results)
        strategy = "keyword_python_fallback" if matches else "keyword_cli"
    return MemoryRetrievalResult(role_name=role_name, query=query, strategy=strategy, matches=matches)


def _cli_keyword_search(*, role_dir: Path, query: str, max_results: int) -> list[MemoryMatch]:
    command_name = shutil.which("rg") or shutil.which("grep")
    if command_name is None:
        return []

    matches: list[MemoryMatch] = []
    seen: set[tuple[str, int]] = set()
    for term in _query_terms(query):
        if len(matches) >= max_results:
            break
        if Path(command_name).name == "rg":
            command = [command_name, "--line-number", "--ignore-case", "--fixed-strings", term, str(role_dir)]
        else:
            command = [command_name, "-R", "-n", "-i", "-F", term, str(role_dir)]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode not in {0, 1}:
            continue
        for raw_line in completed.stdout.splitlines():
            parsed = _parse_search_line(role_dir=role_dir, raw_line=raw_line)
            if parsed is None or (parsed.path, parsed.line_number) in seen:
                continue
            seen.add((parsed.path, parsed.line_number))
            matches.append(parsed)
            if len(matches) >= max_results:
                break
    return matches


def _python_keyword_search(*, role_dir: Path, query: str, max_results: int) -> list[MemoryMatch]:
    terms = [term.lower() for term in _query_terms(query)]
    matches: list[MemoryMatch] = []
    for path in sorted(role_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            lines = path.read_text().splitlines()
        except UnicodeDecodeError:
            continue
        for index, line in enumerate(lines, start=1):
            lowered = line.lower()
            if any(term in lowered for term in terms):
                matches.append(_memory_match(role_dir=role_dir, path=path, line_number=index, preview=line))
            if len(matches) >= max_results:
                return matches
    return matches


def _query_terms(query: str) -> list[str]:
    normalized = " ".join(query.strip().split())
    if not normalized:
        return []
    parts = [part for part in normalized.replace("/", " ").replace("-", " ").split() if len(part) >= 2]
    return [normalized, *parts]


def _parse_search_line(*, role_dir: Path, raw_line: str) -> MemoryMatch | None:
    path_text, separator, remainder = raw_line.partition(":")
    if not separator:
        return None
    line_number_text, separator, preview = remainder.partition(":")
    if not separator or not line_number_text.isdigit():
        return None
    return _memory_match(
        role_dir=role_dir,
        path=Path(path_text),
        line_number=int(line_number_text),
        preview=preview,
    )


def _memory_match(*, role_dir: Path, path: Path, line_number: int, preview: str) -> MemoryMatch:
    try:
        relative = path.resolve().relative_to(role_dir.resolve())
    except ValueError:
        relative = path
    layer = relative.parts[0] if relative.parts and relative.parts[0] in MEMORY_LAYER_NAMES else "legacy"
    compact_preview = " ".join(preview.strip().split())
    return MemoryMatch(
        layer=layer,
        path=str(relative),
        line_number=line_number,
        preview=compact_preview[:240],
    )


def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _append_unique_section(path: Path, title: str, content: str, marker: str) -> None:
    existing = path.read_text() if path.exists() else f"# {title}\n\n"
    if marker in existing:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(existing.rstrip() + "\n\n" + content.strip() + "\n")


def _completion_signal_for_finding(finding: Finding) -> str:
    if finding.completion_signal:
        return finding.completion_signal
    if finding.required_evidence:
        return (
            "Attach "
            + ", ".join(finding.required_evidence)
            + f" evidence showing '{finding.issue}' is closed on the target surface."
        )
    return ""
