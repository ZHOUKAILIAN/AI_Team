from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from .backend import DeterministicBackend
from .gatekeeper import evaluate_candidate
from .harness_paths import default_state_root
from .intake import parse_intake_message
from .models import Finding, StageResultEnvelope, WorkflowSummary
from .orchestrator import WorkflowOrchestrator
from .project_scaffold import scaffold_project_codex_files
from .stage_contracts import build_stage_contract
from .stage_machine import StageMachine
from .state import StageRunStateError, StateStore


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.repo_root = args.repo_root.resolve()
    args.state_root = (
        args.state_root.resolve()
        if args.state_root is not None
        else default_state_root(repo_root=args.repo_root).resolve()
    )
    return args.handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-team",
        description=(
            "AI_Team single-session workflow CLI. Prefer start-session for the real skill-driven workflow; "
            "run/agent-run are deterministic demo commands."
        ),
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--state-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-state", help="Create the workflow state directories.")
    init_parser.set_defaults(handler=_handle_init_state)

    codex_init_parser = subparsers.add_parser(
        "codex-init",
        help="Generate project-local Codex workflow files and initialize local AI_Team state.",
        description=(
            "Generate project-local Codex workflow files and initialize local AI_Team state. "
            "Use this once per clone before triggering the local AI_Team run skill."
        ),
    )
    codex_init_parser.set_defaults(handler=_handle_codex_init)

    run_parser = subparsers.add_parser(
        "run",
        help=(
            "Demo command: execute the deterministic workflow session from an explicit request "
            "(real workflow entrypoint: start-session)."
        ),
        description=(
            "Demo command: execute the deterministic workflow session from an explicit request. "
            "For the real skill-driven workflow, use start-session."
        ),
    )
    run_parser.add_argument("--request", required=True, help="Raw feature or process request.")
    run_parser.add_argument(
        "--print-review",
        action="store_true",
        help="Print the generated session review after the run completes.",
    )
    run_parser.set_defaults(handler=_handle_run)

    start_session_parser = subparsers.add_parser(
        "start-session",
        help=(
            "Create a session scaffold for the single-session AI_Team workflow. "
            "Preferred entrypoint for the real skill-driven workflow."
        ),
        description=(
            "Create a session scaffold for the single-session AI_Team workflow. "
            "Preferred entrypoint for the real skill-driven workflow."
        ),
    )
    start_session_parser.add_argument("--message", required=True, help="Raw user message for session intake.")
    start_session_parser.set_defaults(handler=_handle_start_session)

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
    verify_result_parser.set_defaults(handler=_handle_verify_stage_result)

    human_decision_parser = subparsers.add_parser(
        "record-human-decision",
        help="Record a human workflow decision for a wait state.",
    )
    human_decision_parser.add_argument("--session-id", required=True, help="Existing workflow session ID.")
    human_decision_parser.add_argument("--decision", required=True, help="One of go, no-go, rework.")
    human_decision_parser.add_argument("--target-stage", help="Required for rework decisions from acceptance.")
    human_decision_parser.set_defaults(handler=_handle_record_human_decision)

    agent_run_parser = subparsers.add_parser(
        "agent-run",
        help=(
            "Demo command: execute the deterministic workflow session from a raw user message "
            "(real workflow entrypoint: start-session)."
        ),
        description=(
            "Demo command: execute the deterministic workflow session from a raw user message. "
            "For the real skill-driven workflow, use start-session."
        ),
    )
    agent_run_parser.add_argument("--message", required=True, help="Raw user message for the agent to process.")
    agent_run_parser.add_argument(
        "--print-review",
        action="store_true",
        help="Print the generated session review after the run completes.",
    )
    agent_run_parser.set_defaults(handler=_handle_agent_run)

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
    feedback_parser.set_defaults(handler=_handle_record_feedback)

    review_parser = subparsers.add_parser("review", help="Print the latest or a selected review.")
    review_parser.add_argument("--session-id", help="Specific session ID to inspect.")
    review_parser.set_defaults(handler=_handle_review)

    return parser


def _handle_init_state(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    store.ensure_layout()
    print(f"Initialized workflow state at {args.state_root}")
    return 0


def _handle_codex_init(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    store.ensure_layout()
    written_paths = scaffold_project_codex_files(args.repo_root)

    print(f"state_root: {args.state_root}")
    print(f"project_root: {args.repo_root}")
    print(f"agents_dir: {args.repo_root / '.codex' / 'agents'}")
    print(f"run_skill: {args.repo_root / '.agents' / 'skills' / 'ai-team-run' / 'SKILL.md'}")
    print(f"generated_files: {len(written_paths)}")
    print("recommended_context: open Codex at the project root before using the local AI_Team run skill")
    print("recommended_run_entry: $ai-team-run")
    print(f"manual_init_fallback: {args.repo_root / 'scripts' / 'company-init.sh'}")
    print(f"manual_run_fallback: {args.repo_root / 'scripts' / 'company-run.sh'} \"<your message>\"")
    return 0


def _handle_run(args: argparse.Namespace) -> int:
    intake = parse_intake_message(args.request)
    return _execute_workflow(
        repo_root=args.repo_root,
        state_root=args.state_root,
        request=intake.request,
        contract=intake.contract,
        print_review=args.print_review,
    )


def _handle_agent_run(args: argparse.Namespace) -> int:
    intake = parse_intake_message(args.message)
    if not intake.request:
        raise SystemExit("Unable to extract a workflow request from --message.")

    return _execute_workflow(
        repo_root=args.repo_root,
        state_root=args.state_root,
        request=intake.request,
        contract=intake.contract,
        print_review=args.print_review,
    )


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
    )
    summary_path = store.workflow_summary_path(session.session_id)

    print(f"session_id: {session.session_id}")
    print(f"artifact_dir: {session.artifact_dir}")
    print(f"summary_path: {summary_path}")
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

    if summary.current_state in {"WaitForCEOApproval", "WaitForHumanDecision"}:
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
    print(json.dumps(contract.to_dict(), indent=2))
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
    gate_result, normalized_result = evaluate_candidate(
        session=store.load_session(args.session_id),
        contract=contract,
        result=result,
        acceptance_contract=store.load_acceptance_contract(args.session_id),
    )

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
    if gate_result.reason:
        print(f"gate_reason: {gate_result.reason}")
    _print_summary(updated_summary)
    return 1


def _handle_record_human_decision(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    session = store.load_session(args.session_id)
    summary = store.load_workflow_summary(args.session_id)
    updated_summary = StageMachine().apply_human_decision(
        summary=summary,
        decision=args.decision,
        target_stage=args.target_stage,
    )
    store.save_workflow_summary(session, updated_summary)
    store.set_human_decision(args.session_id, updated_summary.human_decision)
    _print_summary(updated_summary)
    return 0


def _handle_record_feedback(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
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
    return 0


def _execute_workflow(
    *,
    repo_root: Path,
    state_root: Path,
    request: str,
    contract,
    print_review: bool,
) -> int:
    store = StateStore(state_root)
    orchestrator = WorkflowOrchestrator(
        repo_root=repo_root,
        state_store=store,
        backend=DeterministicBackend(),
    )
    result = orchestrator.run(request=request, contract=contract)
    print(f"session_id: {result.session_id}")
    print(f"acceptance_status: {result.acceptance_status}")
    print(f"review_path: {result.review_path}")

    if print_review:
        print("")
        print(result.review_path.read_text())
    return 0


def _handle_review(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    print(store.read_review(session_id=args.session_id))
    return 0


def _print_summary(summary: WorkflowSummary) -> None:
    print(f"session_id: {summary.session_id}")
    print(f"current_state: {summary.current_state}")
    print(f"current_stage: {summary.current_stage}")
    print(f"acceptance_status: {summary.acceptance_status}")
    print(f"human_decision: {summary.human_decision}")


def _expected_submission_stage(summary: WorkflowSummary) -> str | None:
    if summary.current_state in {"Intake", "ProductDraft"}:
        return "Product"
    if summary.current_state == "Dev":
        return "Dev"
    if summary.current_state == "QA":
        return "QA"
    if summary.current_state == "Acceptance":
        return "Acceptance"
    return None
