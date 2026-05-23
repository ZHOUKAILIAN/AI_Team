# Changelog

## [Unreleased]

## [0.2.0b11] - 2026-05-23

- Added human-friendly `agt continue` numbered menus, feedback templates, short action commands, and lightweight TTY loading.
- Defaulted Codex CLI runs to ephemeral sessions while keeping persistent resume as an explicit compatibility option.
- Improved Codex output recovery, timeout cleanup, stale blocked-reason handling, and mandatory workflow closure stages.
- Added service-health verification profile support with required health-contract, in-process, and runtime-capability evidence.
- Added GovernanceReview auditing for service-health evidence and real HTTP coverage gaps.
- Reduced SessionHandoff cross-session context contamination by isolating handoff context to current-session facts.

## [0.2.0b10] - 2026-05-11

- Added `agent-team update` for safe project-level Agent Team configuration upgrades.
- Added dry-run previews, missing role template backfill, doc-map modernization, and opt-in deprecated role cleanup for existing projects.

## [0.2.0b9] - 2026-05-11

- Added runtime worktree change detection for each stage so CLI output can show which files a stage changed.
- Enforced Simplified Chinese for human-readable stage artifacts, reports, summaries, findings, and handoff notes.

## [0.2.0b8] - 2026-05-09

- Simplified CLI from 21 commands to 9: removed `start-session`, `resume`, `current-stage`, `step`, `build-stage-contract`, `build-execution-context`, `acquire-stage-run`, `submit-stage-result`, `judge-stage-result`, `board-snapshot`, `serve-board`, `panel-snapshot`.
- Merged `current-stage` + `step` → `status --verbose`; `panel-snapshot` → `panel --json`; `judge-stage-result` → `verify-stage-result --dry-run`.

## [0.2.0b7] - 2026-05-04

- Clarified packaged role skills so stage workers produce artifact content and the workflow runner persists session artifacts.

## [0.2.0b6] - 2026-05-03

- Corrected README offline smoke-test examples to use the published `--executor dry-run` option.

## [0.2.0b5] - 2026-05-03

- Fixed the release installer so fresh installs can resolve runtime dependencies from PyPI.
- Documented that the installer needs network access to GitHub Releases and PyPI.

## [0.2.0b4] - 2026-05-03

- Removed the legacy project-local Codex bridge initialization path; use `init`, `dev`, or `run-requirement` directly.
- Replaced the separate `init-state` and `init-project-structure` commands with one user-facing `init` command.
- Added the interactive `run-requirement --auto` flow for driving Dev technical planning, Dev implementation, QA, and Acceptance after Product approval.
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
