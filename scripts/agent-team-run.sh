#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: agent-team-run.sh '<raw user message>'" >&2
  exit 1
fi

RAW_MESSAGE="$*"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"
if command -v agent-team >/dev/null 2>&1; then
  agent-team --repo-root "${REPO_ROOT}" start-session --message "${RAW_MESSAGE}"
else
  python3 -m agent_team --repo-root "${REPO_ROOT}" start-session --message "${RAW_MESSAGE}"
fi
