from __future__ import annotations

import argparse
import json
import shlex
import sys
from dataclasses import replace
from pathlib import Path

from .board import build_board_snapshot
from .executor import ClaudeCodeExecutor, CodexExecutor, StageExecutor
from .execution_context import build_stage_execution_context
from .gatekeeper import evaluate_candidate
from .harness_paths import default_state_root
from .intake import parse_intake_message
from .interactive import DevController, DevControllerConfig, ExecutorAlignmentRunner, ExecutorTechPlanRunner, InteractivePrompter
from .models import Finding, GateResult, StageResultEnvelope, WorkflowSummary
from .panel import build_panel_snapshot
from .project_structure import ensure_project_structure
from .skill_registry import STAGES, SOURCE_LABELS, SkillRegistry
from .stage_harness import StageHarness
from .stage_contracts import build_stage_contract
from .stage_machine import StageMachine
from .state import StageRunStateError, StateStore
from .workspace_metadata import refresh_workspace_metadata


RUN_REQUIREMENT_STAGE_ORDER = ("Product", "TechPlan", "Dev", "QA", "Acceptance")
RUN_REQUIREMENT_STAGE_TITLES = {
    "Product": "生成需求方案中",
    "TechPlan": "生成技术方案中",
    "Dev": "执行开发实现中",
    "QA": "执行 QA 验证中",
    "Acceptance": "执行验收判断中",
}
RUN_REQUIREMENT_WAIT_TO_STAGE = {
    "WaitForCEOApproval": "Product",
    "WaitForTechPlanApproval": "TechPlan",
    "WaitForDevApproval": "Dev",
    "WaitForQAApproval": "QA",
    "WaitForHumanDecision": "Acceptance",
}
RUN_REQUIREMENT_STAGE_DOCS = {
    "Product": ("PRD", "product", "prd.md"),
    "TechPlan": ("Technical Plan", "techplan", "technical_plan.md"),
    "Dev": ("Implementation", "dev", "implementation.md"),
    "QA": ("QA Report", "qa", "qa_report.md"),
    "Acceptance": ("Acceptance Report", "acceptance", "acceptance_report.md"),
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(_normalize_command_aliases(sys.argv[1:] if argv is None else argv))
    args.repo_root = args.repo_root.resolve()
    args.state_root = (
        args.state_root.resolve()
        if args.state_root is not None
        else default_state_root(repo_root=args.repo_root).resolve()
    )
    if _should_refresh_workspace_metadata(args.command):
        refresh_workspace_metadata(state_root=args.state_root, repo_root=args.repo_root)
    return args.handler(args)


def _normalize_command_aliases(argv: list[str]) -> list[str]:
    normalized = list(argv)
    index = 0
    value_options = {"--repo-root", "--state-root"}
    while index < len(normalized):
        token = normalized[index]
        if token in value_options:
            index += 2
            continue
        if token.startswith("--repo-root=") or token.startswith("--state-root="):
            index += 1
            continue
        if token == "run-requirement":
            normalized[index] = "run"
            break
        if not token.startswith("-"):
            break
        index += 1
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-team",
        description="Agent Team single-session workflow CLI.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--state-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Create workflow state directories and the project-level doc structure.",
        description=(
            "Create workflow state directories and the project-level doc structure. "
            "Use this once per clone before running the workflow."
        ),
    )
    init_parser.set_defaults(handler=_handle_init)

    start_session_parser = subparsers.add_parser(
        "start-session",
        help=(
            "Create a session scaffold for the single-session Agent Team workflow. "
            "Preferred entrypoint for the real skill-driven workflow."
        ),
        description=(
            "Create a session scaffold for the single-session Agent Team workflow. "
            "Preferred entrypoint for the real skill-driven workflow."
        ),
    )
    start_session_parser.add_argument("--message", required=True, help="Raw user message for session intake.")
    start_session_parser.add_argument(
        "--initiator",
        choices=["human", "agent"],
        default="agent",
        help="Who initiated this workflow session.",
    )
    start_session_parser.set_defaults(handler=_handle_start_session)

    run_requirement_parser = subparsers.add_parser(
        "run",
        help="Drive an Agent Team requirement through runtime-controlled stage execution.",
        description=(
            "Create or resume an Agent Team session and let the runtime acquire, execute, submit, "
            "verify, and advance each executable stage. Human gates are preserved unless explicit "
            "auto-decision flags are provided."
        ),
    )
    run_requirement_target = run_requirement_parser.add_mutually_exclusive_group(required=False)
    run_requirement_target.add_argument("--message", help="Raw user message for a new requirement session.")
    run_requirement_target.add_argument("--session-id", help="Existing session ID to continue driving.")
    run_requirement_parser.add_argument(
        "--executor",
        choices=["codex-exec", "command", "dry-run"],
        default="codex-exec",
        help="Stage executor backend. codex-exec runs Codex CLI; command runs --executor-command.",
    )
    run_requirement_parser.add_argument(
        "--executor-command",
        help=(
            "Shell command for --executor command. The command receives AGENT_TEAM_* environment variables "
            "and must write a StageResultEnvelope JSON to AGENT_TEAM_RESULT_BUNDLE or stdout."
        ),
    )
    run_requirement_parser.add_argument(
        "--command-timeout-seconds",
        type=int,
        default=3600,
        help="Timeout for codex-exec or command executor stage runs.",
    )
    run_requirement_parser.add_argument(
        "--auto",
        action="store_true",
        help=(
            "After the CEO approves Product, automatically pass TechPlan, Dev, QA, and the "
            "final Acceptance decision in interactive runs."
        ),
    )
    run_requirement_parser.add_argument(
        "--auto-approve-product",
        action="store_true",
        help="Automatically record Product approval. Intended for scripts; interactive --auto still keeps Product human-gated.",
    )
    run_requirement_parser.add_argument(
        "--auto-final-decision",
        choices=["go", "no-go"],
        default="",
        help="Automatically record the final human decision after Acceptance.",
    )
    run_requirement_parser.add_argument(
        "--max-stage-runs",
        type=int,
        default=12,
        help="Maximum executable stage attempts before the driver blocks to avoid loops.",
    )
    run_requirement_parser.add_argument(
        "--judge",
        choices=["off", "noop", "openai-sandbox"],
        default="off",
        help="Optional independent judge after hard gates pass.",
    )
    run_requirement_parser.add_argument("--model", default="gpt-5.4", help="Model for --judge openai-sandbox.")
    run_requirement_parser.add_argument("--docker-image", default="python:3.13-slim")
    run_requirement_parser.add_argument("--openai-api-key")
    run_requirement_parser.add_argument("--openai-base-url")
    run_requirement_parser.add_argument("--openai-proxy-url")
    run_requirement_parser.add_argument("--openai-user-agent", default="Agent-Team-Runtime/0.1")
    run_requirement_parser.add_argument("--openai-oa")
    run_requirement_parser.add_argument("--codex-model", default="", help="Optional model for codex-exec.")
    run_requirement_parser.add_argument(
        "--codex-sandbox",
        choices=["read-only", "workspace-write", "danger-full-access"],
        default="workspace-write",
        help="Sandbox mode passed to codex exec.",
    )
    run_requirement_parser.add_argument(
        "--codex-approval-policy",
        choices=["untrusted", "on-request", "never"],
        default="never",
        help="Approval policy passed to codex exec.",
    )
    run_requirement_parser.add_argument(
        "--codex-extra-arg",
        action="append",
        default=[],
        help="Extra argument passed through to codex exec. Repeat for multiple arguments.",
    )
    run_requirement_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Force the legacy single-shot behavior even when stdin/stdout are attached to a TTY.",
    )
    run_requirement_parser.add_argument(
        "--model-output",
        choices=["summary", "raw", "off"],
        default="summary",
        help="Interactive terminal output mode. summary shows stage progress; raw adds runtime details; off prints only gates and document paths.",
    )
    run_requirement_parser.set_defaults(handler=_handle_run_requirement)

    dev_parser = subparsers.add_parser(
        "dev",
        help=(
            "Interactive development workflow: clarify requirements, discuss technical approach, "
            "then execute via AI agents."
        ),
    )
    dev_parser.add_argument("--message", help="Initial requirement. Prompt if omitted.")
    dev_parser.add_argument("--session-id", help="Existing session to resume.")
    dev_parser.add_argument(
        "--executor",
        choices=["codex", "claude-code"],
        default="codex",
        help="AI executor for all interactive and stage prompts.",
    )
    dev_parser.add_argument("--product-executor", choices=["codex", "claude-code"], help="Executor for Product stage.")
    dev_parser.add_argument("--dev-executor", choices=["codex", "claude-code"], help="Executor for Dev stage.")
    dev_parser.add_argument("--qa-executor", choices=["codex", "claude-code"], help="Executor for QA stage.")
    dev_parser.add_argument(
        "--acceptance-executor",
        choices=["codex", "claude-code"],
        help="Executor for Acceptance stage.",
    )
    dev_parser.add_argument("--codex-bin", default="codex", help="Path to codex executable.")
    dev_parser.add_argument("--claude-bin", default="claude", help="Path to Claude Code executable.")
    dev_parser.add_argument("--model", default="", help="Optional model override.")
    dev_parser.add_argument("--sandbox", default="workspace-write", help="Codex sandbox mode.")
    dev_parser.add_argument("--approval", default="never", help="Codex approval policy.")
    dev_parser.add_argument("--profile", default="", help="Optional Codex config profile.")
    dev_parser.add_argument(
        "--with-skills",
        action="append",
        default=[],
        help="Enable skills for this run, e.g. dev:plan,refactor-checklist or qa:security-audit.",
    )
    dev_parser.add_argument(
        "--skip-skills",
        action="append",
        default=[],
        help="Skip skills for this run, e.g. qa:security-audit.",
    )
    dev_parser.add_argument("--skills-empty", action="store_true", help="Run without skills for this invocation.")
    dev_parser.add_argument("--dry-run", action="store_true", help="Print plan without executing.")
    dev_parser.set_defaults(handler=_handle_dev)

    skill_parser = subparsers.add_parser("skill", help="Inspect and manage Agent Team stage skills.")
    skill_subparsers = skill_parser.add_subparsers(dest="skill_command", required=True)

    skill_list_parser = skill_subparsers.add_parser("list", help="List available skills.")
    skill_list_parser.add_argument("--stage", choices=list(STAGES), help="Filter by stage.")
    skill_list_parser.add_argument("--source", choices=["builtin", "personal", "project"], help="Filter by source.")
    skill_list_parser.set_defaults(handler=_handle_skill_list)

    skill_show_parser = skill_subparsers.add_parser("show", help="Show a skill.")
    skill_show_parser.add_argument("name", help="Skill name.")
    skill_show_parser.add_argument("--stage", choices=list(STAGES), help="Resolve skill for a stage.")
    skill_show_parser.set_defaults(handler=_handle_skill_show)

    skill_preferences_parser = skill_subparsers.add_parser("preferences", help="Show or reset skill preferences.")
    skill_preferences_parser.add_argument("--reset", action="store_true", help="Clear skill preferences.")
    skill_preferences_parser.set_defaults(handler=_handle_skill_preferences)

    skill_default_parser = skill_subparsers.add_parser("default", help="Set or reset a stage default skill list.")
    skill_default_parser.add_argument("stage", choices=list(STAGES), help="Stage name.")
    skill_default_parser.add_argument("skills", nargs="*", help="Default skill names.")
    skill_default_parser.add_argument("--reset", action="store_true", help="Clear default skills for the stage.")
    skill_default_parser.set_defaults(handler=_handle_skill_default)

    current_stage_parser = subparsers.add_parser(
        "current-stage",
        help="Print the current workflow stage and summary state for a session.",
    )
    current_stage_parser.add_argument("--session-id", help="Specific session ID to inspect.")
    current_stage_parser.set_defaults(handler=_handle_current_stage)

    resume_parser = subparsers.add_parser(
        "resume",
        help="Print the current stage summary so the operator can resume execution.",
    )
    resume_parser.add_argument("--session-id", help="Specific session ID to inspect.")
    resume_parser.set_defaults(handler=_handle_current_stage)

    step_parser = subparsers.add_parser(
        "step",
        help="Print the next runtime action for the current workflow session.",
    )
    step_parser.add_argument("--session-id", help="Specific session ID to inspect.")
    step_parser.set_defaults(handler=_handle_step)

    build_contract_parser = subparsers.add_parser(
        "build-stage-contract",
        help="Build a machine-readable contract for the requested stage.",
    )
    build_contract_parser.add_argument("--session-id", required=True, help="Existing workflow session ID.")
    build_contract_parser.add_argument("--stage", required=True, help="Stage name to compile.")
    build_contract_parser.set_defaults(handler=_handle_build_stage_contract)

    build_execution_context_parser = subparsers.add_parser(
        "build-execution-context",
        help="Build and persist a machine-readable execution context for the requested stage.",
    )
    build_execution_context_parser.add_argument("--session-id", required=True, help="Existing workflow session ID.")
    build_execution_context_parser.add_argument("--stage", required=True, help="Stage name to compile.")
    build_execution_context_parser.set_defaults(handler=_handle_build_execution_context)

    acquire_stage_run_parser = subparsers.add_parser(
        "acquire-stage-run",
        help="Acquire the active executable stage as a tracked stage run.",
    )
    acquire_stage_run_parser.add_argument("--session-id", required=True, help="Existing workflow session ID.")
    acquire_stage_run_parser.add_argument("--stage", help="Override stage name; must match the active stage.")
    acquire_stage_run_parser.add_argument("--worker", default="codex", help="Logical worker name for the run.")
    acquire_stage_run_parser.set_defaults(handler=_handle_acquire_stage_run)

    submit_result_parser = subparsers.add_parser(
        "submit-stage-result",
        help="Persist a structured stage-result bundle as a submitted candidate result.",
    )
    submit_result_parser.add_argument("--session-id", required=True, help="Existing workflow session ID.")
    submit_result_parser.add_argument("--bundle", type=Path, required=True, help="Path to stage result bundle JSON.")
    submit_result_parser.set_defaults(handler=_handle_submit_stage_result)

    verify_result_parser = subparsers.add_parser(
        "verify-stage-result",
        help="Run gatekeeper verification for the submitted candidate result.",
    )
    verify_result_parser.add_argument("--session-id", required=True, help="Existing workflow session ID.")
    verify_result_parser.add_argument("--run-id", help="Optional explicit stage run to verify.")
    verify_result_parser.add_argument(
        "--judge",
        choices=["off", "noop", "openai-sandbox"],
        default="off",
        help="Optional independent judge to run after hard gates pass.",
    )
    verify_result_parser.add_argument("--model", default="gpt-5.4", help="Model for --judge openai-sandbox.")
    verify_result_parser.add_argument(
        "--docker-image",
        default="python:3.13-slim",
        help="Docker image for --judge openai-sandbox.",
    )
    verify_result_parser.add_argument(
        "--openai-api-key",
        help="Optional API key for --judge openai-sandbox. Defaults to SDK environment resolution.",
    )
    verify_result_parser.add_argument(
        "--openai-base-url",
        help="Optional base URL for --judge openai-sandbox. Defaults to SDK environment resolution.",
    )
    verify_result_parser.add_argument(
        "--openai-proxy-url",
        help="Optional HTTP proxy URL for --judge openai-sandbox, for example http://127.0.0.1:7897.",
    )
    verify_result_parser.add_argument(
        "--openai-user-agent",
        default="Agent-Team-Runtime/0.1",
        help="User-Agent for OpenAI-compatible requests. Defaults to Agent-Team-Runtime/0.1.",
    )
    verify_result_parser.add_argument(
        "--openai-oa",
        help="Optional oa header for OpenAI-compatible proxy requests. Defaults to --openai-user-agent.",
    )
    verify_result_parser.add_argument(
        "--acceptance-matrix",
        type=Path,
        help="Optional JSON file containing the approved acceptance matrix.",
    )
    verify_result_parser.set_defaults(handler=_handle_verify_stage_result)

    judge_result_parser = subparsers.add_parser(
        "judge-stage-result",
        help="Run read-only hard gate plus optional independent judge for a submitted stage result.",
    )
    judge_result_parser.add_argument("--session-id", required=True, help="Existing workflow session ID.")
    judge_result_parser.add_argument("--run-id", help="Optional explicit stage run to judge.")
    judge_result_parser.add_argument(
        "--judge",
        choices=["noop", "openai-sandbox"],
        default="noop",
        help="Judge backend. noop is local and deterministic; openai-sandbox uses OpenAI Agents SDK.",
    )
    judge_result_parser.add_argument("--model", default="gpt-5.4", help="Model for --judge openai-sandbox.")
    judge_result_parser.add_argument(
        "--docker-image",
        default="python:3.13-slim",
        help="Docker image for --judge openai-sandbox.",
    )
    judge_result_parser.add_argument(
        "--openai-api-key",
        help="Optional API key for --judge openai-sandbox. Defaults to SDK environment resolution.",
    )
    judge_result_parser.add_argument(
        "--openai-base-url",
        help="Optional base URL for --judge openai-sandbox. Defaults to SDK environment resolution.",
    )
    judge_result_parser.add_argument(
        "--openai-proxy-url",
        help="Optional HTTP proxy URL for --judge openai-sandbox, for example http://127.0.0.1:7897.",
    )
    judge_result_parser.add_argument(
        "--openai-user-agent",
        default="Agent-Team-Runtime/0.1",
        help="User-Agent for OpenAI-compatible requests. Defaults to Agent-Team-Runtime/0.1.",
    )
    judge_result_parser.add_argument(
        "--openai-oa",
        help="Optional oa header for OpenAI-compatible proxy requests. Defaults to --openai-user-agent.",
    )
    judge_result_parser.add_argument(
        "--acceptance-matrix",
        type=Path,
        help="Optional JSON file containing the approved acceptance matrix.",
    )
    judge_result_parser.add_argument(
        "--print-context",
        action="store_true",
        help="Include the generated JudgeContextCompact in the JSON output.",
    )
    judge_result_parser.set_defaults(handler=_handle_judge_stage_result)

    human_decision_parser = subparsers.add_parser(
        "record-human-decision",
        help="Record a human workflow decision for a wait state.",
    )
    human_decision_parser.add_argument("--session-id", required=True, help="Existing workflow session ID.")
    human_decision_parser.add_argument("--decision", required=True, help="One of go, no-go, rework.")
    human_decision_parser.add_argument("--target-stage", help="Required for rework decisions from acceptance.")
    human_decision_parser.set_defaults(handler=_handle_record_human_decision)

    feedback_parser = subparsers.add_parser(
        "record-feedback",
        help="Record human feedback as a structured learning finding.",
    )
    feedback_parser.add_argument("--session-id", required=True, help="Existing workflow session ID.")
    feedback_parser.add_argument("--source-stage", required=True, help="Stage where the feedback originated.")
    feedback_parser.add_argument("--target-stage", required=True, help="Role that should learn from the feedback.")
    feedback_parser.add_argument("--issue", required=True, help="Issue summary.")
    feedback_parser.add_argument("--severity", default="medium", help="Feedback severity.")
    feedback_parser.add_argument("--lesson", default="", help="Reusable lesson to store.")
    feedback_parser.add_argument("--context-update", default="", help="Context rule to store.")
    feedback_parser.add_argument("--skill-update", default="", help="Skill rule to store.")
    feedback_parser.add_argument("--evidence", default="", help="Optional evidence summary.")
    feedback_parser.add_argument("--evidence-kind", default="", help="Evidence source classification.")
    feedback_parser.add_argument(
        "--required-evidence",
        action="append",
        default=[],
        help="Evidence that must exist before the issue can be closed. Repeat to provide multiple values.",
    )
    feedback_parser.add_argument(
        "--completion-signal",
        default="",
        help="Explicit closure signal for the learning overlay.",
    )
    feedback_parser.add_argument(
        "--apply-rework",
        action="store_true",
        help="Also route the waiting workflow back to the target stage as a human rework decision.",
    )
    feedback_parser.set_defaults(handler=_handle_record_feedback)

    board_snapshot_parser = subparsers.add_parser(
        "board-snapshot",
        help="Print the read-only board snapshot as JSON.",
    )
    board_snapshot_parser.add_argument(
        "--all-workspaces",
        action="store_true",
        help="Aggregate every workspace under CODEX_HOME.",
    )
    board_snapshot_parser.set_defaults(handler=_handle_board_snapshot)

    serve_board_parser = subparsers.add_parser(
        "serve-board",
        help="Serve the local read-only board.",
    )
    serve_board_parser.add_argument("--all-workspaces", action="store_true")
    serve_board_parser.add_argument("--host", default="127.0.0.1")
    serve_board_parser.add_argument("--port", type=int, default=8765)
    serve_board_parser.add_argument("--poll-interval", type=int, default=5)
    serve_board_parser.set_defaults(handler=_handle_serve_board)

    review_parser = subparsers.add_parser("review", help="Print the latest or a selected review.")
    review_parser.add_argument("--session-id", help="Specific session ID to inspect.")
    review_parser.set_defaults(handler=_handle_review)

    status_parser = subparsers.add_parser(
        "status",
        help="Print a user-friendly project, role, and status summary for a session.",
    )
    status_parser.add_argument("--session-id", help="Specific session ID to inspect.")
    status_parser.set_defaults(handler=_handle_status)

    panel_snapshot_parser = subparsers.add_parser(
        "panel-snapshot",
        help="Print the current session snapshot as JSON for the runtime panel.",
    )
    panel_snapshot_parser.add_argument("--session-id", help="Specific session ID to inspect.")
    panel_snapshot_parser.set_defaults(handler=_handle_panel_snapshot)

    panel_parser = subparsers.add_parser(
        "panel",
        help="Start a local read-only web panel for workflow visibility.",
    )
    panel_parser.add_argument("--session-id", help="Specific session ID to inspect.")
    panel_parser.add_argument("--host", default="127.0.0.1", help="Host interface for the local panel.")
    panel_parser.add_argument("--port", type=int, default=8765, help="Port for the local panel.")
    panel_parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the local panel URL in the default browser.",
    )
    panel_parser.set_defaults(handler=_handle_panel)

    return parser


def _handle_init(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    store.ensure_layout()
    structure = ensure_project_structure(args.repo_root)
    print(f"state_root: {args.state_root}")
    print(f"repo_root: {structure.repo_root}")
    print(f"project_root: {structure.project_root}")
    print(f"doc_map_path: {structure.doc_map_path}")
    print(f"used_default_docs: {structure.used_default_docs}")
    print(f"doc_map: {json.dumps(structure.doc_map, ensure_ascii=False, sort_keys=True)}")
    return 0


def _handle_start_session(args: argparse.Namespace) -> int:
    intake = parse_intake_message(args.message)
    if not intake.request:
        raise SystemExit("Unable to extract a workflow request from --message.")

    store = StateStore(args.state_root)
    session = store.create_session(
        intake.request,
        raw_message=args.message,
        contract=intake.contract,
        runtime_mode="session_bootstrap",
        initiator=args.initiator,
    )
    summary_path = store.workflow_summary_path(session.session_id)

    print(f"session_id: {session.session_id}")
    print(f"artifact_dir: {session.artifact_dir}")
    print(f"summary_path: {summary_path}")
    return 0


def _handle_run_requirement(args: argparse.Namespace) -> int:
    from .runtime_driver import RuntimeDriverError, run_requirement

    interactive = _run_requirement_should_be_interactive(args)
    message, session_id = _resolve_run_requirement_target(args, interactive=interactive)
    if interactive:
        return _handle_run_requirement_interactive(args, message=message, session_id=session_id)

    try:
        result = run_requirement(
            repo_root=args.repo_root,
            state_root=args.state_root,
            message=message,
            session_id=session_id,
            options=_runtime_driver_options_from_args(args, interactive=False),
        )
    except RuntimeDriverError as exc:
        raise SystemExit(str(exc))

    _print_runtime_driver_result(result)
    return 1 if result.status in {"blocked", "failed"} else 0


def _runtime_driver_options_from_args(args: argparse.Namespace, *, interactive: bool):
    from .runtime_driver import RuntimeDriverOptions

    return RuntimeDriverOptions(
        executor=args.executor,
        executor_command=args.executor_command or "",
        command_timeout_seconds=args.command_timeout_seconds,
        auto_approve_product=args.auto_approve_product,
        auto_advance_intermediate=args.auto and not interactive,
        auto_final_decision=args.auto_final_decision,
        max_stage_runs=args.max_stage_runs,
        judge=args.judge,
        model=args.model,
        docker_image=args.docker_image,
        openai_api_key=args.openai_api_key,
        openai_base_url=args.openai_base_url,
        openai_proxy_url=args.openai_proxy_url,
        openai_user_agent=args.openai_user_agent,
        openai_oa=args.openai_oa,
        codex_model=args.codex_model,
        codex_sandbox=args.codex_sandbox,
        codex_approval_policy=args.codex_approval_policy,
        codex_extra_args=list(args.codex_extra_arg),
        interactive=interactive,
    )


def _print_runtime_driver_result(result) -> None:
    print(f"session_id: {result.session_id}")
    print(f"artifact_dir: {result.artifact_dir}")
    print(f"summary_path: {result.summary_path}")
    print(f"runtime_driver_status: {result.status}")
    print(f"current_state: {result.current_state}")
    print(f"current_stage: {result.current_stage}")
    print(f"acceptance_status: {result.acceptance_status}")
    print(f"human_decision: {result.human_decision}")
    print(f"stage_run_count: {result.stage_run_count}")
    if result.gate_status:
        print(f"gate_status: {result.gate_status}")
    if result.gate_reason:
        print(f"gate_reason: {result.gate_reason}")
    if result.next_action:
        print(f"next_action: {result.next_action}")


def _run_requirement_should_be_interactive(args: argparse.Namespace) -> bool:
    return not args.non_interactive and sys.stdin.isatty() and sys.stdout.isatty()


def _resolve_run_requirement_target(args: argparse.Namespace, *, interactive: bool) -> tuple[str, str]:
    if args.message and args.session_id:
        raise SystemExit("Provide either --message or --session-id, not both.")
    if args.message:
        return args.message, args.session_id or ""
    if args.session_id:
        return "", args.session_id
    if interactive:
        message = input("请输入需求：").strip()
        if not message:
            raise SystemExit("需求不能为空。")
        return message, ""
    raise SystemExit("run requires --message or --session-id when stdin/stdout are not interactive.")


def _handle_run_requirement_interactive(args: argparse.Namespace, *, message: str, session_id: str) -> int:
    from .runtime_driver import RuntimeDriverError, run_requirement

    store = StateStore(args.state_root)
    current_message = message
    current_session_id = session_id
    header_printed = False

    while True:
        if current_session_id:
            summary_before = store.load_workflow_summary(current_session_id)
            if summary_before.current_state not in RUN_REQUIREMENT_WAIT_TO_STAGE and summary_before.current_state not in {
                "Blocked",
                "Done",
            }:
                _print_run_requirement_stage_banner(
                    stage=_run_requirement_stage_for_summary(summary_before),
                    completed=_run_requirement_completed_stage_count(summary_before),
                )
        else:
            _print_run_requirement_stage_banner(
                stage="Product",
                completed=0,
            )

        try:
            result = run_requirement(
                repo_root=args.repo_root,
                state_root=args.state_root,
                message=current_message,
                session_id=current_session_id,
                options=_runtime_driver_options_from_args(args, interactive=True),
            )
        except RuntimeDriverError as exc:
            raise SystemExit(str(exc))

        if not header_printed:
            print(f"session_id: {result.session_id}")
            print(f"artifact_dir: {result.artifact_dir}")
            print(f"summary_path: {result.summary_path}")
            print("")
            header_printed = True

        summary = store.load_workflow_summary(result.session_id)
        stage = _run_requirement_stage_for_summary(summary)
        completed = _run_requirement_completed_stage_count(summary)
        _print_run_requirement_stage_report(
            store=store,
            session_id=result.session_id,
            stage=stage,
            completed=completed,
            summary=summary,
            model_output=args.model_output,
            result=result,
            auto_approving=_run_requirement_should_auto_approve_stage(args, stage),
        )

        if result.status in {"blocked", "failed"}:
            blocked_decision = _prompt_run_requirement_blocked_decision(
                store=store,
                summary=summary,
                stage=stage,
                result=result,
                args=args,
            )
            if blocked_decision == "quit":
                print("Session saved.")
                print(_run_requirement_resume_command(args, result.session_id))
                return 0
            _clear_run_requirement_blocker(store=store, summary=summary, stage=stage)
            current_session_id = result.session_id
            current_message = ""
            continue
        if result.status == "done" or summary.current_state == "Done":
            print("Session completed.")
            return 0
        if result.status != "waiting_human":
            return 0

        if _run_requirement_should_auto_approve_stage(args, stage):
            updated_summary = _apply_run_requirement_decision(
                store=store,
                summary=summary,
                decision="go",
                target_stage=None,
                issue="",
            )
            next_stage = (
                "完成交付"
                if updated_summary.current_state == "Done"
                else _run_requirement_stage_for_summary(updated_summary)
            )
            print(f"--auto: 已自动通过 {stage}，进入 {next_stage}。")
            current_session_id = result.session_id
            current_message = ""
            if updated_summary.current_state == "Done":
                print("Session completed.")
                return 0
            continue

        decision = _prompt_run_requirement_decision(
            store=store,
            summary=summary,
            stage=stage,
            model_output=args.model_output,
        )
        if decision["action"] == "quit":
            print("Session saved.")
            print(_run_requirement_resume_command(args, result.session_id))
            return 0

        updated_summary = _apply_run_requirement_decision(
            store=store,
            summary=summary,
            decision=decision["decision"],
            target_stage=decision.get("target_stage"),
            issue=decision.get("issue", ""),
        )
        current_session_id = result.session_id
        current_message = ""

        if updated_summary.current_state == "Done":
            print("Session completed.")
            return 0


def _run_requirement_should_auto_approve_stage(args: argparse.Namespace, stage: str) -> bool:
    return bool(args.auto) and stage in {"TechPlan", "Dev", "QA", "Acceptance"}


def _print_run_requirement_stage_banner(*, stage: str, completed: int) -> None:
    total = len(RUN_REQUIREMENT_STAGE_ORDER)
    print(f"[{completed + 1}/{total} {stage}] {RUN_REQUIREMENT_STAGE_TITLES.get(stage, stage)}...")
    print(f"进度: {_render_progress_bar(completed, total)}")


def _print_run_requirement_stage_report(
    *,
    store: StateStore,
    session_id: str,
    stage: str,
    completed: int,
    summary: WorkflowSummary,
    model_output: str,
    result,
    auto_approving: bool = False,
) -> None:
    session = store.load_session(session_id)
    label, artifact_key, filename = RUN_REQUIREMENT_STAGE_DOCS.get(stage, (stage, stage.lower(), f"{stage.lower()}.md"))
    doc_path = summary.artifact_paths.get(artifact_key) or str(session.artifact_dir / filename)
    print(f"[{completed}/{len(RUN_REQUIREMENT_STAGE_ORDER)} {stage}] {RUN_REQUIREMENT_STAGE_TITLES.get(stage, stage)}")
    print(f"进度: {_render_progress_bar(completed, len(RUN_REQUIREMENT_STAGE_ORDER))}")
    if model_output != "off":
        for line in _run_requirement_stage_summary_lines(stage, summary, auto_approving=auto_approving):
            print(f"- {line}")
    print("文档:")
    print(f"- {label}: {doc_path}")
    if model_output == "raw":
        print("调试信息:")
        _print_runtime_driver_result(result)
        _print_run_requirement_raw_streams(store=store, session_id=session_id, stage=stage)
    if result.gate_reason and model_output != "raw":
        print(f"gate_reason: {result.gate_reason}")
    print("下一步:")
    if result.status == "done":
        print("流程已完成。")
    elif result.status in {"blocked", "failed"}:
        print("请检查 gate_reason、stage_run trace 和阶段产物后修复。")
    elif auto_approving:
        print(_run_requirement_auto_next_step_text(stage))
    else:
        print(_run_requirement_next_step_text(stage))
    print("")


def _run_requirement_stage_summary_lines(
    stage: str,
    summary: WorkflowSummary,
    *,
    auto_approving: bool = False,
) -> list[str]:
    del summary
    if stage == "Product":
        return [
            "已解析原始需求",
            "已整理目标、边界和验收标准",
            "已写入 PRD",
        ]
    if stage == "TechPlan":
        return [
            "已确认 PRD 作为技术方案输入",
            "已拆分实现步骤和验证方式",
            "已写入 technical_plan.md",
        ]
    if stage == "Dev":
        return [
            "已根据技术方案完成实现",
            "已记录自检和改动文件",
            "已写入 implementation.md",
        ]
    if stage == "QA":
        return [
            "已独立验证实现结果",
            "已记录 QA 结论和发现",
            "已写入 qa_report.md",
        ]
    if stage == "Acceptance":
        return [
            "已按验收标准汇总结论",
            "已写入 acceptance_report.md",
            "--auto 将自动记录最终通过" if auto_approving else "等待最终人工决策",
        ]
    return [
        "已推进到当前阶段",
    ]


def _run_requirement_next_step_text(stage: str) -> str:
    if stage == "Product":
        return "请打开 PRD 文档确认需求方案和验收标准是否通过。"
    if stage == "TechPlan":
        return "请打开技术方案文档确认实现路径和验证方式是否通过。"
    if stage == "Dev":
        return "请打开实现文档确认代码改动和自检结果是否通过。"
    if stage == "QA":
        return "请打开 QA 报告确认验证结果是否通过。"
    if stage == "Acceptance":
        return "请打开验收报告并确认最终决策。"
    return "请确认当前阶段是否通过。"


def _run_requirement_auto_next_step_text(stage: str) -> str:
    if stage == "Acceptance":
        return "--auto 已启用，将自动通过 Acceptance 并完成交付。"
    next_stage = {
        "TechPlan": "Dev",
        "Dev": "QA",
        "QA": "Acceptance",
    }.get(stage, "下一阶段")
    return f"--auto 已启用，将自动通过 {stage} 并进入 {next_stage}。"


def _prompt_run_requirement_blocked_decision(
    *,
    store: StateStore,
    summary: WorkflowSummary,
    stage: str,
    result,
    args: argparse.Namespace,
) -> str:
    while True:
        print("当前阶段执行被阻塞。")
        print("[r] 重新执行当前阶段")
        print("[p] 打印诊断文件路径")
        print("[q] 保存并退出")
        raw = input("> ").strip().lower()
        if raw == "r":
            return "retry"
        if raw == "p":
            _print_run_requirement_diagnostics(store=store, session_id=result.session_id, stage=stage, args=args)
            continue
        if raw == "q":
            return "quit"
        print("请输入 r / p / q。")


def _clear_run_requirement_blocker(*, store: StateStore, summary: WorkflowSummary, stage: str) -> None:
    session = store.load_session(summary.session_id)
    current_state = summary.current_state
    current_stage = summary.current_stage
    if current_state == "Blocked":
        current_state = stage if stage in RUN_REQUIREMENT_STAGE_ORDER else "Product"
        current_stage = current_state
    store.save_workflow_summary(
        session,
        replace(
            summary,
            current_state=current_state,
            current_stage=current_stage,
            blocked_reason="",
        ),
    )
    store.record_event(
        summary.session_id,
        kind="workflow_blocker_cleared",
        stage=current_stage,
        state=current_state,
        actor="human",
        status="retry",
        message="Interactive operator chose to retry the blocked stage.",
    )


def _print_run_requirement_diagnostics(
    *,
    store: StateStore,
    session_id: str,
    stage: str,
    args: argparse.Namespace,
) -> None:
    session = store.load_session(session_id)
    run = store.latest_stage_run(session_id, stage=stage)
    print("诊断信息:")
    print(f"- executor: {args.executor}")
    print(f"- artifact_dir: {session.artifact_dir}")
    print(f"- workflow_summary: {store.workflow_summary_path(session_id)}")
    if run is None:
        return
    stage_runs_dir = session.session_dir / "stage_runs"
    print(f"- run_id: {run.run_id}")
    print(f"- run_state: {run.state}")
    if run.blocked_reason:
        print(f"- blocked_reason: {run.blocked_reason}")
    context_path = store.latest_execution_context_path(session_id, stage)
    if context_path is not None:
        print(f"- context: {context_path}")
    for label, path in (
        ("contract", stage_runs_dir / f"{run.run_id}_contract.json"),
        ("result", stage_runs_dir / f"{run.run_id}_result.json"),
        ("candidate", stage_runs_dir / f"{run.run_id}_candidate.json"),
        ("stdout", stage_runs_dir / f"{run.run_id}_stdout.txt"),
        ("stderr", stage_runs_dir / f"{run.run_id}_stderr.txt"),
        ("trace", stage_runs_dir / f"{run.run_id}_trace.json"),
    ):
        if path.exists():
            print(f"- {label}: {path}")


def _print_run_requirement_raw_streams(*, store: StateStore, session_id: str, stage: str) -> None:
    run = store.latest_stage_run(session_id, stage=stage)
    if run is None:
        return
    session = store.load_session(session_id)
    stage_runs_dir = session.session_dir / "stage_runs"
    trace_path = run.artifact_paths.get("runtime_trace")
    if trace_path:
        print(f"runtime_trace: {trace_path}")
    for stream_name in ("stdout", "stderr"):
        stream_path = stage_runs_dir / f"{run.run_id}_{stream_name}.txt"
        if not stream_path.exists():
            continue
        print(f"{stream_name}_path: {stream_path}")
        content = stream_path.read_text()
        if content.strip():
            print(f"{stream_name}:")
            print(_truncate_terminal_text(content, limit=4000))


def _truncate_terminal_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value.rstrip()
    return value[:limit].rstrip() + "\n...<truncated>"


def _prompt_run_requirement_decision(
    *,
    store: StateStore,
    summary: WorkflowSummary,
    stage: str,
    model_output: str,
) -> dict[str, str]:
    del model_output
    print(_run_requirement_prompt_text(stage))
    while True:
        raw = input("> ").strip().lower()
        if raw == "p":
            _print_run_requirement_document_link(store=store, summary=summary, stage=stage)
            continue
        if raw == "q":
            return {"action": "quit"}
        if raw == "y":
            return {"action": "apply", "decision": "go"}
        if raw == "e":
            issue = input("修改意见：").strip()
            if stage == "Acceptance":
                target_stage = _prompt_acceptance_rework_target()
                return {
                    "action": "apply",
                    "decision": "rework",
                    "target_stage": target_stage,
                    "issue": issue or "用户要求返工。",
                }
            target_stage = _run_requirement_rework_target(stage)
            return {
                "action": "apply",
                "decision": "rework",
                "target_stage": target_stage,
                "issue": issue or "用户要求返工。",
            }
        if stage == "Acceptance" and raw in {"n", "no"}:
            return {"action": "apply", "decision": "no-go"}
        print("请输入 y / e / p / q。" if stage != "Acceptance" else "请输入 y / n / e / p / q。")


def _prompt_acceptance_rework_target() -> str:
    while True:
        raw = input("返工目标（Product/TechPlan/Dev）：").strip()
        if raw.lower() in {"product", "p"}:
            return "Product"
        if raw.lower() in {"techplan", "tech", "t"}:
            return "TechPlan"
        if raw.lower() in {"dev", "d"}:
            return "Dev"
        print("请输入 Product、TechPlan 或 Dev。")


def _run_requirement_prompt_text(stage: str) -> str:
    if stage == "Acceptance":
        return "[y] 通过，完成交付\n[n] 不通过\n[e] 提修改意见，重新返工\n[p] 重新打印文档链接\n[q] 保存并退出"
    if stage == "Product":
        return "[y] 通过，进入技术方案\n[e] 提修改意见，重新生成 PRD\n[p] 重新打印 PRD 文档链接\n[q] 保存并退出"
    if stage == "TechPlan":
        return "[y] 通过，进入开发实现\n[e] 提修改意见，重新生成技术方案\n[p] 重新打印技术方案文档链接\n[q] 保存并退出"
    if stage == "Dev":
        return "[y] 通过，进入 QA\n[e] 提修改意见，打回 Dev\n[p] 重新打印实现文档链接\n[q] 保存并退出"
    if stage == "QA":
        return "[y] 通过，进入验收\n[e] 提修改意见，打回 Dev\n[p] 重新打印 QA 报告链接\n[q] 保存并退出"
    return (
        "[y] 通过，进入下一阶段\n"
        "[e] 提修改意见，重新生成当前阶段\n"
        "[p] 重新打印文档链接\n"
        "[q] 保存并退出"
    )


def _run_requirement_rework_target(stage: str) -> str:
    if stage == "QA":
        return "Dev"
    return stage


def _print_run_requirement_document_link(*, store: StateStore, summary: WorkflowSummary, stage: str) -> None:
    session = store.load_session(summary.session_id)
    label, artifact_key, filename = RUN_REQUIREMENT_STAGE_DOCS.get(stage, (stage, stage.lower(), f"{stage.lower()}.md"))
    doc_path = summary.artifact_paths.get(artifact_key) or str(session.artifact_dir / filename)
    print("文档:")
    print(f"- {label}: {doc_path}")


def _apply_run_requirement_decision(
    *,
    store: StateStore,
    summary: WorkflowSummary,
    decision: str,
    target_stage: str | None,
    issue: str,
) -> WorkflowSummary:
    session = store.load_session(summary.session_id)
    if issue:
        source_stage = _run_requirement_stage_for_summary(summary)
        finding = Finding(
            source_stage=source_stage,
            target_stage=target_stage or source_stage,
            issue=issue,
            severity="medium",
        )
        store.record_feedback(summary.session_id, finding)
    updated_summary = StageMachine().apply_human_decision(
        summary=summary,
        decision=decision,
        target_stage=target_stage,
    )
    store.save_workflow_summary(session, updated_summary)
    store.set_human_decision(summary.session_id, updated_summary.human_decision)
    store.record_event(
        summary.session_id,
        kind="workflow_state_changed",
        stage=updated_summary.current_stage,
        state=updated_summary.current_state,
        actor="human",
        status=updated_summary.human_decision,
        message=(
            f"Workflow moved to {updated_summary.current_stage} / "
            f"{updated_summary.current_state} after interactive decision."
        ),
    )
    return updated_summary


def _run_requirement_resume_command(args: argparse.Namespace, session_id: str) -> str:
    return (
        "Resume:\n"
        f"agent-team --repo-root {shlex.quote(str(args.repo_root))} "
        f"--state-root {shlex.quote(str(args.state_root))} "
        f"run --session-id {shlex.quote(session_id)}"
    )


def _run_requirement_stage_for_summary(summary: WorkflowSummary) -> str:
    if summary.current_state in RUN_REQUIREMENT_WAIT_TO_STAGE:
        return RUN_REQUIREMENT_WAIT_TO_STAGE[summary.current_state]
    if summary.current_state in RUN_REQUIREMENT_STAGE_ORDER:
        return summary.current_state
    if summary.current_state in {"Intake", "ProductDraft"}:
        return "Product"
    if summary.current_stage in RUN_REQUIREMENT_STAGE_ORDER:
        return summary.current_stage
    return "Product"


def _run_requirement_completed_stage_count(summary: WorkflowSummary) -> int:
    if summary.current_state in {"Intake", "ProductDraft"}:
        return 0
    if summary.current_state in {"WaitForCEOApproval", "TechPlan"}:
        return 1
    if summary.current_state in {"WaitForTechPlanApproval", "Dev"}:
        return 2
    if summary.current_state in {"WaitForDevApproval", "QA"}:
        return 3
    if summary.current_state in {"WaitForQAApproval", "Acceptance"}:
        return 4
    if summary.current_state in {"WaitForHumanDecision", "Done"}:
        return 5
    if summary.current_state == "Blocked" and summary.current_stage in RUN_REQUIREMENT_STAGE_ORDER:
        return RUN_REQUIREMENT_STAGE_ORDER.index(summary.current_stage)
    return 0


def _render_progress_bar(completed: int, total: int, width: int = 10) -> str:
    total = max(total, 1)
    completed = max(0, min(completed, total))
    filled = int(width * completed / total)
    return f"[{'#' * filled}{'-' * (width - filled)}] {completed}/{total}"


def _handle_dev(args: argparse.Namespace) -> int:
    if args.dry_run:
        print("agent-team dev dry run")
        print(f"repo_root: {args.repo_root}")
        print(f"executor: {args.executor}")
        print(f"codex_bin: {args.codex_bin}")
        print(f"claude_bin: {args.claude_bin}")
        return 0

    store = StateStore(args.state_root)
    default_executor = _build_executor(args, args.executor)
    alignment_runner = ExecutorAlignmentRunner(repo_root=args.repo_root, executor=default_executor)
    tech_plan_runner = ExecutorTechPlanRunner(repo_root=args.repo_root, executor=default_executor)
    skill_registry = SkillRegistry(args.repo_root)
    stage_harness = StageHarness(
        repo_root=args.repo_root,
        state_store=store,
        executor=default_executor,
        stage_executors=_stage_executor_overrides(args),
    )
    controller = DevController(
        config=DevControllerConfig(
            repo_root=args.repo_root,
            state_store=store,
            message=args.message or "",
            session_id=args.session_id or "",
        ),
        prompter=InteractivePrompter(),
        alignment_runner=alignment_runner,
        tech_plan_runner=tech_plan_runner,
        stage_harness=stage_harness,
        skill_registry=skill_registry,
        skill_overrides=_resolve_skill_overrides(args, skill_registry),
        skills_empty=args.skills_empty,
    )
    session_id = controller.run()
    print(f"session_id: {session_id}")
    print(f"panel: agent-team panel --session-id {session_id}")
    return 0


def _build_executor(args: argparse.Namespace, executor_name: str) -> StageExecutor:
    if executor_name == "claude-code":
        return ClaudeCodeExecutor(
            claude_bin=args.claude_bin,
            model=args.model,
        )
    return CodexExecutor(
        repo_root=args.repo_root,
        codex_bin=args.codex_bin,
        model=args.model,
        sandbox=args.sandbox,
        approval=args.approval,
        profile=args.profile,
    )


def _stage_executor_overrides(args: argparse.Namespace) -> dict[str, StageExecutor]:
    overrides: dict[str, StageExecutor] = {}
    for stage in ("Product", "Dev", "QA", "Acceptance"):
        value = getattr(args, f"{stage.lower()}_executor", None)
        if value:
            overrides[stage] = _build_executor(args, value)
    return overrides


def _resolve_skill_overrides(args: argparse.Namespace, registry: SkillRegistry) -> dict[str, list[str]]:
    if args.skills_empty:
        return {}
    if not args.with_skills and not args.skip_skills:
        return {}

    selected = {stage: registry.load_preferences().selected_for(stage) for stage in STAGES}
    for stage, names in _parse_stage_skill_specs(args.with_skills).items():
        selected[stage] = names
    for stage, names in _parse_stage_skill_specs(args.skip_skills).items():
        selected[stage] = [name for name in selected.get(stage, []) if name not in set(names)]
    return selected


def _parse_stage_skill_specs(specs: list[str]) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for spec in specs:
        if ":" not in spec:
            raise SystemExit(f"Skill spec must be stage:name[,name]: {spec}")
        stage_raw, names_raw = spec.split(":", 1)
        stage = _normalize_stage_name(stage_raw)
        names = [name.strip() for name in names_raw.split(",") if name.strip()]
        parsed.setdefault(stage, []).extend(names)
    return parsed


def _normalize_stage_name(stage: str) -> str:
    for known in STAGES:
        if known.lower() == stage.lower():
            return known
    raise SystemExit(f"Unknown skill stage: {stage}")


def _handle_skill_list(args: argparse.Namespace) -> int:
    registry = SkillRegistry(args.repo_root)
    for skill in registry.list_skills(stage=args.stage, source=args.source):
        stages = ",".join(skill.stages)
        print(f"{skill.name}\t{SOURCE_LABELS[skill.source]}\t{stages}\t{skill.description}")
    return 0


def _handle_skill_show(args: argparse.Namespace) -> int:
    registry = SkillRegistry(args.repo_root)
    skill = registry.get_skill(args.name, stage=args.stage)
    if skill is None:
        raise SystemExit(f"Skill not found: {args.name}")
    print(f"name: {skill.name}")
    print(f"source: {SOURCE_LABELS[skill.source]}")
    print(f"stages: {', '.join(skill.stages)}")
    print(f"path: {skill.path}")
    print("")
    print(skill.content)
    return 0


def _handle_skill_preferences(args: argparse.Namespace) -> int:
    registry = SkillRegistry(args.repo_root)
    if args.reset:
        registry.reset_preferences()
    assert registry.preference_path is not None
    print(registry.preference_path.read_text() if registry.preference_path.exists() else "")
    return 0


def _handle_skill_default(args: argparse.Namespace) -> int:
    registry = SkillRegistry(args.repo_root)
    if args.reset:
        registry.clear_default(args.stage)
    else:
        registry.set_default(args.stage, args.skills)
    assert registry.preference_path is not None
    print(registry.preference_path.read_text())
    return 0


def _handle_current_stage(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    session_id = args.session_id or store.latest_session_id()
    if not session_id:
        raise SystemExit("No workflow session exists yet.")

    summary = store.load_workflow_summary(session_id)
    _print_summary(summary)
    return 0


def _handle_step(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    session_id = args.session_id or store.latest_session_id()
    if not session_id:
        raise SystemExit("No workflow session exists yet.")

    summary = store.load_workflow_summary(session_id)
    _print_summary(summary)

    if summary.current_state in {
        "WaitForCEOApproval",
        "WaitForTechPlanApproval",
        "WaitForDevApproval",
        "WaitForQAApproval",
        "WaitForHumanDecision",
    }:
        print("next_action: record-human-decision")
        return 0

    active_run = store.active_stage_run(session_id)
    if active_run is not None:
        print(f"run_id: {active_run.run_id}")
        print(f"run_stage: {active_run.stage}")
        print(f"run_state: {active_run.state}")
        print(f"contract_id: {active_run.contract_id}")
        if active_run.required_outputs:
            print(f"required_outputs: {', '.join(active_run.required_outputs)}")
        if active_run.required_evidence:
            print(f"required_evidence: {', '.join(active_run.required_evidence)}")
        if active_run.state == "RUNNING":
            print("next_action: submit-stage-result")
        elif active_run.state == "SUBMITTED":
            print("next_action: verify-stage-result")
        else:
            print("next_action: wait")
        return 0

    expected_stage = _expected_submission_stage(summary)
    if expected_stage is None:
        print("next_action: none")
        return 0

    contract = build_stage_contract(
        repo_root=args.repo_root,
        state_store=store,
        session_id=session_id,
        stage=expected_stage,
    )
    print(f"next_stage: {expected_stage}")
    print(f"contract_id: {contract.contract_id}")
    if contract.required_outputs:
        print(f"required_outputs: {', '.join(contract.required_outputs)}")
    if contract.evidence_requirements:
        print(f"required_evidence: {', '.join(contract.evidence_requirements)}")
    print("next_action: acquire-stage-run")
    return 0


def _handle_build_stage_contract(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    contract = build_stage_contract(
        repo_root=args.repo_root,
        state_store=store,
        session_id=args.session_id,
        stage=args.stage,
    )
    store.record_event(
        args.session_id,
        kind="stage_contract_requested",
        stage=args.stage,
        state=args.stage,
        actor="operator",
        status="requested",
        message=f"Stage contract requested for {args.stage}.",
        details={"contract_id": contract.contract_id},
    )
    print(json.dumps(contract.to_dict(), indent=2))
    return 0


def _handle_build_execution_context(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    contract = build_stage_contract(
        repo_root=args.repo_root,
        state_store=store,
        session_id=args.session_id,
        stage=args.stage,
    )
    context = build_stage_execution_context(
        repo_root=args.repo_root,
        state_store=store,
        session_id=args.session_id,
        stage=args.stage,
        contract=contract,
    )
    context_path = store.save_execution_context(context)
    session = store.load_session(args.session_id)
    summary = store.load_workflow_summary(args.session_id)
    summary.artifact_paths["execution_context"] = str(context_path)
    store.save_workflow_summary(session, summary)
    print(json.dumps(context.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _handle_acquire_stage_run(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    summary = store.load_workflow_summary(args.session_id)
    expected_stage = _expected_submission_stage(summary)
    if expected_stage is None:
        raise SystemExit(f"Cannot acquire a stage run while workflow is waiting in {summary.current_state}.")

    stage = args.stage or expected_stage
    if stage != expected_stage:
        raise SystemExit(f"Expected active stage {expected_stage}, but acquire requested {stage}.")

    contract = build_stage_contract(
        repo_root=args.repo_root,
        state_store=store,
        session_id=args.session_id,
        stage=stage,
    )
    try:
        run = store.create_stage_run(
            session_id=args.session_id,
            stage=stage,
            contract_id=contract.contract_id,
            required_outputs=list(contract.required_outputs),
            required_evidence=list(contract.evidence_requirements),
            worker=args.worker,
        )
    except StageRunStateError as exc:
        raise SystemExit(str(exc))

    print(f"run_id: {run.run_id}")
    print(f"run_stage: {run.stage}")
    print(f"run_state: {run.state}")
    print(f"contract_id: {run.contract_id}")
    return 0


def _handle_submit_stage_result(args: argparse.Namespace) -> int:
    payload = json.loads(args.bundle.read_text())
    result = StageResultEnvelope.from_dict(payload)
    if result.session_id != args.session_id:
        raise SystemExit("Bundle session_id does not match --session-id.")

    store = StateStore(args.state_root)
    summary = store.load_workflow_summary(args.session_id)
    expected_stage = _expected_submission_stage(summary)
    if expected_stage is None:
        raise SystemExit(f"Cannot submit a stage result while workflow is waiting in {summary.current_state}.")
    active_run = store.active_stage_run(args.session_id, stage=expected_stage)
    if active_run is None:
        raise SystemExit(f"No active stage run for {expected_stage}. Acquire the stage run first.")
    if result.stage != active_run.stage:
        raise SystemExit(f"Expected active stage {active_run.stage}, but bundle declared {result.stage}.")
    if not result.contract_id:
        raise SystemExit("Bundle is missing contract_id.")

    try:
        submitted = store.submit_stage_run_result(active_run.run_id, result)
    except StageRunStateError as exc:
        raise SystemExit(str(exc))

    print(f"stored_bundle: {args.bundle}")
    print(f"run_id: {submitted.run_id}")
    print(f"run_state: {submitted.state}")
    _print_summary(summary)
    return 0


def _handle_verify_stage_result(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    summary = store.load_workflow_summary(args.session_id)

    if args.run_id:
        run = store.load_stage_run(args.run_id)
    else:
        expected_stage = _expected_submission_stage(summary)
        if expected_stage is None:
            raise SystemExit(f"Cannot verify a stage result while workflow is waiting in {summary.current_state}.")
        run = store.active_stage_run(args.session_id, stage=expected_stage)
        if run is None:
            raise SystemExit(f"No active stage run for {expected_stage}.")

    if run.session_id != args.session_id:
        raise SystemExit("Stage run session_id does not match --session-id.")
    if run.state != "SUBMITTED":
        raise SystemExit(f"Stage run {run.run_id} is {run.state}; expected SUBMITTED.")
    if not run.candidate_bundle_path:
        raise SystemExit(f"Stage run {run.run_id} has no submitted candidate bundle.")

    result = StageResultEnvelope.from_dict(json.loads(Path(run.candidate_bundle_path).read_text()))
    contract = build_stage_contract(
        repo_root=args.repo_root,
        state_store=store,
        session_id=args.session_id,
        stage=run.stage,
    )
    verifying_run = store.update_stage_run(run, state="VERIFYING")
    try:
        gate_result, normalized_result, judge_payload = _evaluate_stage_result_for_verification(
            args=args,
            store=store,
            summary=summary,
            contract=contract,
            result=result,
        )
    except SystemExit:
        store.update_stage_run(verifying_run, state="SUBMITTED")
        raise

    if gate_result.status == "PASSED":
        stage_record = store.record_stage_result(args.session_id, normalized_result)
        session = store.load_session(args.session_id)
        updated_summary = StageMachine().advance(summary=summary, stage_result=normalized_result)
        updated_summary.artifact_paths[normalized_result.stage.lower()] = str(stage_record.artifact_path)
        updated_summary.artifact_paths.update(stage_record.supplemental_artifact_paths)
        store.save_workflow_summary(session, updated_summary)
        store.update_stage_run(
            verifying_run,
            state="PASSED",
            gate_result=gate_result,
            blocked_reason="",
            artifact_paths={
                normalized_result.stage.lower(): str(stage_record.artifact_path),
                **stage_record.supplemental_artifact_paths,
            },
        )
        for finding in normalized_result.findings:
            store.apply_learning(finding)
        print(f"run_id: {verifying_run.run_id}")
        print(f"gate_status: {gate_result.status}")
        _print_judge_payload(judge_payload)
        _print_summary(updated_summary)
        return 0

    session = store.load_session(args.session_id)
    updated_summary = replace(summary, blocked_reason=gate_result.reason if gate_result.status == "BLOCKED" else "")
    store.save_workflow_summary(session, updated_summary)
    store.update_stage_run(
        verifying_run,
        state=gate_result.status,
        gate_result=gate_result,
        blocked_reason=gate_result.reason if gate_result.status == "BLOCKED" else "",
    )
    print(f"run_id: {verifying_run.run_id}")
    print(f"gate_status: {gate_result.status}")
    _print_judge_payload(judge_payload)
    if gate_result.reason:
        print(f"gate_reason: {gate_result.reason}")
    _print_summary(updated_summary)
    return 1


def _evaluate_stage_result_for_verification(
    *,
    args: argparse.Namespace,
    store: StateStore,
    summary: WorkflowSummary,
    contract,
    result: StageResultEnvelope,
):
    if args.judge == "off":
        gate_result, normalized_result = evaluate_candidate(
            session=store.load_session(args.session_id),
            contract=contract,
            result=result,
            acceptance_contract=store.load_acceptance_contract(args.session_id),
        )
        return gate_result, normalized_result, None

    from .gate_evaluator import GateEvaluator, NoopJudge
    from .openai_sandbox_judge import OpenAISandboxJudge, OpenAISandboxJudgeUnavailable
    from .stage_policies import default_policy_registry

    judge = (
        OpenAISandboxJudge(
            model=args.model,
            docker_image=args.docker_image,
            api_key=args.openai_api_key,
            base_url=args.openai_base_url,
            proxy_url=args.openai_proxy_url,
            user_agent=args.openai_user_agent,
            oa_header=_resolve_openai_oa_header(args),
        )
        if args.judge == "openai-sandbox"
        else NoopJudge()
    )
    session = store.load_session(args.session_id)
    try:
        evaluation = GateEvaluator(judge=judge).evaluate(
            session=session,
            policy=default_policy_registry().get(result.stage),
            contract=contract,
            result=result,
            original_request_summary=session.request,
            approved_prd_summary=_approved_prd_summary(summary=summary, result=result),
            approved_acceptance_matrix=_load_acceptance_matrix(args.acceptance_matrix),
        )
    except OpenAISandboxJudgeUnavailable as exc:
        raise SystemExit(str(exc))

    return (
        _gate_result_from_evaluation(evaluation),
        evaluation.result,
        {
            "decision": _gate_decision_to_dict(evaluation.decision),
            "judge_result": _judge_result_to_dict(evaluation.judge_result),
        },
    )


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


def _print_judge_payload(payload: dict[str, object] | None) -> None:
    if payload is None:
        return
    decision = payload["decision"]
    judge_result = payload["judge_result"]
    if isinstance(decision, dict):
        print(f"decision_outcome: {decision['outcome']}")
    if isinstance(judge_result, dict):
        print(f"judge_verdict: {judge_result['verdict']}")
        print(f"judge_confidence: {judge_result['confidence']}")


def _handle_judge_stage_result(args: argparse.Namespace) -> int:
    from .gate_evaluator import GateEvaluator, NoopJudge
    from .openai_sandbox_judge import OpenAISandboxJudge, OpenAISandboxJudgeUnavailable
    from .stage_policies import default_policy_registry

    store = StateStore(args.state_root)
    summary = store.load_workflow_summary(args.session_id)

    if args.run_id:
        run = store.load_stage_run(args.run_id)
    else:
        expected_stage = _expected_submission_stage(summary)
        if expected_stage is None:
            raise SystemExit(f"Cannot judge a stage result while workflow is waiting in {summary.current_state}.")
        run = store.active_stage_run(args.session_id, stage=expected_stage)
        if run is None:
            raise SystemExit(f"No active stage run for {expected_stage}.")

    if run.session_id != args.session_id:
        raise SystemExit("Stage run session_id does not match --session-id.")
    if not run.candidate_bundle_path:
        raise SystemExit(f"Stage run {run.run_id} has no submitted candidate bundle.")

    result = StageResultEnvelope.from_dict(json.loads(Path(run.candidate_bundle_path).read_text()))
    contract = build_stage_contract(
        repo_root=args.repo_root,
        state_store=store,
        session_id=args.session_id,
        stage=run.stage,
    )
    policy = default_policy_registry().get(run.stage)
    session = store.load_session(args.session_id)
    acceptance_matrix = _load_acceptance_matrix(args.acceptance_matrix)
    judge = (
        OpenAISandboxJudge(
            model=args.model,
            docker_image=args.docker_image,
            api_key=args.openai_api_key,
            base_url=args.openai_base_url,
            proxy_url=args.openai_proxy_url,
            user_agent=args.openai_user_agent,
            oa_header=_resolve_openai_oa_header(args),
        )
        if args.judge == "openai-sandbox"
        else NoopJudge()
    )

    try:
        evaluation = GateEvaluator(judge=judge).evaluate(
            session=session,
            policy=policy,
            contract=contract,
            result=result,
            original_request_summary=session.request,
            approved_prd_summary=_approved_prd_summary(summary=summary, result=result),
            approved_acceptance_matrix=acceptance_matrix,
        )
    except OpenAISandboxJudgeUnavailable as exc:
        raise SystemExit(str(exc))

    payload = {
        "session_id": args.session_id,
        "run_id": run.run_id,
        "stage": run.stage,
        "judge": args.judge,
        "hard_gate_result": evaluation.hard_gate_result.to_dict(),
        "decision": _gate_decision_to_dict(evaluation.decision),
        "judge_result": _judge_result_to_dict(evaluation.judge_result),
    }
    if args.print_context and evaluation.judge_context is not None:
        payload["judge_context"] = evaluation.judge_context.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _resolve_openai_oa_header(args: argparse.Namespace) -> str:
    return args.openai_oa or args.openai_user_agent


def _handle_record_human_decision(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    session = store.load_session(args.session_id)
    if session.initiator == "agent":
        raise SystemExit(
            "Human decisions are reserved for human-initiated sessions. "
            "Agent sessions must wait for a human operator to intervene."
        )
    summary = store.load_workflow_summary(args.session_id)
    updated_summary = StageMachine().apply_human_decision(
        summary=summary,
        decision=args.decision,
        target_stage=args.target_stage,
    )
    store.save_workflow_summary(session, updated_summary)
    execution_context_path = _save_next_execution_context_if_needed(
        args=args,
        store=store,
        session=session,
        summary=updated_summary,
    )
    store.set_human_decision(args.session_id, updated_summary.human_decision)
    store.record_event(
        args.session_id,
        kind="workflow_state_changed",
        stage=updated_summary.current_stage,
        state=updated_summary.current_state,
        actor="runtime",
        status=updated_summary.human_decision,
        message=(
            f"Workflow moved to {updated_summary.current_stage} / "
            f"{updated_summary.current_state} after human decision."
        ),
    )
    _print_summary(updated_summary)
    if execution_context_path is not None:
        print(f"execution_context: {execution_context_path}")
    return 0


def _save_next_execution_context_if_needed(
    *,
    args: argparse.Namespace,
    store: StateStore,
    session,
    summary: WorkflowSummary,
) -> Path | None:
    if summary.current_state in RUN_REQUIREMENT_STAGE_ORDER:
        stage = summary.current_state
        contract = build_stage_contract(
            repo_root=args.repo_root,
            state_store=store,
            session_id=args.session_id,
            stage=stage,
        )
        context = build_stage_execution_context(
            repo_root=args.repo_root,
            state_store=store,
            session_id=args.session_id,
            stage=stage,
            contract=contract,
        )
        execution_context_path = store.save_execution_context(context)
        summary.artifact_paths["execution_context"] = str(execution_context_path)
        store.save_workflow_summary(session, summary)
        return execution_context_path
    return None


def _handle_record_feedback(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    session = None
    updated_summary = None
    if args.apply_rework:
        session = store.load_session(args.session_id)
        summary = store.load_workflow_summary(args.session_id)
        updated_summary = StageMachine().apply_human_decision(
            summary=summary,
            decision="rework",
            target_stage=args.target_stage,
        )

    finding = Finding(
        source_stage=args.source_stage,
        target_stage=args.target_stage,
        issue=args.issue,
        severity=args.severity,
        lesson=args.lesson,
        proposed_context_update=args.context_update,
        proposed_skill_update=args.skill_update,
        evidence=args.evidence,
        evidence_kind=args.evidence_kind,
        required_evidence=list(args.required_evidence),
        completion_signal=args.completion_signal,
    )
    feedback_path = store.record_feedback(args.session_id, finding)
    print(f"recorded_feedback: {feedback_path}")
    if updated_summary is not None and session is not None:
        store.save_workflow_summary(session, updated_summary)
        store.set_human_decision(args.session_id, updated_summary.human_decision)
        store.record_event(
            args.session_id,
            kind="workflow_state_changed",
            stage=updated_summary.current_stage,
            state=updated_summary.current_state,
            actor="human",
            status=updated_summary.human_decision,
            message=(
                f"Workflow moved to {updated_summary.current_stage} / "
                f"{updated_summary.current_state} after feedback-triggered rework."
            ),
        )
        _print_summary(updated_summary)
    return 0


def _handle_board_snapshot(args: argparse.Namespace) -> int:
    if not args.all_workspaces:
        raise SystemExit("board-snapshot currently requires --all-workspaces.")
    print(json.dumps(build_board_snapshot(), indent=2))
    return 0


def _handle_serve_board(args: argparse.Namespace) -> int:
    if not args.all_workspaces:
        raise SystemExit("serve-board currently requires --all-workspaces.")
    from .web_server import run_console_server

    print(f"poll_interval_seconds: {args.poll_interval}")
    run_console_server(
        host=args.host,
        port=args.port,
        default_route="/projects",
    )
    return 0


def _handle_review(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    print(store.read_review(session_id=args.session_id))
    return 0


def _handle_panel_snapshot(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    session_id = args.session_id or store.latest_session_id()
    if not session_id:
        raise SystemExit("No workflow session exists yet.")

    print(json.dumps(build_panel_snapshot(store, session_id, repo_root=args.repo_root), indent=2))
    return 0


def _handle_status(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    session_id = args.session_id or store.latest_session_id()
    if not session_id:
        raise SystemExit("No workflow session exists yet.")

    snapshot = build_panel_snapshot(store, session_id, repo_root=args.repo_root)
    overview = snapshot["overview"]
    print(f"project: {overview['project']}")
    print(f"role: {overview['role']}")
    print(f"status: {overview['status']}")
    print(f"detail: {overview['detail']}")
    print(f"session_id: {session_id}")
    print(f"status_path: {store.status_path(session_id)}")
    print(f"panel: agent-team panel --session-id {session_id}")
    return 0


def _handle_panel(args: argparse.Namespace) -> int:
    from .web_server import run_console_server

    store = StateStore(args.state_root)
    run_console_server(
        store=store,
        default_session_id=args.session_id,
        repo_root=args.repo_root,
        host=args.host,
        port=args.port,
        open_browser=args.open_browser,
        default_route="/projects",
    )
    return 0


def _print_summary(summary: WorkflowSummary) -> None:
    print(f"session_id: {summary.session_id}")
    print(f"current_state: {summary.current_state}")
    print(f"current_stage: {summary.current_stage}")
    print(f"acceptance_status: {summary.acceptance_status}")
    print(f"human_decision: {summary.human_decision}")


def _load_acceptance_matrix(path: Path | None) -> list[dict[str, object]]:
    if path is None:
        return []
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise SystemExit("--acceptance-matrix must point to a JSON array.")
    return [dict(item) for item in payload]


def _approved_prd_summary(*, summary: WorkflowSummary, result: StageResultEnvelope) -> str:
    if result.stage == "Product" and result.artifact_name == "prd.md":
        return result.artifact_content[:4000]
    prd_path = summary.artifact_paths.get("product") or summary.artifact_paths.get("prd")
    if prd_path and Path(prd_path).exists():
        return Path(prd_path).read_text()[:4000]
    return ""


def _gate_decision_to_dict(decision) -> dict[str, object]:
    return {
        "outcome": decision.outcome,
        "target_stage": decision.target_stage,
        "reason": decision.reason,
        "missing_outputs": list(decision.missing_outputs),
        "missing_evidence": list(decision.missing_evidence),
        "findings": [finding.to_dict() for finding in decision.findings],
        "judge_verdict": decision.judge_verdict,
        "judge_confidence": decision.judge_confidence,
        "judge_trace_id": decision.judge_trace_id,
        "derived_status": decision.derived_status,
    }


def _judge_result_to_dict(judge_result) -> dict[str, object] | None:
    if judge_result is None:
        return None
    return {
        "verdict": judge_result.verdict,
        "target_stage": judge_result.target_stage,
        "confidence": judge_result.confidence,
        "reasons": list(judge_result.reasons),
        "missing_evidence": list(judge_result.missing_evidence),
        "findings": [finding.to_dict() for finding in judge_result.findings],
        "trace_id": judge_result.trace_id,
    }


def _expected_submission_stage(summary: WorkflowSummary) -> str | None:
    if summary.current_state in {"Intake", "ProductDraft"}:
        return "Product"
    if summary.current_state == "TechPlan":
        return "TechPlan"
    if summary.current_state == "Dev":
        return "Dev"
    if summary.current_state == "QA":
        return "QA"
    if summary.current_state == "Acceptance":
        return "Acceptance"
    return None


def _should_refresh_workspace_metadata(command: str) -> bool:
    return command not in {"board-snapshot", "serve-board"}
