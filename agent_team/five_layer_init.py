from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


FIVE_LAYER_SKILL_NAME = "five-layer-classifier"
DEFAULT_FIVE_LAYER_SKILL_SOURCE = (
    "https://github.com/ZHOUKAILIAN/skills/tree/"
    "feature/five-layer-classifier-skill/five-layer-classifier"
)


@dataclass(frozen=True, slots=True)
class FiveLayerClassificationResult:
    status: str
    reason: str
    five_layer_root: Path
    report_path: Path
    prompt_path: Path
    metadata_path: Path
    stdout_path: Path
    stderr_path: Path
    last_message_path: Path
    returncode: int | None = None

    def to_metadata(self) -> dict[str, object]:
        payload = asdict(self)
        for key, value in list(payload.items()):
            if isinstance(value, Path):
                payload[key] = str(value)
        return payload


def run_five_layer_classification(
    *,
    repo_root: Path,
    project_root: Path,
    mode: str = "auto",
    interactive: bool = False,
    timeout_seconds: int = 1800,
    codex_bin: str = "codex",
    skill_source: str = DEFAULT_FIVE_LAYER_SKILL_SOURCE,
) -> FiveLayerClassificationResult:
    repo_root = repo_root.resolve()
    project_root = project_root.resolve()
    five_layer_root = project_root / "five-layer"
    five_layer_root.mkdir(parents=True, exist_ok=True)

    report_path = five_layer_root / "classification.md"
    prompt_path = five_layer_root / "classification-prompt.md"
    metadata_path = five_layer_root / "classification-run.json"
    stdout_path = five_layer_root / "classification-stdout.log"
    stderr_path = five_layer_root / "classification-stderr.log"
    last_message_path = five_layer_root / "classification-last-message.md"

    skill_path = _find_five_layer_skill()
    prompt = _build_classification_prompt(
        repo_root=repo_root,
        five_layer_root=five_layer_root,
        report_path=report_path,
        skill_path=skill_path,
        skill_source=skill_source,
    )
    prompt_path.write_text(prompt)
    _ensure_placeholder_report(report_path)
    report_before_run = report_path.read_text() if report_path.exists() else ""

    if mode == "skip":
        return _record_result(
            FiveLayerClassificationResult(
                status="skipped",
                reason="five-layer classification was skipped by CLI option.",
                five_layer_root=five_layer_root,
                report_path=report_path,
                prompt_path=prompt_path,
                metadata_path=metadata_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                last_message_path=last_message_path,
            ),
            command_preview=[],
            skill_path=skill_path,
            skill_source=skill_source,
            repo_root=repo_root,
        )

    should_run = mode == "run" or (mode == "auto" and interactive)
    if not should_run:
        return _record_result(
            FiveLayerClassificationResult(
                status="skipped",
                reason="auto mode only runs codex exec from an interactive terminal; use --five-layer-classification run to force it.",
                five_layer_root=five_layer_root,
                report_path=report_path,
                prompt_path=prompt_path,
                metadata_path=metadata_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                last_message_path=last_message_path,
            ),
            command_preview=[],
            skill_path=skill_path,
            skill_source=skill_source,
            repo_root=repo_root,
        )

    codex_path = _resolve_executable(codex_bin)
    if codex_path is None:
        return _record_result(
            FiveLayerClassificationResult(
                status="blocked",
                reason=f"codex executable was not found: {codex_bin}",
                five_layer_root=five_layer_root,
                report_path=report_path,
                prompt_path=prompt_path,
                metadata_path=metadata_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                last_message_path=last_message_path,
                returncode=127,
            ),
            command_preview=[],
            skill_path=skill_path,
            skill_source=skill_source,
            repo_root=repo_root,
        )

    if skill_path is None and not skill_source.strip():
        return _record_result(
            FiveLayerClassificationResult(
                status="blocked",
                reason=f"{FIVE_LAYER_SKILL_NAME} skill has no local installation and no remote source URL.",
                five_layer_root=five_layer_root,
                report_path=report_path,
                prompt_path=prompt_path,
                metadata_path=metadata_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                last_message_path=last_message_path,
                returncode=126,
            ),
            command_preview=[],
            skill_path=skill_path,
            skill_source=skill_source,
            repo_root=repo_root,
        )

    command = _build_codex_command(
        codex_bin=codex_path,
        repo_root=repo_root,
        last_message_path=last_message_path,
        prompt=prompt,
    )
    command_preview = [*command[:-1], "<classification-prompt>"]
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        stdout_path.write_text("")
        stderr_path.write_text(str(exc))
        return _record_result(
            FiveLayerClassificationResult(
                status="blocked",
                reason=str(exc),
                five_layer_root=five_layer_root,
                report_path=report_path,
                prompt_path=prompt_path,
                metadata_path=metadata_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                last_message_path=last_message_path,
                returncode=127,
            ),
            command_preview=command_preview,
            skill_path=skill_path,
            skill_source=skill_source,
            repo_root=repo_root,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _coerce_stream_text(exc.stdout)
        stderr = _coerce_stream_text(exc.stderr) or f"codex exec timed out after {timeout_seconds} seconds."
        stdout_path.write_text(stdout)
        stderr_path.write_text(stderr)
        return _record_result(
            FiveLayerClassificationResult(
                status="failed",
                reason=f"codex exec timed out after {timeout_seconds} seconds.",
                five_layer_root=five_layer_root,
                report_path=report_path,
                prompt_path=prompt_path,
                metadata_path=metadata_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                last_message_path=last_message_path,
                returncode=124,
            ),
            command_preview=command_preview,
            skill_path=skill_path,
            skill_source=skill_source,
            repo_root=repo_root,
        )

    stdout_path.write_text(completed.stdout)
    stderr_path.write_text(completed.stderr)
    report_changed = report_path.exists() and report_path.read_text() != report_before_run
    if completed.returncode == 0 and _report_has_real_content(report_path) and report_changed:
        status = "completed"
        reason = "five-layer classification completed."
    elif completed.returncode == 0:
        status = "failed"
        reason = "codex exec completed but did not write a fresh classification report."
    else:
        status = "failed"
        reason = f"codex exec exited with status {completed.returncode}."

    return _record_result(
        FiveLayerClassificationResult(
            status=status,
            reason=reason,
            five_layer_root=five_layer_root,
            report_path=report_path,
            prompt_path=prompt_path,
            metadata_path=metadata_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            last_message_path=last_message_path,
            returncode=completed.returncode,
        ),
        command_preview=command_preview,
        skill_path=skill_path,
        skill_source=skill_source,
        repo_root=repo_root,
    )


def _find_five_layer_skill() -> Path | None:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        candidates = [Path(codex_home) / "skills" / FIVE_LAYER_SKILL_NAME / "SKILL.md"]
    else:
        candidates = [Path.home() / ".codex" / "skills" / FIVE_LAYER_SKILL_NAME / "SKILL.md"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _build_classification_prompt(
    *,
    repo_root: Path,
    five_layer_root: Path,
    report_path: Path,
    skill_path: Path | None,
    skill_source: str,
) -> str:
    local_skill_location = (
        "local cache present; path intentionally omitted because local caches are machine-specific"
        if skill_path is not None
        else "not installed"
    )
    source_url = skill_source.strip() or "not configured"
    target_scope = _portable_repo_path(repo_root, repo_root)
    report_location = _portable_repo_path(report_path, repo_root)
    five_layer_location = _portable_repo_path(five_layer_root, repo_root)
    return f"""Use the {FIVE_LAYER_SKILL_NAME} skill to classify this repository during Agent Team project init.

Target scope: {target_scope}
Purpose: project init five-layer split audit, formal-entry discovery, and agent orientation.
Output destination: {report_location}
Allowed write area: {five_layer_location}
Skill source URL: {source_url}
Local skill path, if available: {local_skill_location}

Required behavior:
1. Load and follow the remote skill source URL first. If a local skill path is also available, treat it only as a cache or fallback.
2. Classify the repository under the AI Coding five-layer model: L1 product definition, L2 product implementation, L3 project landing, L4 repository governance, L5 local development control, and research/outside-five-layers.
3. Treat this as a classification and split-preparation pass only. Do not move, rename, delete, publish, or physically split files.
4. Inspect active project docs and representative source files before judging. Do not classify by file extension or directory name alone.
5. If the repository is large, use file-group classification, but state the grouping rule, exclusions, and unresolved files clearly.
6. Identify stable formal entries for L1, L3, and L4 when they exist, and identify task/session-local L5 material that must stay local.
7. Apply the conflict rule: lower layers depend on upper layers; lower layers may report drift or delta but must not silently rewrite upper-layer truth.
8. Include high-risk misclassification warnings, recommended migration/split/downgrade/local-retention actions, and a proof package.
9. Write the complete Markdown report to exactly: {report_location}
10. Keep any auxiliary notes, if needed, under: {five_layer_location}

Return a concise final message that names the report path and whether the classification is complete, blocked, or needs human decisions.
"""


def _build_codex_command(
    *,
    codex_bin: str,
    repo_root: Path,
    last_message_path: Path,
    prompt: str,
) -> list[str]:
    return [
        codex_bin,
        "exec",
        "--cd",
        str(repo_root),
        "--sandbox",
        "workspace-write",
        "-c",
        'approval_policy="never"',
        "--output-last-message",
        str(last_message_path),
        "--ignore-rules",
        "--disable",
        "plugins",
        "--ephemeral",
        "--skip-git-repo-check",
        prompt,
    ]


def _resolve_executable(command: str) -> str | None:
    path = Path(command).expanduser()
    if path.is_absolute() or "/" in command:
        return str(path) if path.exists() else None
    return shutil.which(command)


def _record_result(
    result: FiveLayerClassificationResult,
    *,
    command_preview: list[str],
    skill_path: Path | None,
    skill_source: str,
    repo_root: Path,
) -> FiveLayerClassificationResult:
    metadata = _portable_result_metadata(result, repo_root=repo_root)
    metadata["generated_at"] = datetime.now(timezone.utc).isoformat()
    metadata["skill_name"] = FIVE_LAYER_SKILL_NAME
    metadata["skill_path"] = "local-cache-present" if skill_path is not None else ""
    metadata["skill_source"] = skill_source
    metadata["command"] = _portable_command_preview(command_preview, repo_root=repo_root)
    result.metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return result


def _portable_result_metadata(
    result: FiveLayerClassificationResult,
    *,
    repo_root: Path,
) -> dict[str, object]:
    payload = asdict(result)
    for key, value in list(payload.items()):
        if isinstance(value, Path):
            payload[key] = _portable_repo_path(value, repo_root)
    return payload


def _portable_command_preview(command_preview: list[str], *, repo_root: Path) -> list[str]:
    portable: list[str] = []
    for token in command_preview:
        if token == "<classification-prompt>":
            portable.append(token)
            continue
        path = Path(token)
        if path.is_absolute():
            if path.name == "codex":
                portable.append("codex")
            else:
                portable.append(_portable_repo_path(path, repo_root))
            continue
        portable.append(token)
    return portable


def _portable_repo_path(path: Path, repo_root: Path) -> str:
    path = path.resolve()
    repo_root = repo_root.resolve()
    if path == repo_root:
        return "."
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.name


def _ensure_placeholder_report(report_path: Path) -> None:
    if report_path.exists() and _report_has_real_content(report_path):
        return
    report_path.write_text(
        "# Five-Layer Classification\n\n"
        "Status: pending.\n\n"
        "This placeholder is replaced when `agent-team init` completes the Codex five-layer classification run.\n"
    )


def _report_has_real_content(report_path: Path) -> bool:
    if not report_path.exists():
        return False
    content = report_path.read_text()
    return "Status: pending." not in content and len(content.strip()) > 120


def _coerce_stream_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
