#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_DIR="${REPO_ROOT}/codex-skill/ai-company-workflow"
CODEX_HOME_DIR="${CODEX_HOME:-${HOME}/.codex}"
TARGET_DIR="${CODEX_HOME_DIR}/skills/ai-company-workflow"

mkdir -p "${TARGET_DIR}"
cp "${SOURCE_DIR}/SKILL.md" "${TARGET_DIR}/SKILL.md"

if [[ -d "${SOURCE_DIR}/scripts" ]]; then
  mkdir -p "${TARGET_DIR}/scripts"
  cp -R "${SOURCE_DIR}/scripts/." "${TARGET_DIR}/scripts/"
fi

echo "Installed ai-company-workflow skill to ${TARGET_DIR}"
