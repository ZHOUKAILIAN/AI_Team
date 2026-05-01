# Changelog

## [Unreleased]

- No unreleased entries yet.

## [0.2.0b3] - 2026-04-26

- Fixed the packaged global `agent-team-run.sh` helper so it runs against the current workspace repo root instead of requiring repo-local role directories or switching into the runtime vendor checkout.

## [0.2.0b2] - 2026-04-26

- Fixed `codex-init` generated agents so they use packaged role context and no longer require repo-local Product/Dev/QA/Acceptance role directories.

## [0.2.0b1] - 2026-04-26

- Added policy-driven stage evaluation with sandbox judge support.
- Added stage execution context handoff for downstream development agents.
- Added runtime observability and board/panel support improvements.
- Added OpenAI Agents SDK sandbox judge configuration support.

## [0.1.0] - 2026-04-19

- Added the first GitHub-Releases-only distribution contract for Agent Team.
- Added a version-pinned shell installer and checksum-verified release artifacts.
