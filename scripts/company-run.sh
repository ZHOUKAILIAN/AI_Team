#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: company-run.sh '<raw user message>'" >&2
  exit 1
fi

RAW_MESSAGE="$*"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
AI_TEAM_EXECUTOR="${AI_TEAM_EXECUTOR:-codex-exec}"

AI_TEAM_ARGS=(
  --repo-root "${REPO_ROOT}"
  run-requirement
  --message "${RAW_MESSAGE}"
  --executor "${AI_TEAM_EXECUTOR}"
)

if [[ -n "${AI_TEAM_EXECUTOR_COMMAND:-}" ]]; then
  AI_TEAM_ARGS+=(--executor-command "${AI_TEAM_EXECUTOR_COMMAND}")
fi
if [[ -n "${AI_TEAM_AUTO_APPROVE_PRODUCT:-}" ]]; then
  AI_TEAM_ARGS+=(--auto-approve-product)
fi
if [[ -n "${AI_TEAM_AUTO_FINAL_DECISION:-}" ]]; then
  AI_TEAM_ARGS+=(--auto-final-decision "${AI_TEAM_AUTO_FINAL_DECISION}")
fi
if [[ -n "${AI_TEAM_JUDGE:-}" ]]; then
  AI_TEAM_ARGS+=(--judge "${AI_TEAM_JUDGE}")
fi
if [[ -n "${AI_TEAM_CODEX_MODEL:-}" ]]; then
  AI_TEAM_ARGS+=(--codex-model "${AI_TEAM_CODEX_MODEL}")
fi
if [[ -n "${AI_TEAM_CODEX_SANDBOX:-}" ]]; then
  AI_TEAM_ARGS+=(--codex-sandbox "${AI_TEAM_CODEX_SANDBOX}")
fi
if [[ -n "${AI_TEAM_CODEX_APPROVAL_POLICY:-}" ]]; then
  AI_TEAM_ARGS+=(--codex-approval-policy "${AI_TEAM_CODEX_APPROVAL_POLICY}")
fi

cd "${REPO_ROOT}"
if [[ -f "${REPO_ROOT}/ai_company/cli.py" ]]; then
  python3 -m ai_company "${AI_TEAM_ARGS[@]}"
elif command -v ai-team >/dev/null 2>&1; then
  ai-team "${AI_TEAM_ARGS[@]}"
else
  python3 -m ai_company "${AI_TEAM_ARGS[@]}"
fi
