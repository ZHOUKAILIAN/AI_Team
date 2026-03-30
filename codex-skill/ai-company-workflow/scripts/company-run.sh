#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: company-run.sh '<raw user message>'" >&2
  exit 2
fi

RAW_MESSAGE="$1"
CODEX_HOME_DIR="${CODEX_HOME:-${HOME}/.codex}"
VENDOR_DIR="${AI_TEAM_VENDOR_DIR:-${CODEX_HOME_DIR}/vendor/ai-team}"

if [[ -f "./ai_company/cli.py" && -d "./Product" && -d "./Dev" && -d "./QA" && -d "./Acceptance" ]]; then
  RUNTIME_DIR="$(pwd)"
elif [[ -f "${VENDOR_DIR}/ai_company/cli.py" && -d "${VENDOR_DIR}/Product" ]]; then
  RUNTIME_DIR="${VENDOR_DIR}"
else
  echo "AI Company runtime not found in the current workspace or ${VENDOR_DIR}" >&2
  exit 1
fi

cd "${RUNTIME_DIR}"
python3 -m ai_company start-session --message "${RAW_MESSAGE}"
