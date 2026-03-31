from __future__ import annotations

import argparse
from pathlib import Path

from .backend import DeterministicBackend
from .intake import extract_request_from_message
from .orchestrator import WorkflowOrchestrator
from .state import StateStore


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.repo_root = args.repo_root.resolve()
    args.state_root = (args.state_root or (args.repo_root / ".ai_company_state")).resolve()
    return args.handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai_company",
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

    review_parser = subparsers.add_parser("review", help="Print the latest or a selected review.")
    review_parser.add_argument("--session-id", help="Specific session ID to inspect.")
    review_parser.set_defaults(handler=_handle_review)

    return parser


def _handle_init_state(args: argparse.Namespace) -> int:
    store = StateStore(args.state_root)
    store.ensure_layout()
    print(f"Initialized workflow state at {args.state_root}")
    return 0


def _handle_run(args: argparse.Namespace) -> int:
    return _execute_workflow(
        repo_root=args.repo_root,
        state_root=args.state_root,
        request=args.request,
        print_review=args.print_review,
    )


def _handle_agent_run(args: argparse.Namespace) -> int:
    request = extract_request_from_message(args.message)
    if not request:
        raise SystemExit("Unable to extract a workflow request from --message.")

    return _execute_workflow(
        repo_root=args.repo_root,
        state_root=args.state_root,
        request=request,
        print_review=args.print_review,
    )


def _handle_start_session(args: argparse.Namespace) -> int:
    request = extract_request_from_message(args.message) or args.message.strip()
    if not request:
        raise SystemExit("Unable to extract a workflow request from --message.")

    store = StateStore(args.state_root)
    session = store.create_session(request, raw_message=args.message)
    summary_path = store.workflow_summary_path(session.session_id)

    print(f"session_id: {session.session_id}")
    print(f"artifact_dir: {session.artifact_dir}")
    print(f"summary_path: {summary_path}")
    return 0


def _execute_workflow(
    *,
    repo_root: Path,
    state_root: Path,
    request: str,
    print_review: bool,
) -> int:
    store = StateStore(state_root)
    orchestrator = WorkflowOrchestrator(
        repo_root=repo_root,
        state_store=store,
        backend=DeterministicBackend(),
    )
    result = orchestrator.run(request=request)
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
