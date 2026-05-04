# Changelog

## [Unreleased]

## [0.2.0b6] - 2026-05-03

- Corrected README offline smoke-test examples to use the published `--executor dry-run` option.

## [0.2.0b5] - 2026-05-03

- Fixed the release installer so fresh installs can resolve runtime dependencies from PyPI.
- Documented that the installer needs network access to GitHub Releases and PyPI.

## [0.2.0b4] - 2026-05-03

- Removed the legacy project-local Codex bridge initialization path; use `init`, `dev`, or `run-requirement` directly.
- Replaced the separate `init-state` and `init-project-structure` commands with one user-facing `init` command.
- Added the interactive `run-requirement --auto` flow for driving TechPlan, Dev, QA, and Acceptance after Product approval.
- Documented the release installer path for trying Agent Team in a real project.

## [0.2.0b3] - 2026-04-26

- Fixed the packaged global `agent-team-run.sh` helper so it runs against the current workspace repo root instead of requiring repo-local role directories or switching into the runtime vendor checkout.

## [0.2.0b2] - 2026-04-26

- Fixed generated project-local agents so they use packaged role context and no longer require repo-local Product/Dev/QA/Acceptance role directories.

## [0.2.0b1] - 2026-04-26

- Added policy-driven stage evaluation with sandbox judge support.
- Added stage execution context handoff for downstream development agents.
- Added runtime observability and board/panel support improvements.
- Added OpenAI Agents SDK sandbox judge configuration support.

## [0.1.0] - 2026-04-19

- Added the first GitHub-Releases-only distribution contract for Agent Team.
- Added a version-pinned shell installer and checksum-verified release artifacts.
