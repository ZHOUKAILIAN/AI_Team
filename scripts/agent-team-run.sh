#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: agent-team-run.sh '<raw user message>'" >&2
  exit 1
fi

RAW_MESSAGE="$*"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
AGT_BIN="${AGT_BIN:-${REPO_ROOT}/packages/cli/dist/index.js}"

AGT_ARGS=(
  run
  "${RAW_MESSAGE}"
  --repo-root "${REPO_ROOT}"
)

if [[ -n "${AGENT_TEAM_PROFILE:-}" ]]; then
  AGT_ARGS+=(--profile "${AGENT_TEAM_PROFILE}")
fi
if [[ -n "${AGENT_TEAM_STATE_ROOT:-}" ]]; then
  AGT_ARGS+=(--state-root "${AGENT_TEAM_STATE_ROOT}")
fi
if [[ -n "${AGENT_TEAM_TASK_WORKTREE:-}" ]]; then
  AGT_ARGS+=(--task-worktree)
fi
if [[ -n "${AGENT_TEAM_HUMAN_GATES:-}" ]]; then
  AGT_ARGS+=(--human-gates)
fi

cd "${REPO_ROOT}"
if [[ -f "${AGT_BIN}" ]]; then
  node "${AGT_BIN}" "${AGT_ARGS[@]}"
elif command -v agt >/dev/null 2>&1; then
  agt "${AGT_ARGS[@]}"
elif command -v agent-team >/dev/null 2>&1; then
  agent-team "${AGT_ARGS[@]}"
else
  echo "agt is not built or installed. Run npm install && npm run build first." >&2
  exit 1
fi
