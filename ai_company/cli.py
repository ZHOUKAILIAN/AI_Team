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
        description="Run the Product -> Dev -> QA -> Acceptance workflow with persisted learning.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--state-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-state", help="Create the workflow state directories.")
    init_parser.set_defaults(handler=_handle_init_state)

    run_parser = subparsers.add_parser("run", help="Execute a workflow session.")
    run_parser.add_argument("--request", required=True, help="Raw feature or process request.")
    run_parser.add_argument(
        "--print-review",
        action="store_true",
        help="Print the generated session review after the run completes.",
    )
    run_parser.set_defaults(handler=_handle_run)

    agent_run_parser = subparsers.add_parser(
        "agent-run",
        help="Execute a workflow session from the user's raw natural-language message.",
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
