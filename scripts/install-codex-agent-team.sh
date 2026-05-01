#!/usr/bin/env bash
set -euo pipefail

if ! command -v git >/dev/null 2>&1; then
  echo "git is required to install Agent Team runtime" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CODEX_HOME_DIR="${CODEX_HOME:-${HOME}/.codex}"
VENDOR_ROOT="${CODEX_HOME_DIR}/vendor"
VENDOR_DIR="${AGENT_TEAM_VENDOR_DIR:-${VENDOR_ROOT}/agent-team}"
REPO_SOURCE="${AGENT_TEAM_REPO_SOURCE:-}"
REPO_URL="${AGENT_TEAM_REPO_URL:-https://github.com/ZHOUKAILIAN/agent-team-runtime.git}"

mkdir -p "${VENDOR_ROOT}"

if [[ -n "${REPO_SOURCE}" ]]; then
  rm -rf "${VENDOR_DIR}"
  mkdir -p "${VENDOR_DIR}"
  cp -R "${REPO_SOURCE}/." "${VENDOR_DIR}/"
elif [[ -d "${VENDOR_DIR}/.git" ]]; then
  git -C "${VENDOR_DIR}" fetch --depth 1 origin main
  git -C "${VENDOR_DIR}" checkout -B main FETCH_HEAD
else
  git clone --depth 1 "${REPO_URL}" "${VENDOR_DIR}"
fi

echo "Installed vendored Agent Team runtime to ${VENDOR_DIR}"
