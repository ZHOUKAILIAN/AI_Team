from __future__ import annotations

import json
import os
import signal
import re
import shutil
import subprocess
from hashlib import sha256
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .codex_isolation import default_codex_home, isolated_codex_env, prepare_isolated_codex_home
from .executor_env import build_executor_env, executor_env_config_path
from .execution_context import StageExecutionContext, build_stage_execution_context
from .gate_evaluator import GateEvaluator, NoopJudge
from .gatekeeper import evaluate_candidate
from .intake import parse_intake_message
from .models import EvidenceItem, Finding, GateResult, StageContract, StageResultEnvelope, WorkflowSummary
from .openai_sandbox_judge import OpenAISandboxJudge, OpenAISandboxJudgeUnavailable
from .stage_contracts import build_stage_contract
from .stage_machine import StageMachine
from .stage_payload import ALLOWED_STAGE_PAYLOAD_FIELDS, FORBIDDEN_STAGE_PAYLOAD_FIELDS, envelope_from_stage_payload
from .stage_policies import default_policy_registry
from .state import StageRunStateError, StateStore, artifact_name_for_stage
from .skill_registry import Skill, skill_injection_text, skill_scope
from .workflow import EXECUTABLE_STATES, artifact_key_for


REQUIRED_PASS_TRACE_STEPS = [
    "contract_built",
    "execution_context_built",
    "stage_run_acquired",
    "executor_started",
    "executor_completed",
    "worktree_changes_detected",
    "result_submitted",
    "gate_evaluated",
    "state_advanced",
]


@dataclass(slots=True)
class RuntimeDriverOptions:
    executor: str = "codex-exec"
    executor_command: str = ""
    command_timeout_seconds: int = 3600
    auto_advance_intermediate: bool = False
    max_stage_runs: int = 12
    judge: str = "off"
    model: str = "gpt-5.4"
    docker_image: str = "python:3.13-slim"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_proxy_url: str | None = None
    openai_user_agent: str = "Agent-Team-Runtime/0.1"
    openai_oa: str | None = None
    codex_model: str = ""
    codex_sandbox: str = "workspace-write"
    codex_approval_policy: str = "never"
    codex_extra_args: list[str] = field(default_factory=list)
    enabled_skills_by_stage: dict[str, list[Skill]] = field(default_factory=dict)
    codex_isolate_home: bool = True
    codex_ignore_rules: bool = True
    codex_disable_plugins: bool = True
    codex_ephemeral: bool = False
    codex_skip_git_repo_check: bool = True
    codex_capability_check: bool = True
    provider_smoke_check: bool = False
    provider_smoke_command: str = ""
    interactive: bool = False
    trace_prompts: bool = False
    max_output_repair_attempts: int = 2


@dataclass(slots=True)
class RuntimeDriverResult:
    session_id: str
    artifact_dir: Path
    summary_path: Path
    status: str
    current_state: str
    current_stage: str
    acceptance_status: str
    human_decision: str
    next_action: str = ""
    stage_run_count: int = 0
    gate_status: str = ""
    gate_reason: str = ""


@dataclass(slots=True)
class StageExecutionRequest:
    repo_root: Path
    state_store: StateStore
    session_id: str
    run_id: str
    contract: StageContract
    context: StageExecutionContext
    contract_path: Path
    context_path: Path
    result_path: Path
    output_schema_path: Path
    prompt_path: Path | None = None
    skill_asset_root: Path | None = None
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    skills: list[Skill] = field(default_factory=list)
    executor_env_config_path: Path | None = None
    executor_metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeDriverError(RuntimeError):
    pass


class StagePayloadProtocolError(ValueError):
    pass


MODEL_OUTPUT_FORMAT_STAT_KEYS = (
    "invalid_json_count",
    "unsupported_field_count",
    "runtime_controlled_field_count",
    "missing_required_evidence_count",
    "derived_evidence_key_count",
    "repair_attempt_count",
    "repair_success_count",
)


class StageExecutor(Protocol):
    name: str

    def execute(self, request: StageExecutionRequest) -> StageResultEnvelope:
        raise NotImplementedError


def _write_stage_run_streams(request: StageExecutionRequest, *, stdout: object, stderr: object) -> None:
    request.result_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path = getattr(request, "stdout_path", None) or request.result_path.parent / f"{request.run_id}_stdout.txt"
    stderr_path = getattr(request, "stderr_path", None) or request.result_path.parent / f"{request.run_id}_stderr.txt"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(_coerce_stream_text(stdout))
    stderr_path.write_text(_coerce_stream_text(stderr))


def _skill_trace_entry(skill: Skill, skill_asset_root: Path, included_in_prompt: bool) -> dict[str, Any]:
    installed_path = skill_asset_root / skill.name
    return {
        "name": skill.name,
        "description": skill.description,
        "source": skill.source,
        "source_ref": skill.source_ref or str(skill.path.parent.resolve()),
        "scope": skill_scope(skill.source),
        "path": str(skill.path),
        "stages": list(skill.stages),
        "delivery": skill.delivery,
        "included_in_prompt": included_in_prompt,
        "installed_path": str(installed_path) if skill.delivery == "sandbox" else "",
        "sandbox_files": list(skill.sandbox_files),
        "env_vars": list(skill.env_vars),
    }


def _install_runtime_sandbox_skills(skills: list[Skill], skill_asset_root: Path) -> None:
    for skill in skills:
        if skill.delivery != "sandbox":
            continue
        destination = skill_asset_root / skill.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(skill.path.parent, destination)


def _coerce_stream_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


_CODEX_SESSION_ID_RE = re.compile(r'"(?:conversation_id|session_id|id)"\s*:\s*"([^"\s]+)"')


_CODEX_EXEC_CAPABILITIES_CACHE: set[str] | None = None


def _default_codex_capabilities() -> set[str]:
    return {
        "--cd",
        "--sandbox",
        "--output-schema",
        "--json",
        "-o",
        "--output-last-message",
        "--skip-git-repo-check",
        "--disable",
        "--ephemeral",
    }


def _codex_exec_capabilities() -> set[str]:
    global _CODEX_EXEC_CAPABILITIES_CACHE
    if _CODEX_EXEC_CAPABILITIES_CACHE is not None:
        return set(_CODEX_EXEC_CAPABILITIES_CACHE)
    try:
        completed = subprocess.run(
            ["codex", "exec", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        help_text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    except (FileNotFoundError, subprocess.TimeoutExpired, TypeError):
        help_text = ""
    capabilities = {flag for flag in _default_codex_capabilities() if flag in help_text}
    if "-o," in help_text or "-o " in help_text:
        capabilities.add("-o")
    if not capabilities:
        capabilities = _default_codex_capabilities()
    _CODEX_EXEC_CAPABILITIES_CACHE = set(capabilities)
    return set(capabilities)


def _load_codex_resume_id(request: StageExecutionRequest) -> str:
    store = getattr(request, "state_store", None)
    if store is None:
        return ""
    try:
        state = store.load_codex_exec_state(request.session_id)
    except (AttributeError, FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return ""
    for key in ("conversation_id", "session_id", "resume_id"):
        value = state.get(key)
        if _looks_like_codex_session_id(value):
            return str(value)
    return ""


def _save_codex_resume_id(
    request: StageExecutionRequest,
    conversation_id: str,
    *,
    codex_home: Path | None = None,
) -> None:
    if not _looks_like_codex_session_id(conversation_id):
        return
    store = getattr(request, "state_store", None)
    if store is None:
        return
    state: dict[str, object] = {"conversation_id": conversation_id}
    if codex_home is not None:
        state["codex_home"] = str(codex_home)
    try:
        store.save_codex_exec_state(request.session_id, state)
    except (AttributeError, FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return


def _codex_env_for_stage_request(request: StageExecutionRequest) -> tuple[dict[str, str], Path | None]:
    store = getattr(request, "state_store", None)
    if store is None:
        return build_executor_env(config_path=request.executor_env_config_path), None
    codex_home = store.codex_home_path(request.session_id)
    prepare_isolated_codex_home(source_home=default_codex_home(), target_home=codex_home)
    env = build_executor_env(config_path=request.executor_env_config_path)
    env["CODEX_HOME"] = str(codex_home)
    return env, codex_home


def _extract_codex_session_id(stream_text: str) -> str:
    latest = ""
    for line in stream_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            event = None
        event_id = _codex_session_id_from_event(event)
        if event_id:
            latest = event_id
            continue
        if "session_meta" not in stripped and "conversation_id" not in stripped and "session_id" not in stripped:
            continue
        for match in _CODEX_SESSION_ID_RE.finditer(stripped):
            value = match.group(1)
            if _looks_like_codex_session_id(value):
                latest = value
    return latest


def _codex_session_id_from_event(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    event_type = value.get("type")
    payload = value.get("payload")
    if isinstance(payload, dict):
        payload_keys = ("id", "session_id", "conversation_id") if event_type == "session_meta" else (
            "session_id",
            "conversation_id",
        )
        for key in payload_keys:
            candidate = payload.get(key)
            if _looks_like_codex_session_id(candidate):
                return str(candidate)
    if event_type == "session_meta":
        for key in ("id", "session_id", "conversation_id"):
            candidate = value.get(key)
            if _looks_like_codex_session_id(candidate):
                return str(candidate)
    for key in ("conversation_id", "session_id"):
        candidate = value.get(key)
        if _looks_like_codex_session_id(candidate):
            return str(candidate)
    return ""


def _looks_like_codex_session_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    return bool(8 <= len(text) <= 200 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", text))


def _latest_codex_session_id(codex_home: Path | None) -> str:
    if codex_home is None or not codex_home.exists():
        return ""
    candidates = sorted(
        (path for path in (codex_home / "sessions").glob("**/*.jsonl") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            session_id = _extract_codex_session_id(path.read_text(errors="replace"))
        except OSError:
            continue
        if session_id:
            return session_id
    return ""



def _run_subprocess_with_timeout(command: list[str], *, cwd: Path, env: dict[str, str] | None, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    if getattr(subprocess.run, "__module__", "subprocess") != "subprocess":
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=env,
            stdin=subprocess.DEVNULL,
        )
    kwargs: dict[str, object] = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "env": env,
        "stdin": subprocess.DEVNULL,
        "start_new_session": True,
    }
    process = subprocess.Popen(command, **kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return subprocess.CompletedProcess(command, process.returncode, stdout=stdout, stderr=stderr)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
        stderr_text = _coerce_stream_text(stderr)
        timeout_msg = f"Command timed out after {timeout_seconds} seconds."
        stderr_text = (stderr_text + "\n" + timeout_msg).strip() if stderr_text else timeout_msg
        return subprocess.CompletedProcess(command, 124, stdout=_coerce_stream_text(stdout), stderr=stderr_text)

def _record_codex_invocation_metadata(
    request: StageExecutionRequest,
    *,
    command: list[str],
    resume_id: str,
    conversation_id: str,
    codex_home: Path | None,
    ephemeral: bool,
    returncode: int,
) -> None:
    sanitized_command = list(command)
    if sanitized_command and len(sanitized_command[-1]) > 200:
        sanitized_command[-1] = "<prompt>"
    request.executor_metadata["codex_exec"] = {
        "mode": "resume" if resume_id else "new",
        "resume_id": resume_id,
        "conversation_id": conversation_id,
        "codex_home": str(codex_home) if codex_home is not None else "",
        "ephemeral": ephemeral,
        "returncode": returncode,
        "command": sanitized_command,
    }


def run_requirement(
    *,
    repo_root: Path,
    state_root: Path,
    message: str = "",
    session_id: str = "",
    options: RuntimeDriverOptions | None = None,
) -> RuntimeDriverResult:
    opts = options or RuntimeDriverOptions()
    store = StateStore(state_root)
    store.ensure_layout()
    session = store.load_session(session_id) if session_id else _create_driver_session(
        store,
        message,
        interactive=opts.interactive,
    )
    _record_provider_smoke_metadata(store=store, session=session, options=opts)
    if opts.interactive:
        _ensure_interactive_runtime_mode(store=store, session_id=session.session_id)
    executor = build_stage_executor(opts)

    stage_run_count = 0
    while True:
        summary = store.load_workflow_summary(session.session_id)
        waiting = _handle_wait_state(
            repo_root=repo_root,
            store=store,
            summary=summary,
            auto_advance_intermediate=opts.auto_advance_intermediate,
        )
        if waiting is not None:
            return _result_from_summary(
                store=store,
                session_id=session.session_id,
                status=waiting[0],
                next_action=waiting[1],
                stage_run_count=stage_run_count,
            )

        summary = store.load_workflow_summary(session.session_id)
        stage = _expected_submission_stage(summary)
        if stage is None:
            status = "done" if summary.current_state == "Done" else "idle"
            return _result_from_summary(
                store=store,
                session_id=session.session_id,
                status=status,
                stage_run_count=stage_run_count,
            )
        if stage_run_count >= opts.max_stage_runs:
            return _result_from_summary(
                store=store,
                session_id=session.session_id,
                status="blocked",
                next_action="increase --max-stage-runs or inspect the active findings",
                stage_run_count=stage_run_count,
                gate_status="BLOCKED",
                gate_reason=f"Runtime driver reached max_stage_runs={opts.max_stage_runs}.",
            )

        gate_result = _execute_stage(
            repo_root=repo_root,
            store=store,
            session_id=session.session_id,
            stage=stage,
            executor=executor,
            options=opts,
        )
        stage_run_count += 1
        if gate_result.status != "PASSED":
            return _result_from_summary(
                store=store,
                session_id=session.session_id,
                status=gate_result.status.lower(),
                stage_run_count=stage_run_count,
                gate_status=gate_result.status,
                gate_reason=gate_result.reason,
            )


def build_stage_executor(options: RuntimeDriverOptions) -> StageExecutor:
    if options.executor == "dry-run":
        return DryRunStageExecutor()
    if options.executor == "command":
        if not options.executor_command.strip():
            raise RuntimeDriverError("--executor-command is required when --executor command is used.")
        return CommandStageExecutor(
            command=options.executor_command,
            timeout_seconds=options.command_timeout_seconds,
        )
    if options.executor == "codex-exec":
        return CodexExecStageExecutor(options)
    raise RuntimeDriverError(f"Unsupported runtime driver executor: {options.executor}")


class DryRunStageExecutor:
    name = "dry-run"

    def execute(self, request: StageExecutionRequest) -> StageResultEnvelope:
        stage = request.contract.stage
        artifact_name = _contract_artifact_name(request.contract)
        return StageResultEnvelope(
            session_id=request.session_id,
            stage=stage,
            status="completed",
            artifact_name=artifact_name,
            artifact_content=_dry_run_artifact_content(stage, request.context, artifact_name=artifact_name),
            contract_id=request.contract.contract_id,
            journal=f"Dry-run executor produced {artifact_name} for {stage}.",
            evidence=_default_evidence(stage, artifact_name=artifact_name),
            summary=f"{stage} dry-run result satisfied the stage contract.",
            acceptance_status="recommended_go" if stage == "Acceptance" else "",
            supplemental_artifacts=_dry_run_supplemental_artifacts(stage, request.context),
            executor_status="synthetic",
            executor_exit_code=0,
            result_parse_status="synthetic",
            dry_run=True,
            authoritative=False,
        )


class CommandStageExecutor:
    name = "command"

    def __init__(self, *, command: str, timeout_seconds: int) -> None:
        self.command = command
        self.timeout_seconds = timeout_seconds

    def execute(self, request: StageExecutionRequest) -> StageResultEnvelope:
        request.result_path.parent.mkdir(parents=True, exist_ok=True)
        env = build_executor_env(config_path=request.executor_env_config_path)
        env.update(_stage_environment(request))
        try:
            completed = subprocess.run(
                self.command,
                cwd=request.repo_root,
                env=env,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _coerce_stream_text(exc.stdout)
            stderr = _coerce_stream_text(exc.stderr) or f"Executor timed out after {self.timeout_seconds} seconds."
            _record_stage_status_metadata(request, executor_status="timeout", executor_exit_code=124, result_parse_status="not_produced")
            _write_stage_run_streams(
                request,
                stdout=stdout,
                stderr=stderr,
            )
            return _blocked_result_from_process(
                request=request,
                command=self.command,
                stdout=stdout,
                stderr=stderr,
                exit_code=124,
            )
        _write_stage_run_streams(request, stdout=completed.stdout, stderr=completed.stderr)
        _record_stage_status_metadata(request, executor_status="completed" if completed.returncode == 0 else "failed", executor_exit_code=completed.returncode)
        if request.result_path.exists():
            _record_stage_status_metadata(request, result_parse_status="candidate_result_file")
            return _stage_result_from_json_text(
                request=request,
                value=request.result_path.read_text(),
                source=str(request.result_path),
            )
        if completed.stdout.strip():
            _record_stage_status_metadata(request, result_parse_status="candidate_stdout")
            return _stage_result_from_json_text(request=request, value=completed.stdout, source="stdout")
        _record_stage_status_metadata(request, result_parse_status="not_produced")
        return _blocked_result_from_process(
            request=request,
            command=self.command,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
        )


class CodexExecStageExecutor:
    name = "codex-exec"

    def __init__(self, options: RuntimeDriverOptions) -> None:
        self.options = options

    def execute(self, request: StageExecutionRequest) -> StageResultEnvelope:
        request.result_path.parent.mkdir(parents=True, exist_ok=True)
        prompt = _build_codex_prompt(request)
        if request.prompt_path is not None:
            request.prompt_path.parent.mkdir(parents=True, exist_ok=True)
            request.prompt_path.write_text(prompt)

        completed = self._run_codex(request, prompt=prompt, output_path=request.result_path)
        _write_stage_run_streams(request, stdout=completed.stdout, stderr=completed.stderr)
        _record_stage_status_metadata(request, executor_status="completed" if completed.returncode == 0 else "failed", executor_exit_code=completed.returncode)
        if completed.returncode != 0 and not request.result_path.exists():
            _record_stage_status_metadata(request, result_parse_status="not_produced")
            return _blocked_result_from_process(
                request=request,
                command="codex exec",
                stdout=completed.stdout,
                stderr=completed.stderr,
                exit_code=completed.returncode,
            )
        if not request.result_path.exists():
            raise RuntimeDriverError("codex exec completed without writing the stage result file.")

        raw_output = request.result_path.read_text()
        try:
            result = _parse_stage_result_json_text(request=request, value=raw_output, source=str(request.result_path))
            _record_stage_status_metadata(request, result_parse_status="parsed")
            return result
        except StagePayloadProtocolError as exc:
            _record_stage_status_metadata(request, result_parse_status="protocol_error")
            _increment_model_output_format_stats(request=request, **_parse_protocol_error_stats(exc))
            if self.options.max_output_repair_attempts <= 0:
                return _invalid_stage_payload_result(request=request, value=raw_output, source=str(request.result_path), error=exc)
            return self._repair_stage_output(request=request, previous_output=raw_output, error=exc)

    def _run_codex(
        self,
        request: StageExecutionRequest,
        *,
        prompt: str,
        output_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        resume_id = "" if self.options.codex_ephemeral else _load_codex_resume_id(request)
        command = self._build_codex_command(request, prompt=prompt, output_path=output_path, resume_id=resume_id)
        codex_home: Path | None = None
        completed: subprocess.CompletedProcess[str]
        try:
            if self.options.codex_isolate_home:
                if self.options.codex_ephemeral or getattr(request, "state_store", None) is None:
                    with isolated_codex_env(env_config_path=request.executor_env_config_path) as env:
                        completed = _run_subprocess_with_timeout(
                            command,
                            cwd=request.repo_root,
                            env=env,
                            timeout_seconds=self.options.command_timeout_seconds,
                        )
                else:
                    env, codex_home = _codex_env_for_stage_request(request)
                    completed = _run_subprocess_with_timeout(
                        command,
                        cwd=request.repo_root,
                        env=env,
                        timeout_seconds=self.options.command_timeout_seconds,
                    )
            else:
                completed = _run_subprocess_with_timeout(
                    command,
                    cwd=request.repo_root,
                    env=None,
                    timeout_seconds=self.options.command_timeout_seconds,
                )
        except FileNotFoundError as exc:
            completed = subprocess.CompletedProcess(command, 127, stdout="", stderr=str(exc))
        except subprocess.TimeoutExpired as exc:
            stdout = _coerce_stream_text(exc.stdout)
            stderr = _coerce_stream_text(exc.stderr) or f"codex exec timed out after {self.options.command_timeout_seconds} seconds."
            completed = subprocess.CompletedProcess(command, 124, stdout=stdout, stderr=stderr)

        conversation_id = "" if self.options.codex_ephemeral else _extract_codex_session_id(completed.stdout)
        if not conversation_id and not self.options.codex_ephemeral:
            conversation_id = _latest_codex_session_id(codex_home)
        if conversation_id and not self.options.codex_ephemeral:
            _save_codex_resume_id(request, conversation_id, codex_home=codex_home)
        _record_codex_invocation_metadata(
            request,
            command=command,
            resume_id=resume_id,
            conversation_id=conversation_id,
            codex_home=codex_home,
            ephemeral=self.options.codex_ephemeral,
            returncode=completed.returncode,
        )
        return completed

    def _build_codex_command(
        self,
        request: StageExecutionRequest,
        *,
        prompt: str,
        output_path: Path,
        resume_id: str = "",
    ) -> list[str]:
        capabilities = _codex_exec_capabilities() if self.options.codex_capability_check else _default_codex_capabilities()
        skipped_flags: list[str] = []
        output_flag = "-o" if "-o" in capabilities else "--output-last-message"
        if resume_id:
            command = [
                "codex",
                "exec",
                "resume",
                "-c",
                f'approval_policy="{self.options.codex_approval_policy}"',
            ]
            if "--output-schema" in capabilities:
                command.extend(["--output-schema", str(request.output_schema_path)])
            else:
                skipped_flags.append("--output-schema")
            if "--json" in capabilities:
                command.append("--json")
            else:
                skipped_flags.append("--json")
            command.extend([output_flag, str(output_path)])
        else:
            command = ["codex", "exec"]
            if "--cd" in capabilities:
                command.extend(["--cd", str(request.repo_root)])
            else:
                skipped_flags.append("--cd")
            if "--sandbox" in capabilities:
                command.extend(["--sandbox", self.options.codex_sandbox])
            else:
                skipped_flags.append("--sandbox")
            command.extend([
                "-c",
                f'approval_policy="{self.options.codex_approval_policy}"',
            ])
            if "--output-schema" in capabilities:
                command.extend(["--output-schema", str(request.output_schema_path)])
            else:
                skipped_flags.append("--output-schema")
            if "--json" in capabilities:
                command.append("--json")
            else:
                skipped_flags.append("--json")
            command.extend([output_flag, str(output_path)])
        if self.options.codex_ignore_rules:
            if "--ignore-rules" in capabilities:
                command.append("--ignore-rules")
            else:
                skipped_flags.append("--ignore-rules")
        if self.options.codex_disable_plugins:
            if "--disable" in capabilities:
                command.extend(["--disable", "plugins"])
            else:
                skipped_flags.append("--disable plugins")
        if self.options.codex_ephemeral and not resume_id:
            if "--ephemeral" in capabilities:
                command.append("--ephemeral")
            else:
                skipped_flags.append("--ephemeral")
        if self.options.codex_skip_git_repo_check:
            if "--skip-git-repo-check" in capabilities:
                command.append("--skip-git-repo-check")
            else:
                skipped_flags.append("--skip-git-repo-check")
        if self.options.codex_model:
            command.extend(["--model", self.options.codex_model])
        command.extend(self.options.codex_extra_args)
        if resume_id:
            command.append(resume_id)
        command.append(prompt)
        request.executor_metadata["codex_exec_capabilities"] = {
            "checked": self.options.codex_capability_check,
            "supported_flags": sorted(capabilities),
            "skipped_flags": skipped_flags,
            "output_flag": output_flag,
        }
        return command

    def _repair_stage_output(
        self,
        *,
        request: StageExecutionRequest,
        previous_output: str,
        error: Exception,
    ) -> StageResultEnvelope:
        current_output = previous_output
        current_error: Exception = error
        last_source = str(request.result_path)
        max_attempts = max(0, self.options.max_output_repair_attempts)
        for attempt in range(1, max_attempts + 1):
            _increment_model_output_format_stats(request=request, repair_attempt_count=1)
            repair_path = request.result_path.with_name(
                f"{request.result_path.stem}-repair-{attempt}{request.result_path.suffix}"
            )
            repair_prompt = _build_output_repair_prompt(
                request=request,
                error=str(current_error),
                previous_output=current_output,
            )
            if request.prompt_path is not None:
                repair_prompt_path = request.prompt_path.with_name(
                    f"{request.prompt_path.stem}-repair-{attempt}{request.prompt_path.suffix}"
                )
                repair_prompt_path.write_text(repair_prompt)

            completed = self._run_codex(request, prompt=repair_prompt, output_path=repair_path)
            stdout = _coerce_stream_text(completed.stdout)
            stderr = _coerce_stream_text(completed.stderr)
            existing_stdout = request.stdout_path.read_text() if request.stdout_path and request.stdout_path.exists() else ""
            existing_stderr = request.stderr_path.read_text() if request.stderr_path and request.stderr_path.exists() else ""
            _write_stage_run_streams(
                request,
                stdout=(existing_stdout + f"\n\n[output repair {attempt} stdout]\n" + stdout).strip(),
                stderr=(existing_stderr + f"\n\n[output repair {attempt} stderr]\n" + stderr).strip(),
            )
            if completed.returncode != 0 and not repair_path.exists():
                current_error = StagePayloadProtocolError(
                    f"Stage output protocol repair attempt {attempt} failed before producing a result: {stderr or stdout}"
                )
                last_source = str(repair_path)
                continue
            if not repair_path.exists():
                current_error = StagePayloadProtocolError(
                    f"Stage output protocol repair attempt {attempt} completed without writing a result file."
                )
                last_source = str(repair_path)
                continue
            current_output = repair_path.read_text()
            last_source = str(repair_path)
            try:
                repaired = _parse_stage_result_json_text(request=request, value=current_output, source=str(repair_path))
                _record_stage_status_metadata(request, result_parse_status="repaired")
                _increment_model_output_format_stats(request=request, repair_success_count=1)
                return repaired
            except StagePayloadProtocolError as repair_error:
                _record_stage_status_metadata(request, result_parse_status="protocol_error")
                _increment_model_output_format_stats(request=request, **_parse_protocol_error_stats(repair_error))
                current_error = StagePayloadProtocolError(
                    f"Stage output protocol repair attempt {attempt} failed: {repair_error}. Original error: {error}"
                )

        return _invalid_stage_payload_result(
            request=request,
            value=current_output,
            source=last_source,
            error=StagePayloadProtocolError(
                f"Stage output protocol repair failed after {max_attempts} attempt(s): {current_error}"
            ),
        )


def _create_driver_session(store: StateStore, message: str, *, interactive: bool = False):
    intake = parse_intake_message(message)
    if not intake.request:
        raise RuntimeDriverError("Unable to extract a workflow request from --message.")
    return store.create_session(
        intake.request,
        raw_message=message,
        contract=intake.contract,
        runtime_mode="runtime_driver_interactive" if interactive else "runtime_driver",
        initiator="human",
    )


def _ensure_interactive_runtime_mode(*, store: StateStore, session_id: str) -> None:
    session = store.load_session(session_id)
    summary = store.load_workflow_summary(session_id)
    if summary.runtime_mode == "runtime_driver_interactive":
        return
    store.save_workflow_summary(session, replace(summary, runtime_mode="runtime_driver_interactive"))


def _handle_wait_state(
    *,
    repo_root: Path,
    store: StateStore,
    summary: WorkflowSummary,
    auto_advance_intermediate: bool,
) -> tuple[str, str] | None:
    del repo_root
    if summary.current_state == "WaitForProductDefinitionApproval":
        if summary.runtime_mode == "runtime_driver_interactive":
            return ("waiting_human", "approve|rework|reject")
        return ("waiting_human", "approve")
    if summary.current_state == "WaitForTechnicalDesignApproval":
        return ("waiting_human", "approve|rework|reject")
    if summary.current_state == "WaitForHumanDecision":
        return ("waiting_human", "approve|no-go|rework")
    if summary.current_state == "Blocked":
        return ("blocked", "inspect gate_reason and route rework")
    return None


def _apply_human_decision(*, store: StateStore, summary: WorkflowSummary, decision: str) -> None:
    session = store.load_session(summary.session_id)
    updated = StageMachine().apply_human_decision(summary=summary, decision=decision)
    store.save_workflow_summary(session, updated)
    store.set_human_decision(summary.session_id, updated.human_decision)
    store.record_event(
        summary.session_id,
        kind="workflow_state_changed",
        stage=updated.current_stage,
        state=updated.current_state,
        actor="runtime-driver",
        status=updated.human_decision,
        message=f"Runtime driver applied human decision: {decision}.",
    )


def _capture_worktree_snapshot(repo_root: Path, *, excluded_roots: list[Path] | None = None) -> dict[str, Any]:
    probe = _run_git(repo_root, ["rev-parse", "--is-inside-work-tree"])
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        reason = (probe.stderr or probe.stdout or "not a git worktree").strip()
        return {"available": False, "reason": reason}

    status = _run_git(repo_root, ["status", "--short", "--untracked-files=all"])
    if status.returncode != 0:
        reason = (status.stderr or status.stdout or "git status failed").strip()
        return {"available": False, "reason": reason}

    excluded_paths = _repo_relative_excluded_paths(repo_root, excluded_roots or [])
    entries: dict[str, dict[str, str]] = {}
    status_lines: list[str] = []
    for raw_line in status.stdout.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        path = _path_from_git_status_line(line)
        if not path or _is_excluded_repo_path(path, excluded_paths):
            continue
        status_code = line[:2] if len(line) >= 2 else line.strip()
        entry = {
            "path": path,
            "status": status_code,
            "status_line": line,
            "fingerprint": _worktree_file_fingerprint(repo_root / path),
        }
        entries[path] = entry
        status_lines.append(line)

    return {
        "available": True,
        "dirty_count": len(entries),
        "status_lines": status_lines,
        "entries": entries,
    }


def _summarize_worktree_changes(
    *,
    repo_root: Path,
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    if not before.get("available") or not after.get("available"):
        reasons = []
        if not before.get("available"):
            reasons.append(f"before: {before.get('reason', 'unavailable')}")
        if not after.get("available"):
            reasons.append(f"after: {after.get('reason', 'unavailable')}")
        return {
            "available": False,
            "reason": "; ".join(reasons),
            "before_dirty_count": before.get("dirty_count", 0),
            "after_dirty_count": after.get("dirty_count", 0),
            "changed_files": [],
            "changed_file_paths": [],
            "status_lines": [],
            "diff_stat": "",
        }

    before_entries = before.get("entries", {}) if isinstance(before.get("entries"), dict) else {}
    after_entries = after.get("entries", {}) if isinstance(after.get("entries"), dict) else {}
    changed_files: list[dict[str, Any]] = []
    for path in sorted(set(before_entries) | set(after_entries)):
        before_entry = before_entries.get(path)
        after_entry = after_entries.get(path)
        if _worktree_entry_signature(before_entry) == _worktree_entry_signature(after_entry):
            continue
        change_type = _worktree_change_type(before_entry, after_entry)
        changed_files.append(
            {
                "path": path,
                "status": str(after_entry.get("status", "clean")) if isinstance(after_entry, dict) else "clean",
                "status_line": (
                    str(after_entry.get("status_line", f"clean {path}"))
                    if isinstance(after_entry, dict)
                    else f"clean {path}"
                ),
                "preexisting_dirty": before_entry is not None,
                "change_type": change_type,
            }
        )

    diff_paths = [
        item["path"]
        for item in changed_files
        if item.get("status") != "clean" and not str(item.get("status", "")).startswith("??")
    ]
    return {
        "available": True,
        "before_dirty_count": before.get("dirty_count", 0),
        "after_dirty_count": after.get("dirty_count", 0),
        "changed_files": changed_files,
        "changed_file_paths": [str(item["path"]) for item in changed_files],
        "status_lines": [str(item["status_line"]) for item in changed_files],
        "diff_stat": _worktree_diff_stat(repo_root, diff_paths),
    }


def _run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["git", *args], 1, stdout="", stderr=str(exc))


def _repo_relative_excluded_paths(repo_root: Path, excluded_roots: list[Path]) -> set[str]:
    repo = repo_root.resolve()
    paths: set[str] = set()
    for root in excluded_roots:
        try:
            relative = root.resolve().relative_to(repo)
        except ValueError:
            continue
        value = relative.as_posix().rstrip("/")
        if value and value != ".":
            paths.add(value)
    return paths


def _is_excluded_repo_path(path: str, excluded_paths: set[str]) -> bool:
    normalized = path.rstrip("/")
    return any(normalized == excluded or normalized.startswith(f"{excluded}/") for excluded in excluded_paths)


def _path_from_git_status_line(line: str) -> str:
    path = line[3:] if len(line) >= 3 else line.strip()
    if " -> " in path:
        path = path.rsplit(" -> ", 1)[-1]
    if len(path) >= 2 and path[0] == path[-1] == '"':
        path = path[1:-1]
    return path.strip()


def _worktree_file_fingerprint(path: Path) -> str:
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return "missing"
    if path.is_symlink():
        return f"symlink:{os.readlink(path)}"
    if not path.is_file():
        return f"special:{stat.st_mode}:{stat.st_size}:{stat.st_mtime_ns}"
    if stat.st_size > 10 * 1024 * 1024:
        return f"large-file:{stat.st_size}:{stat.st_mtime_ns}"
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _worktree_entry_signature(entry: object) -> tuple[str, str] | None:
    if not isinstance(entry, dict):
        return None
    return (str(entry.get("status", "")), str(entry.get("fingerprint", "")))


def _worktree_change_type(before_entry: object, after_entry: object) -> str:
    if before_entry is None and after_entry is not None:
        return "new_dirty_file"
    if before_entry is not None and after_entry is None:
        return "became_clean"
    before_status = str(before_entry.get("status", "")) if isinstance(before_entry, dict) else ""
    after_status = str(after_entry.get("status", "")) if isinstance(after_entry, dict) else ""
    if before_status != after_status:
        return "status_changed"
    return "content_changed"


def _worktree_diff_stat(repo_root: Path, paths: list[str]) -> str:
    if not paths:
        return ""
    unique_paths = sorted(set(paths))
    unstaged = _run_git(repo_root, ["diff", "--stat", "--", *unique_paths])
    staged = _run_git(repo_root, ["diff", "--cached", "--stat", "--", *unique_paths])
    parts: list[str] = []
    if unstaged.returncode == 0 and unstaged.stdout.strip():
        parts.append("未暂存改动:\n" + unstaged.stdout.strip())
    if staged.returncode == 0 and staged.stdout.strip():
        parts.append("已暂存改动:\n" + staged.stdout.strip())
    return "\n".join(parts)


def _execute_stage(
    *,
    repo_root: Path,
    store: StateStore,
    session_id: str,
    stage: str,
    executor: StageExecutor,
    options: RuntimeDriverOptions,
) -> GateResult:
    trace_steps: list[dict[str, Any]] = []
    contract = build_stage_contract(repo_root=repo_root, state_store=store, session_id=session_id, stage=stage)
    _add_runtime_trace_step(
        trace_steps,
        step="contract_built",
        details={"contract_id": contract.contract_id, "required_outputs": list(contract.required_outputs)},
    )
    context = build_stage_execution_context(
        repo_root=repo_root,
        state_store=store,
        session_id=session_id,
        stage=stage,
        contract=contract,
    )
    context_path = store.save_execution_context(context)
    _add_runtime_trace_step(
        trace_steps,
        step="execution_context_built",
        details={"context_id": context.context_id, "context_path": str(context_path)},
    )
    session = store.load_session(session_id)
    summary = store.load_workflow_summary(session_id)
    store.save_workflow_summary(
        session,
        replace(summary, artifact_paths={**summary.artifact_paths, "execution_context": str(context_path)}),
    )
    run = store.create_stage_run(
        session_id=session_id,
        stage=stage,
        contract_id=contract.contract_id,
        required_outputs=list(contract.required_outputs),
        required_evidence=list(contract.evidence_requirements),
        worker=executor.name,
    )
    stage_result_path = store.stage_result_path(session, stage, run.attempt)
    result_bundle_path = store.command_stdout_path(session, stage, run.attempt).with_name(
        f"{stage.lower()}-result-bundle.json"
    )
    prompt_path = store.stage_prompt_bundle_path(session, stage, run.attempt) if options.trace_prompts else None
    skill_asset_root = store.skill_asset_root(session, stage, run.attempt)
    stage_skills = list(options.enabled_skills_by_stage.get(stage, []))
    _install_runtime_sandbox_skills(stage_skills, skill_asset_root)
    skill_trace = {
        "skill_count": len(stage_skills),
        "skill_asset_root": str(skill_asset_root),
        "included_in_prompt": executor.name == "codex-exec",
        "skills": [
            _skill_trace_entry(skill, skill_asset_root, included_in_prompt=executor.name == "codex-exec")
            for skill in stage_skills
        ],
    }
    common_artifact_paths = {"stage_result": str(stage_result_path)}
    if prompt_path is not None:
        common_artifact_paths["prompt_bundle"] = str(prompt_path)
    run = store.update_stage_run(run, artifact_paths=common_artifact_paths)
    _add_runtime_trace_step(
        trace_steps,
        step="stage_run_acquired",
        details={
            "run_id": run.run_id,
            "worker": executor.name,
            "skill_injection": skill_trace,
        },
    )
    _write_runtime_trace(
        store=store,
        session_id=session_id,
        run_id=run.run_id,
        stage=stage,
        trace_steps=trace_steps,
    )
    request = StageExecutionRequest(
        repo_root=repo_root,
        state_store=store,
        session_id=session_id,
        run_id=run.run_id,
        contract=contract,
        context=context,
        contract_path=store.stage_contract_path(session, stage, run.attempt),
        context_path=context_path,
        result_path=result_bundle_path,
        output_schema_path=store.session_output_schema_path(session),
        prompt_path=prompt_path,
        skill_asset_root=skill_asset_root,
        stdout_path=store.command_stdout_path(session, stage, run.attempt),
        stderr_path=store.command_stderr_path(session, stage, run.attempt),
        skills=stage_skills,
        executor_env_config_path=executor_env_config_path(store.root),
    )
    request.contract_path.parent.mkdir(parents=True, exist_ok=True)
    request.contract_path.write_text(json.dumps(contract.to_dict(), ensure_ascii=False, indent=2))
    schema_path = request.output_schema_path
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(json.dumps(_stage_result_schema(contract), indent=2))
    prompt_text = _build_codex_prompt(request)
    if request.prompt_path is not None:
        request.prompt_path.parent.mkdir(parents=True, exist_ok=True)
        request.prompt_path.write_text(prompt_text)
    store.record_event(
        session_id,
        kind="runtime_driver_stage_started",
        stage=stage,
        state=stage,
        actor="runtime-driver",
        status="started",
        message=f"Runtime driver started {stage} with executor {executor.name}.",
        details={
            "run_id": run.run_id,
            "contract_path": str(request.contract_path),
            "context_path": str(request.context_path),
            "result_path": str(request.result_path),
            "prompt_path": str(request.prompt_path),
            "stage_result_path": str(stage_result_path),
            "skill_count": len(stage_skills),
            "attempt": run.attempt,
            "stage_run_id": run.run_id,
            "actionable_feedback_count": len(context.actionable_findings),
            "actionable_feedback": [finding.to_dict() for finding in context.actionable_findings],
        },
    )
    worktree_snapshot_before = _capture_worktree_snapshot(
        repo_root,
        excluded_roots=[store.root / "_runtime"],
    )
    _add_runtime_trace_step(
        trace_steps,
        step="executor_started",
        details={
            "attempt": run.attempt,
            "stage_run_id": run.run_id,
            "executor": executor.name,
            "actionable_feedback_count": len(context.actionable_findings),
            "actionable_feedback": [finding.to_dict() for finding in context.actionable_findings],
        },
    )
    _write_runtime_trace(
        store=store,
        session_id=session_id,
        run_id=run.run_id,
        stage=stage,
        trace_steps=trace_steps,
    )
    try:
        result = executor.execute(request)
    except KeyboardInterrupt:
        _mark_stage_run_interrupted(
            store=store,
            run=run,
            stage=stage,
            trace_steps=trace_steps,
            reason="executor interrupted",
        )
        raise
    except BaseException as exc:
        _mark_stage_run_interrupted(
            store=store,
            run=run,
            stage=stage,
            trace_steps=trace_steps,
            reason=f"executor interrupted: {exc}",
        )
        raise
    worktree_snapshot_after = _capture_worktree_snapshot(
        repo_root,
        excluded_roots=[store.root / "_runtime"],
    )
    worktree_changes = _summarize_worktree_changes(
        repo_root=repo_root,
        before=worktree_snapshot_before,
        after=worktree_snapshot_after,
    )
    _record_stage_status_metadata(
        request,
        result_parse_status=request.executor_metadata.get("status", {}).get("result_parse_status", "parsed"),
    )
    _add_runtime_trace_step(
        trace_steps,
        step="executor_completed",
        status="ok" if result.status != "blocked" else "blocked",
        details={
            "attempt": run.attempt,
            "stage_run_id": run.run_id,
            "executor": executor.name,
            "result_status": result.status,
            "executor_status": result.executor_status or request.executor_metadata.get("status", {}).get("executor_status", ""),
            "executor_exit_code": result.executor_exit_code,
            "result_parse_status": result.result_parse_status or request.executor_metadata.get("status", {}).get("result_parse_status", ""),
            "executor_metadata": dict(request.executor_metadata),
        },
    )
    _add_runtime_trace_step(
        trace_steps,
        step="worktree_changes_detected",
        details=worktree_changes,
    )
    store.record_event(
        session_id,
        kind="runtime_driver_worktree_changes_detected",
        stage=stage,
        state=stage,
        actor="runtime-driver",
        status="ok",
        message=f"Runtime driver detected {len(worktree_changes.get('changed_files', []))} worktree change(s).",
        details=worktree_changes,
    )
    _write_runtime_trace(
        store=store,
        session_id=session_id,
        run_id=run.run_id,
        stage=stage,
        trace_steps=trace_steps,
    )
    _apply_executor_metadata_to_result(request=request, result=result)
    conflict_gate = _executor_result_conflict_gate(result)
    try:
        submitted = store.submit_stage_run_result(run.run_id, result)
    except StageRunStateError as exc:
        failed_gate = GateResult(
            status="BLOCKED",
            reason=f"Executor produced an invalid stage result: {exc}",
            findings=list(result.findings),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
        _add_runtime_trace_step(
            trace_steps,
            step="result_submitted",
            status="failed",
            details={"error": str(exc)},
        )
        _add_runtime_trace_step(
            trace_steps,
            step="gate_evaluated",
            status="blocked",
            details={"gate_status": failed_gate.status, "gate_reason": failed_gate.reason},
        )
        _write_runtime_trace(
            store=store,
            session_id=session_id,
            run_id=run.run_id,
            stage=stage,
            trace_steps=trace_steps,
        )
        latest_summary = store.load_workflow_summary(session_id)
        store.save_workflow_summary(session, replace(latest_summary, blocked_reason=failed_gate.reason))
        store.update_stage_run(
            run,
            state="BLOCKED",
            gate_result=failed_gate,
            blocked_reason=failed_gate.reason,
            artifact_paths=common_artifact_paths,
        )
        return failed_gate
    _add_runtime_trace_step(
        trace_steps,
        step="result_submitted",
        details={"stage_result_path": submitted.candidate_bundle_path},
    )
    _write_runtime_trace(
        store=store,
        session_id=session_id,
        run_id=run.run_id,
        stage=stage,
        trace_steps=trace_steps,
    )
    verifying_run = store.update_stage_run(submitted, state="VERIFYING")
    if conflict_gate is not None:
        gate_result = conflict_gate
        normalized_result = result
    else:
        gate_result, normalized_result = _evaluate_stage_result(
            repo_root=repo_root,
            store=store,
            summary=store.load_workflow_summary(session_id),
            contract=contract,
            result=result,
            options=options,
        )
    _record_gate_model_output_format_stats(request=request, gate_result=gate_result)
    _record_stage_status_metadata(request, gate_status=gate_result.status)
    _add_runtime_trace_step(
        trace_steps,
        step="gate_evaluated",
        status="ok" if gate_result.status == "PASSED" else gate_result.status.lower(),
        details={
            "attempt": run.attempt,
            "stage_run_id": run.run_id,
            "gate_status": gate_result.status,
            "gate_reason": gate_result.reason,
        },
    )
    _write_runtime_trace(
        store=store,
        session_id=session_id,
        run_id=run.run_id,
        stage=stage,
        trace_steps=trace_steps,
    )
    if gate_result.status == "PASSED":
        stage_record = store.record_stage_result(session_id, normalized_result)
        latest_summary = store.load_workflow_summary(session_id)
        updated_summary = StageMachine().advance(summary=latest_summary, stage_result=normalized_result)
        _record_stage_status_metadata(request, state_transition_status="advanced")
        _add_runtime_trace_step(
            trace_steps,
            step="state_advanced",
            details={
                "from_state": latest_summary.current_state,
                "to_state": updated_summary.current_state,
                "to_stage": updated_summary.current_stage,
            },
        )
        _write_runtime_trace(
            store=store,
            session_id=session_id,
            run_id=run.run_id,
            stage=stage,
            trace_steps=trace_steps,
        )
        trace_gate = _validate_runtime_trace(trace_steps, required_steps=REQUIRED_PASS_TRACE_STEPS)
        if trace_gate.status != "PASSED":
            store.update_stage_run(
                verifying_run,
                state="BLOCKED",
                gate_result=trace_gate,
                blocked_reason=trace_gate.reason,
                artifact_paths=common_artifact_paths,
            )
            return trace_gate
        artifact_key = artifact_key_for(normalized_result.stage)
        updated_summary.artifact_paths[artifact_key] = str(stage_record.artifact_path)
        updated_summary.artifact_paths.update(stage_record.supplemental_artifact_paths)
        store.save_workflow_summary(session, updated_summary)
        store.update_stage_run(
            verifying_run,
            state="PASSED",
            gate_result=gate_result,
            blocked_reason="",
            artifact_paths={
                artifact_key: str(stage_record.artifact_path),
                **stage_record.supplemental_artifact_paths,
                **common_artifact_paths,
            },
        )
        for finding in normalized_result.findings:
            store.apply_learning(finding)
        return gate_result

    latest_summary = store.load_workflow_summary(session_id)
    blocked_reason = gate_result.reason if gate_result.status == "BLOCKED" else ""
    store.save_workflow_summary(session, replace(latest_summary, blocked_reason=blocked_reason))
    store.update_stage_run(
        verifying_run,
        state=gate_result.status,
        gate_result=gate_result,
        blocked_reason=blocked_reason,
        artifact_paths=common_artifact_paths,
    )
    return gate_result


def _evaluate_stage_result(
    *,
    repo_root: Path,
    store: StateStore,
    summary: WorkflowSummary,
    contract: StageContract,
    result: StageResultEnvelope,
    options: RuntimeDriverOptions,
) -> tuple[GateResult, StageResultEnvelope]:
    del repo_root
    if options.judge == "off":
        return evaluate_candidate(
            session=store.load_session(result.session_id),
            contract=contract,
            result=result,
            acceptance_contract=store.load_acceptance_contract(result.session_id),
        )

    judge = (
        OpenAISandboxJudge(
            model=options.model,
            docker_image=options.docker_image,
            api_key=options.openai_api_key,
            base_url=options.openai_base_url,
            proxy_url=options.openai_proxy_url,
            user_agent=options.openai_user_agent,
            oa_header=options.openai_oa or options.openai_user_agent,
        )
        if options.judge == "openai-sandbox"
        else NoopJudge()
    )
    try:
        evaluation = GateEvaluator(judge=judge).evaluate(
            session=store.load_session(result.session_id),
            policy=_policy_for_result(result),
            contract=contract,
            result=result,
            original_request_summary=store.load_session(result.session_id).request,
            approved_product_definition_summary=_approved_product_definition_summary(summary=summary, result=result),
            approved_acceptance_matrix=[],
        )
    except OpenAISandboxJudgeUnavailable as exc:
        raise RuntimeDriverError(str(exc)) from exc
    return _gate_result_from_evaluation(evaluation), evaluation.result


def _policy_for_result(result: StageResultEnvelope):
    return default_policy_registry().get(result.stage)


def _gate_result_from_evaluation(evaluation) -> GateResult:
    decision = evaluation.decision
    if decision.outcome == "pass":
        status = "PASSED"
    elif decision.outcome == "blocked":
        status = "BLOCKED"
    else:
        status = "FAILED"
    return GateResult(
        status=status,
        reason=decision.reason,
        missing_outputs=list(decision.missing_outputs),
        missing_evidence=list(decision.missing_evidence),
        findings=list(decision.findings),
        checked_at=evaluation.hard_gate_result.checked_at,
    )


def _approved_product_definition_summary(*, summary: WorkflowSummary, result: StageResultEnvelope) -> str:
    if result.stage == "ProductDefinition" and result.artifact_name == artifact_name_for_stage("ProductDefinition"):
        return result.artifact_content[:4000]
    product_definition_path = summary.artifact_paths.get("product_definition")
    if product_definition_path and Path(product_definition_path).exists():
        return Path(product_definition_path).read_text()[:4000]
    return ""


def _expected_submission_stage(summary: WorkflowSummary) -> str | None:
    if summary.current_state == "Intake":
        return "Route"
    if summary.current_state in EXECUTABLE_STATES:
        return summary.current_state
    return None


def _record_provider_smoke_metadata(*, store: StateStore, session, options: RuntimeDriverOptions) -> None:
    metadata = {
        "executor": options.executor,
        "model": options.codex_model or options.model,
        "smoke_check_enabled": bool(options.provider_smoke_check),
    }
    if options.provider_smoke_check:
        command = options.provider_smoke_command or "codex exec --skip-git-repo-check --sandbox read-only --model {model} reply ok"
        rendered = command.format(model=metadata["model"])
        try:
            completed = subprocess.run(rendered, shell=True, capture_output=True, text=True, timeout=30, check=False)
            metadata.update({
                "smoke_status": "passed" if completed.returncode == 0 else "failed",
                "smoke_exit_code": completed.returncode,
                "smoke_stdout_preview": (completed.stdout or "")[:500],
                "smoke_stderr_preview": (completed.stderr or "")[:500],
            })
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            metadata.update({"smoke_status": "error", "smoke_error": str(exc)})
    try:
        summary = store.load_workflow_summary(session.session_id)
        store.save_workflow_summary(session, replace(summary, provider_model_metadata=metadata))
    except Exception:
        return

def _mark_stage_run_interrupted(
    *,
    store: StateStore,
    run,
    stage: str,
    trace_steps: list[dict[str, Any]],
    reason: str,
) -> None:
    _add_runtime_trace_step(trace_steps, step="executor_interrupted", status="blocked", details={"reason": reason})
    try:
        store.update_stage_run(
            run,
            state="BLOCKED",
            gate_result=GateResult(
                status="BLOCKED",
                reason=reason,
                checked_at=datetime.now(timezone.utc).isoformat(),
            ),
            blocked_reason=reason,
            steps=trace_steps,
        )
    except Exception:
        return



def _result_from_summary(
    *,
    store: StateStore,
    session_id: str,
    status: str,
    next_action: str = "",
    stage_run_count: int = 0,
    gate_status: str = "",
    gate_reason: str = "",
) -> RuntimeDriverResult:
    session = store.load_session(session_id)
    summary = store.load_workflow_summary(session_id)
    return RuntimeDriverResult(
        session_id=session_id,
        artifact_dir=session.artifact_dir,
        summary_path=store.workflow_summary_path(session_id),
        status=status,
        current_state=summary.current_state,
        current_stage=summary.current_stage,
        acceptance_status=summary.acceptance_status,
        human_decision=summary.human_decision,
        next_action=next_action,
        stage_run_count=stage_run_count,
        gate_status=gate_status,
        gate_reason=gate_reason,
    )


def _default_evidence(stage: str, *, artifact_name: str | None = None) -> list[EvidenceItem]:
    return {
        "Route": [
            EvidenceItem(
                name="route_classification",
                kind="artifact",
                summary="Route classified the request against five-layer responsibilities and red lines.",
                producer="runtime-driver",
            ),
        ],
        "ProductDefinition": [
            EvidenceItem(
                name="l1_classification",
                kind="artifact",
                summary="ProductDefinition separated L1 candidates from non-L1 task content.",
                producer="runtime-driver",
            )
        ],
        "ProjectRuntime": [
            EvidenceItem(
                name="project_landing_review",
                kind="report",
                summary="ProjectRuntime checked project landing defaults and L3 deltas.",
                producer="runtime-driver",
            )
        ],
        "TechnicalDesign": [
            EvidenceItem(
                name="technical_design_plan",
                kind="report",
                summary="TechnicalDesign identified implementation steps and verification commands.",
                producer="runtime-driver",
            )
        ],
        "Implementation": [
            EvidenceItem(
                name="self_code_review",
                kind="report",
                summary="Dry-run Implementation reviewed the generated implementation handoff.",
                producer="runtime-driver",
            ),
            EvidenceItem(
                name="self_verification",
                kind="command",
                summary="Implementation self-verification completed.",
                command="agent-team runtime dry-run",
                exit_code=0,
                producer="runtime-driver",
            ),
        ],
        "Verification": [
            EvidenceItem(
                name="independent_verification",
                kind="command",
                summary="Verification independently reran critical checks.",
                command="agent-team runtime dry-run",
                exit_code=0,
                producer="runtime-driver",
            )
        ],
        "GovernanceReview": [
            EvidenceItem(
                name="layer_governance_review",
                kind="report",
                summary="GovernanceReview checked layer boundaries, evidence, and writeback obligations.",
                producer="runtime-driver",
            )
        ],
        "Acceptance": [
            EvidenceItem(
                name="product_and_governance_validation",
                kind="report",
                summary="Acceptance validated product result plus governance evidence.",
                producer="runtime-driver",
            )
        ],
        "SessionHandoff": [
            EvidenceItem(
                name="local_control_handoff",
                kind="artifact",
                summary="SessionHandoff preserved local-control continuity and unresolved decisions.",
                producer="runtime-driver",
            )
        ],
    }[stage]


def _dry_run_artifact_content(stage: str, context: StageExecutionContext, *, artifact_name: str | None = None) -> str:
    if stage == "Route":
        return (
            "{\n"
            '  "request": ' + json.dumps(context.original_request_summary, ensure_ascii=False) + ",\n"
            '  "affected_layers": ["L1", "L2", "L3", "L4", "L5"],\n'
            '  "required_stages": ["ProductDefinition", "ProjectRuntime", "TechnicalDesign", '
            '"Implementation", "Verification", "GovernanceReview", "Acceptance", "SessionHandoff"],\n'
            '  "red_lines": ["lower_layers_must_not_rewrite_upper_layer_truth", '
            '"do_not_promote_l5_or_research_to_formal_truth"],\n'
            '  "status": "dry_run_classified"\n'
            "}\n"
        )
    if stage == "ProductDefinition":
        alignment_summary = _stage_alignment_update_summary(context.actionable_findings)
        alignment_section = (
            "\n## 阶段对齐更新\n"
            f"{alignment_summary}\n"
            "这些澄清或返工意见必须被吸收到本次重新生成的正式产品定义 delta 中；"
            "非 L1 内容应下沉到对应层，不得作为旁路备注继续传递。\n"
            if alignment_summary
            else ""
        )
        return (
            "# Product Definition Delta\n\n"
            f"## 原始需求\n{context.original_request_summary}\n\n"
            "## 理解复述\n"
            "- 本阶段先复述需求意图、成功标准和非目标；若缺少 L1 决策，应先提出澄清问题而不是猜测。\n\n"
            f"{alignment_section}"
            "## L1 候选\n"
            "- 待人工确认的稳定产品语义、核心对象、职责边界和长期规则。\n\n"
            "## 非 L1 内容\n"
            "- 交付范围、实现提示、项目落地、治理规则和本地现场材料不得写入正式产品定义。\n\n"
            "## 冲突规则\n"
            "- 下层只能报告 delta 或 drift，不能反向改写 L1。\n"
        )
    if stage == "ProjectRuntime":
        return (
            "# Project Landing Delta\n\n"
            "## L3 默认做法\n"
            "- 记录本项目如何承载、组织、启动、打包和默认运行该产品。\n\n"
            "## 不属于 L3\n"
            "- 不重写 L1 产品语义。\n"
            "- 不伪装成 L4 共享协作治理规则。\n"
        )
    if stage == "TechnicalDesign":
        return (
            "- Write technical-design.md content in Simplified Chinese. Do not edit source code in this stage.\n"
            "- If a material design choice is unresolved, return status `blocked` with focused questions in artifact_content.\n"
            "- If understood, start with `## 方案理解复述`: approved requirement, chosen approach, scope, non-goals, and verification target.\n"
            "- Include implementation approach, affected files/interfaces, verification plan, risks, and rollback.\n"
        )
    if stage == "Implementation":
        return (
            "- Write artifact_content as implementation.md in Simplified Chinese.\n"
            "- Treat approved_technical_design_content as the implementation source of truth.\n"
            "- Implement the approved technical design instead of replacing it with a new design.\n"
            "- If the approved technical design is missing, contradictory, or too ambiguous to implement safely, return status `blocked` with focused questions in artifact_content.\n"
            "- Keep changes scoped to the approved design.\n"
            "- For server-side changes, run or prepare end-to-end verification from API/request to persisted data; if database access or query confirmation is needed, return status `blocked` with the exact evidence needed from the user.\n"
            "- For frontend mini-program changes that cannot be launched locally, state the limitation and run available static, build, or unit checks instead of claiming runtime validation.\n"
            "- The implementation report must name changed files, actual behavior changes, self-review results, commands run, skipped checks, and unresolved risks in Chinese."
        )
    if stage == "Verification":
        return (
            "- Write artifact_content as verification-report.md in Simplified Chinese. Independently verify Implementation evidence against L1, L2, L3, and the technical design.\n"
            "- For server-side changes, verify the full path from API/request to persisted data; include command/request, response, and data evidence when available.\n"
            "- If database evidence requires user-provided access, query results, or approval, return status `blocked` with the exact query/evidence request.\n"
            "- For frontend mini-program changes that cannot be launched locally, state that limitation and verify with available static, build, or unit checks only."
        )
    if stage == "GovernanceReview":
        return (
            "# Governance Review\n\n"
            "## Layer Boundary Result\n"
            "- No L5 or research material was promoted to formal truth in dry-run mode.\n"
            "- Lower-layer artifacts report deltas instead of rewriting upper-layer truth.\n\n"
            "## Writeback Obligations\n"
            "- Accepted L1/L3/L4 deltas require explicit canonical writeback targets before merge.\n"
        )
    if stage == "Acceptance":
        return (
        "# Acceptance Report\n\n"
        "## Recommendation\nrecommended_go\n\n"
        "## Product-Level Validation\n"
        "- Runtime driver preserved five-layer gates and governance evidence.\n"
        )
    return (
        "# Session Handoff\n\n"
        "## Current State\n"
        "- Five-layer dry-run completed through AI acceptance recommendation.\n\n"
        "## Next Action\n"
        "- Human Go/No-Go decision remains pending.\n\n"
        "## Local Control\n"
        "- Keep task/session evidence in L5; do not promote local notes to formal truth automatically.\n"
    )


def _dry_run_supplemental_artifacts(stage: str, context: StageExecutionContext) -> dict[str, str]:
    return {}


def _stage_environment(request: StageExecutionRequest) -> dict[str, str]:
    env = {
        "AGENT_TEAM_REPO_ROOT": str(request.repo_root),
        "AGENT_TEAM_SESSION_ID": request.session_id,
        "AGENT_TEAM_STAGE": request.contract.stage,
        "AGENT_TEAM_RUN_ID": request.run_id,
        "AGENT_TEAM_CONTRACT_PATH": str(request.contract_path),
        "AGENT_TEAM_CONTEXT_PATH": str(request.context_path),
        "AGENT_TEAM_RESULT_BUNDLE": str(request.result_path),
        "AGENT_TEAM_OUTPUT_SCHEMA": str(request.output_schema_path),
        "AGENT_TEAM_ARTIFACT_DIR": str(request.state_store.load_session(request.session_id).artifact_dir),
    }
    if request.prompt_path is not None:
        env["AGENT_TEAM_PROMPT_PATH"] = str(request.prompt_path)
    if request.skill_asset_root is not None:
        env["AGENT_TEAM_SKILL_ASSET_ROOT"] = str(request.skill_asset_root)
    if request.skills:
        env["AGENT_TEAM_ENABLED_SKILLS"] = ",".join(skill.name for skill in request.skills)
    return env


def _record_stage_status_metadata(
    request: StageExecutionRequest,
    *,
    executor_status: str = "",
    executor_exit_code: int | None = None,
    result_parse_status: str = "",
    gate_status: str = "",
    state_transition_status: str = "",
) -> None:
    status: dict[str, object] = dict(request.executor_metadata.get("status", {}))
    if executor_status:
        status["executor_status"] = executor_status
    if executor_exit_code is not None:
        status["executor_exit_code"] = executor_exit_code
    if result_parse_status:
        status["result_parse_status"] = result_parse_status
    if gate_status:
        status["gate_status"] = gate_status
    if state_transition_status:
        status["state_transition_status"] = state_transition_status
    if status:
        request.executor_metadata["status"] = status


def _executor_result_conflict_gate(result: StageResultEnvelope) -> GateResult | None:
    if result.dry_run:
        return None
    if result.executor_exit_code is None or result.executor_exit_code == 0:
        return None
    if result.status != "completed":
        return None
    reason = (
        "executor_result_conflict: executor exited with "
        f"{result.executor_exit_code} but stage_result.status is completed."
    )
    return GateResult(
        status="BLOCKED",
        reason=reason,
        findings=list(result.findings),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


def _apply_executor_metadata_to_result(*, request: StageExecutionRequest, result: StageResultEnvelope) -> None:
    status = request.executor_metadata.get("status", {})
    if not isinstance(status, dict):
        return
    if not result.executor_status and status.get("executor_status"):
        result.executor_status = str(status.get("executor_status"))
    if result.executor_exit_code is None and status.get("executor_exit_code") is not None:
        try:
            result.executor_exit_code = int(status.get("executor_exit_code"))
        except (TypeError, ValueError):
            pass
    if not result.result_parse_status and status.get("result_parse_status"):
        result.result_parse_status = str(status.get("result_parse_status"))


def _increment_model_output_format_stats(request: StageExecutionRequest, **increments: int) -> None:
    store = getattr(request, "state_store", None)
    if store is None:
        return
    nonzero = {key: int(value) for key, value in increments.items() if key in MODEL_OUTPUT_FORMAT_STAT_KEYS and int(value)}
    if not nonzero:
        return
    try:
        session = store.load_session(request.session_id)
        summary = store.load_workflow_summary(request.session_id)
    except Exception:
        return
    stats = {key: int(summary.model_output_format_stats.get(key, 0) or 0) for key in MODEL_OUTPUT_FORMAT_STAT_KEYS}
    for key, value in nonzero.items():
        stats[key] = stats.get(key, 0) + value
    store.save_workflow_summary(session, replace(summary, model_output_format_stats=stats))


def _parse_protocol_error_stats(error: Exception) -> dict[str, int]:
    message = str(error)
    stats: dict[str, int] = {}
    if "Invalid stage payload JSON" in message:
        stats["invalid_json_count"] = 1
    if "unsupported field" in message:
        stats["unsupported_field_count"] = 1
    if "runtime-controlled field" in message:
        stats["runtime_controlled_field_count"] = 1
    return stats


def _record_gate_model_output_format_stats(*, request: StageExecutionRequest, gate_result: GateResult) -> None:
    if gate_result.status not in {"FAILED", "BLOCKED"}:
        return
    stats: dict[str, int] = {}
    missing_base_names = [item for item in gate_result.missing_evidence if "." not in item]
    if missing_base_names:
        stats["missing_required_evidence_count"] = len(missing_base_names)
    if "derived key(s)" in gate_result.reason:
        stats["derived_evidence_key_count"] = gate_result.reason.count("derived key(s)")
    _increment_model_output_format_stats(request=request, **stats)

def _contract_artifact_name(contract: StageContract) -> str:
    required_outputs = list(getattr(contract, "required_outputs", []) or [])
    if required_outputs:
        return required_outputs[0]
    return artifact_name_for_stage(contract.stage)


def _blocked_result_from_process(
    *,
    request: StageExecutionRequest,
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int,
) -> StageResultEnvelope:
    stdout_text = _coerce_stream_text(stdout)
    stderr_text = _coerce_stream_text(stderr)
    return StageResultEnvelope(
        session_id=request.session_id,
        stage=request.contract.stage,
        status="blocked",
        artifact_name=_contract_artifact_name(request.contract),
        artifact_content=(
            f"# {request.contract.stage} Blocked\n\n"
            f"Command `{command}` exited with {exit_code} before producing a valid stage result.\n\n"
            "## stderr\n\n"
            f"```text\n{stderr_text.strip()[:4000]}\n```\n\n"
            "## stdout\n\n"
            f"```text\n{stdout_text.strip()[:4000]}\n```\n"
        ),
        contract_id=request.contract.contract_id,
        blocked_reason=f"Executor command failed with exit code {exit_code}.",
        evidence=[
            EvidenceItem(
                name="executor_failure",
                kind="command",
                summary=f"Executor command exited with {exit_code}.",
                command=command,
                exit_code=exit_code,
                producer="runtime-driver",
            )
        ],
    )


def _parse_stage_result_json_text(*, request: StageExecutionRequest, value: str, source: str) -> StageResultEnvelope:
    try:
        payload = json.loads(value)
        if not isinstance(payload, dict):
            raise TypeError("stage result payload must be a JSON object")
        return _stage_result_from_payload_dict(request=request, payload=payload)
    except Exception as exc:
        raise StagePayloadProtocolError(f"Invalid stage payload JSON from {source}: {exc}") from exc


def _stage_result_from_json_text(*, request: StageExecutionRequest, value: str, source: str) -> StageResultEnvelope:
    try:
        return _parse_stage_result_json_text(request=request, value=value, source=source)
    except StagePayloadProtocolError as exc:
        return _invalid_stage_payload_result(request=request, value=value, source=source, error=exc)


def _invalid_stage_payload_result(
    *,
    request: StageExecutionRequest,
    value: str,
    source: str,
    error: Exception,
) -> StageResultEnvelope:
    return StageResultEnvelope(
        session_id=request.session_id,
        stage=request.contract.stage,
        status="blocked",
        artifact_name=_contract_artifact_name(request.contract),
        artifact_content=(
            f"# {request.contract.stage} Blocked\n\n"
            f"Executor produced invalid stage payload JSON from {source}.\n\n"
            f"## Error\n\n```text\n{error}\n```\n\n"
            f"## Raw Output\n\n```text\n{value.strip()[:4000]}\n```\n"
        ),
        contract_id=request.contract.contract_id,
        blocked_reason=str(error),
        evidence=[
            EvidenceItem(
                name="executor_invalid_json",
                kind="artifact",
                summary=f"Runtime driver could not parse stage result JSON from {source}.",
                producer="runtime-driver",
            )
        ],
    )


def _stage_result_from_payload_dict(
    *,
    request: StageExecutionRequest,
    payload: dict[str, Any],
) -> StageResultEnvelope:
    return envelope_from_stage_payload(
        payload=payload,
        session_id=request.session_id,
        stage=request.contract.stage,
        contract_id=request.contract.contract_id,
        artifact_name=_contract_artifact_name(request.contract),
    )


def _build_output_repair_prompt(*, request: StageExecutionRequest, error: str, previous_output: str) -> str:
    required_evidence = list(getattr(request.contract, "evidence_requirements", []) or [])
    required_outputs = list(getattr(request.contract, "required_outputs", []) or [])
    allowed_fields = ", ".join(sorted(ALLOWED_STAGE_PAYLOAD_FIELDS))
    forbidden_fields = ", ".join(sorted(FORBIDDEN_STAGE_PAYLOAD_FIELDS))
    previous = previous_output.strip()[:12000]
    return (
        f"<agent_team_output_repair stage=\"{request.contract.stage}\">\n"
        "Your previous response was rejected by the runtime output parser.\n"
        "Do not continue the task, change product/design decisions, or add explanations.\n"
        "Repair only the JSON envelope while preserving the stage document content as much as possible.\n\n"
        "<output_rules>\n"
        "Return only valid JSON stage payload. Remove runtime-controlled fields.\n"
        "Keep the document in artifact_content.\n"
        "Use evidence_by_name for contract evidence: include each required evidence key exactly and fill its value object.\n"
        "Do not invent derived evidence keys; put sub-checks in metadata.checks or summary.\n"
        "</output_rules>\n\n"
        f"<error>{_xml_cdata(error)}</error>\n\n"
        f"<allowed_fields>{_xml_cdata(allowed_fields)}</allowed_fields>\n"
        f"<forbidden_fields>{_xml_cdata(forbidden_fields)}</forbidden_fields>\n"
        f"<required_outputs>{_xml_cdata(json.dumps(required_outputs, ensure_ascii=False))}</required_outputs>\n"
        f"<required_evidence>{_xml_cdata(json.dumps(required_evidence, ensure_ascii=False))}</required_evidence>\n\n"
        f"<previous_output>{_xml_cdata(previous)}</previous_output>\n"
        "</agent_team_output_repair>\n"
    )


def _build_codex_prompt(request: StageExecutionRequest) -> str:
    contract_json = json.dumps(request.contract.to_dict(), ensure_ascii=False, indent=2)
    context_json = json.dumps(request.context.to_dict(), ensure_ascii=False, indent=2)
    format_instructions = _stage_artifact_format_instructions(
        request.contract.stage,
        required_outputs=request.contract.required_outputs,
    )
    stage_alignment_updates = _stage_alignment_update_summary(request.context.actionable_findings)
    skill_text = skill_injection_text(
        request.skills,
        asset_root=str(request.skill_asset_root) if request.skill_asset_root is not None else ".agent-team/skills",
    )
    skill_section = f"{skill_text}\n\n" if skill_text else ""
    return (
        f"<agent_team_prompt stage=\"{request.contract.stage}\">\n"
        "<role>\n"
        f"You are the {request.contract.stage} stage worker inside the Agent Team runtime driver.\n"
        "</role>\n\n"
        "<stage_task>\n"
        "Execute only this stage. Do not advance workflow state.\n"
        "</stage_task>\n\n"
        f"{skill_section}"
        "<alignment_updates>\n"
        "Use these only when regenerating this stage artifact; the corrected artifact feeds later stages.\n"
        f"{_xml_cdata(stage_alignment_updates or 'None')}\n"
        "</alignment_updates>\n\n"
        "<output_rules>\n"
        "Return only JSON stage payload.\n"
        "Keep the document in artifact_content.\n"
        "Human-readable content must be Simplified Chinese.\n"
        "Use evidence_by_name for contract evidence. Runtime owns evidence keys; you only fill each required key's value object.\n"
        "For every key in stage_contract.evidence_requirements, include that exact key in evidence_by_name.\n"
        "Do not invent derived evidence keys such as <required>_check or <required>_semantics; put sub-checks in metadata.checks or summary.\n"
        "</output_rules>\n\n"
        "<stage_rules>\n"
        f"{_xml_cdata(format_instructions)}\n"
        "</stage_rules>\n\n"
        "<stage_contract>\n"
        f"{_xml_cdata(contract_json)}\n"
        "</stage_contract>\n\n"
        "<stage_context>\n"
        f"{_xml_cdata(context_json)}\n"
        "</stage_context>\n"
        "</agent_team_prompt>\n"
    )


def _stage_artifact_format_instructions(stage: str, *, required_outputs: list[str] | None = None) -> str:
    required_outputs = required_outputs or []
    if stage == "Route":
        return (
            "- Write artifact_content as valid JSON for route-packet.json; JSON keys stay as required, but all human-readable string values must be Simplified Chinese.\n"
            "- Include affected_layers, required_stages, baseline_sources, red_lines, and unresolved_questions.\n"
            "- Do not implement code or rewrite product definition in Route."
        )
    if stage == "ProductDefinition":
        return (
            "- Write product-definition-delta.md content in Simplified Chinese.\n"
            "- If unclear or missing an L1 product decision, return status `blocked` with concise questions in artifact_content.\n"
            "- If understood, start with `## 理解复述`: intent, success criteria, and explicit non-goals.\n"
            "- Then separate `## L1 候选` from `## 非 L1 内容`.\n"
            "- L1 means stable product semantics, core objects, operating model, responsibility boundaries, and long-term rules.\n"
            "- Do not write implementation plans, local session notes, governance rules, or research drafts as product truth."
        )
    if stage == "ProjectRuntime":
        return (
            "- Write artifact_content as project-landing-delta.md in Simplified Chinese.\n"
            "- Capture only L3 project landing defaults: entrypoints, run commands, directories, packaging, "
            "configuration, deployment shape, and project-specific runtime conventions.\n"
            "- Do not redefine product semantics and do not create shared governance rules here."
        )
    if stage == "TechnicalDesign":
        return (
            "- Write technical-design.md content in Simplified Chinese. Do not edit source code in this stage.\n"
            "- If a material design choice is unresolved, return status `blocked` with focused questions in artifact_content.\n"
            "- If understood, start with `## 方案理解复述`: approved requirement, chosen approach, scope, non-goals, and verification target.\n"
            "- Include implementation approach, affected files/interfaces, verification plan, risks, and rollback.\n"
        )
    if stage == "Implementation":
        return (
            "- Write artifact_content as implementation.md in Simplified Chinese.\n"
            "- Treat approved_technical_design_content as the implementation source of truth.\n"
            "- Implement the approved technical design instead of replacing it with a new design.\n"
            "- If the approved technical design is missing, contradictory, or too ambiguous to implement safely, return status `blocked` with focused questions in artifact_content.\n"
            "- Keep changes scoped to the approved design.\n"
            "- For server-side changes, run or prepare end-to-end verification from API/request to persisted data; if database access or query confirmation is needed, return status `blocked` with the exact evidence needed from the user.\n"
            "- For frontend mini-program changes that cannot be launched locally, state the limitation and run available static, build, or unit checks instead of claiming runtime validation.\n"
            "- The implementation report must name changed files, actual behavior changes, self-review results, commands run, skipped checks, and unresolved risks in Chinese."
        )
    if stage == "Verification":
        return (
            "- Write artifact_content as verification-report.md in Simplified Chinese. Independently verify Implementation evidence against L1, L2, L3, and the technical design.\n"
            "- For server-side changes, verify the full path from API/request to persisted data; include command/request, response, and data evidence when available.\n"
            "- If database evidence requires user-provided access, query results, or approval, return status `blocked` with the exact query/evidence request.\n"
            "- For frontend mini-program changes that cannot be launched locally, state that limitation and verify with available static, build, or unit checks only."
        )
    if stage == "GovernanceReview":
        return "- Write artifact_content as governance-review.md in Simplified Chinese. Check five-layer boundary violations, evidence quality, writeback obligations, and merge readiness."
    if stage == "Acceptance":
        return "- Write artifact_content as acceptance-report.md in Simplified Chinese. Recommend final Go/No-Go from product result and governance evidence; do not claim human approval."
    if stage == "SessionHandoff":
        return "- Write artifact_content as session-handoff.md in Simplified Chinese. Preserve L5 local-control handoff, unresolved decisions, next actions, and non-promoted local material."
    return "- Write artifact_content in Simplified Chinese unless the user explicitly asks for another language, and keep it concise."


def _xml_cdata(value: str) -> str:
    return "<![CDATA[" + value.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _stage_alignment_update_summary(findings: list[Finding]) -> str:
    lines: list[str] = []
    for index, finding in enumerate(findings, start=1):
        issue = finding.issue.strip()
        if not issue:
            continue
        lines.append(f"{index}. {finding.source_stage} -> {finding.target_stage}: {issue}")
        if finding.proposed_context_update.strip():
            lines.append(f"   context_update: {finding.proposed_context_update.strip()}")
        if finding.lesson.strip():
            lines.append(f"   lesson: {finding.lesson.strip()}")
        if finding.required_evidence:
            lines.append(f"   required_evidence: {', '.join(finding.required_evidence)}")
        if finding.completion_signal.strip():
            lines.append(f"   completion_signal: {finding.completion_signal.strip()}")
    return "\n".join(lines)


def _add_runtime_trace_step(
    trace_steps: list[dict[str, Any]],
    *,
    step: str,
    status: str = "ok",
    details: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    first_at = _parse_trace_timestamp(trace_steps[0].get("at")) if trace_steps else None
    previous_at = _parse_trace_timestamp(trace_steps[-1].get("at")) if trace_steps else None
    trace_steps.append(
        {
            "step": step,
            "status": status,
            "at": now.isoformat(),
            "elapsed_seconds": _trace_seconds_between(first_at, now) if first_at is not None else 0.0,
            "since_previous_seconds": _trace_seconds_between(previous_at, now) if previous_at is not None else 0.0,
            "details": details or {},
        }
    )


def _trace_seconds_between(start: datetime, end: datetime) -> float:
    return round(max((end - start).total_seconds(), 0.0), 3)


def _parse_trace_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _write_runtime_trace(
    *,
    store: StateStore,
    session_id: str,
    run_id: str,
    stage: str,
    trace_steps: list[dict[str, Any]],
) -> None:
    del stage
    store.update_stage_run_trace(
        session_id=session_id,
        run_id=run_id,
        required_pass_steps=list(REQUIRED_PASS_TRACE_STEPS),
        steps=trace_steps,
    )


def _validate_runtime_trace(
    trace_steps: list[dict[str, Any]],
    *,
    required_steps: list[str],
) -> GateResult:
    ok_steps = [str(item.get("step", "")) for item in trace_steps if item.get("status") == "ok"]
    missing_steps = [step for step in required_steps if step not in ok_steps]
    if missing_steps:
        return GateResult(
            status="BLOCKED",
            reason="Runtime trace is missing required step(s): " + ", ".join(missing_steps),
            missing_evidence=["stage_result"],
        )

    cursor = -1
    for step in required_steps:
        try:
            index = ok_steps.index(step)
        except ValueError:
            return GateResult(
                status="BLOCKED",
                reason=f"Runtime trace is missing required step: {step}",
                missing_evidence=["stage_result"],
            )
        if index <= cursor:
            return GateResult(
                status="BLOCKED",
                reason=f"Runtime trace step is out of order: {step}",
                missing_evidence=["stage_result"],
            )
        cursor = index

    return GateResult(status="PASSED", reason="Runtime trace contains all non-skippable steps in order.")


def _stage_result_schema(contract: StageContract | None = None) -> dict[str, Any]:
    required_evidence = list(getattr(contract, "evidence_requirements", []) or [])
    evidence_value_schema = {
        "type": "object",
        "required": [
            "kind",
            "summary",
            "artifact_path",
            "command",
            "exit_code",
            "producer",
            "metadata",
        ],
        "properties": {
            "kind": {"type": "string"},
            "summary": {"type": "string"},
            "artifact_path": {"type": "string"},
            "command": {"type": "string"},
            "exit_code": {"type": ["integer", "null"]},
            "producer": {"type": "string"},
            "metadata": {
                "type": "object",
                "required": ["checks", "notes"],
                "properties": {
                    "checks": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "required": [
            "status",
            "artifact_content",
            "journal",
            "findings",
            "evidence",
            "evidence_by_name",
            "suggested_next_owner",
            "summary",
            "acceptance_status",
            "blocked_reason",
        ],
        "properties": {
            "status": {"enum": ["completed", "failed", "blocked"]},
            "artifact_content": {"type": "string"},
            "journal": {"type": "string"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "source_stage",
                        "target_stage",
                        "issue",
                        "severity",
                        "lesson",
                        "proposed_context_update",
                        "proposed_contract_update",
                        "evidence",
                        "evidence_kind",
                        "required_evidence",
                        "completion_signal",
                    ],
                    "properties": {
                        "source_stage": {"type": "string"},
                        "target_stage": {"type": "string"},
                        "issue": {"type": "string"},
                        "severity": {"type": "string"},
                        "lesson": {"type": "string"},
                        "proposed_context_update": {"type": "string"},
                        "proposed_contract_update": {"type": "string"},
                        "evidence": {"type": "string"},
                        "evidence_kind": {"type": "string"},
                        "required_evidence": {"type": "array", "items": {"type": "string"}},
                        "completion_signal": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "name",
                        "kind",
                        "summary",
                        "artifact_path",
                        "command",
                        "exit_code",
                        "producer",
                    ],
                    "properties": {
                        "name": {"type": "string"},
                        "kind": {"type": "string"},
                        "summary": {"type": "string"},
                        "artifact_path": {"type": "string"},
                        "command": {"type": "string"},
                        "exit_code": {"type": ["integer", "null"]},
                        "producer": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "evidence_by_name": {
                "type": "object",
                "required": required_evidence,
                "properties": {name: evidence_value_schema for name in required_evidence},
                "additionalProperties": False,
            },
            "suggested_next_owner": {"type": "string"},
            "summary": {"type": "string"},
            "acceptance_status": {"type": "string"},
            "blocked_reason": {"type": "string"},
        },
        "additionalProperties": False,
    }
