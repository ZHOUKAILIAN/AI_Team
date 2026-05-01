#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: agent-team-run.sh '<raw user message>'" >&2
  exit 1
fi

RAW_MESSAGE="$*"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
AGENT_TEAM_EXECUTOR="${AGENT_TEAM_EXECUTOR:-codex-exec}"

AGENT_TEAM_ARGS=(
  --repo-root "${REPO_ROOT}"
  run-requirement
  --message "${RAW_MESSAGE}"
  --executor "${AGENT_TEAM_EXECUTOR}"
)

if [[ -n "${AGENT_TEAM_EXECUTOR_COMMAND:-}" ]]; then
  AGENT_TEAM_ARGS+=(--executor-command "${AGENT_TEAM_EXECUTOR_COMMAND}")
fi
if [[ -n "${AGENT_TEAM_AUTO_APPROVE_PRODUCT:-}" ]]; then
  AGENT_TEAM_ARGS+=(--auto-approve-product)
fi
if [[ -n "${AGENT_TEAM_AUTO_FINAL_DECISION:-}" ]]; then
  AGENT_TEAM_ARGS+=(--auto-final-decision "${AGENT_TEAM_AUTO_FINAL_DECISION}")
fi
if [[ -n "${AGENT_TEAM_JUDGE:-}" ]]; then
  AGENT_TEAM_ARGS+=(--judge "${AGENT_TEAM_JUDGE}")
fi
if [[ -n "${AGENT_TEAM_CODEX_MODEL:-}" ]]; then
  AGENT_TEAM_ARGS+=(--codex-model "${AGENT_TEAM_CODEX_MODEL}")
fi
if [[ -n "${AGENT_TEAM_CODEX_SANDBOX:-}" ]]; then
  AGENT_TEAM_ARGS+=(--codex-sandbox "${AGENT_TEAM_CODEX_SANDBOX}")
fi
if [[ -n "${AGENT_TEAM_CODEX_APPROVAL_POLICY:-}" ]]; then
  AGENT_TEAM_ARGS+=(--codex-approval-policy "${AGENT_TEAM_CODEX_APPROVAL_POLICY}")
fi

cd "${REPO_ROOT}"
if [[ -f "${REPO_ROOT}/agent_team/cli.py" ]]; then
  python3 -m agent_team "${AGENT_TEAM_ARGS[@]}"
elif command -v agent-team >/dev/null 2>&1; then
  agent-team "${AGENT_TEAM_ARGS[@]}"
else
  python3 -m agent_team "${AGENT_TEAM_ARGS[@]}"
fi
