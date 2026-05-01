#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"
if command -v agent-team >/dev/null 2>&1; then
  agent-team --repo-root "${REPO_ROOT}" codex-init
else
  python3 -m agent_team --repo-root "${REPO_ROOT}" codex-init
fi
