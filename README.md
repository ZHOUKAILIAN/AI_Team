# One-Person AI Company

**Language Policy**:
This README is available in English and [Chinese (中文)](README_zh.md). However, to maintain optimal performance and consistency for AI collaboration, all internal contexts, memories, and onboarding manuals (`context.md`) within each role's folder are strictly in **English**.

**Repository**: `git@github.com:ZHOUKAILIAN/AI_Team.git`

---

## 🌟 Introduction
Welcome to the **One-Person AI Company**! This repository simulates a complete software tech company architecture, operated by a single person collaborating with AI. By defining clear roles, responsibilities, and workflows, we transform a solo developer into a full-scale, cross-functional product delivery team.

## 🏢 Company Architecture
Our company is divided into five core departments, each with its dedicated persona, tone, and specific responsibilities:

### 1. 📢 Product Manager (`/Product`)
- **Role**: Defines "what to build" and "why".
- **Tone**: Professional, Rigorous, User-Centric, and Excellence-Driven.
- **Responsibilities**: Product Vision & Strategy, Requirement Ownership (PRDs), Value Delivery Management, Cross-Functional Alignment.

### 2. 💻 Software Engineer (`/Dev`)
- **Role**: Transforms product requirements into robust, working software.
- **Tone**: Geeky, Rigorous, Efficient, and Excellence-Driven.
- **Responsibilities**: Technical Implementation, System Architecture & Design, Code Quality, Engineering Excellence.

### 3. 🛡️ QA Engineer (`/QA`)
- **Role**: The ultimate guardian of product quality before delivery.
- **Tone**: Meticulous, Rigorous, Professional, and Zero-Tolerance for Defects.
- **Responsibilities**: Quality Assurance, Risk Mitigation, Test Strategy & Coverage, Defect Management.

### 4. ⚖️ Acceptance Manager (`/Acceptance`)
- **Role**: Acts as the final end-to-end (E2E) verification layer beyond QA, serving as the gatekeeper confirming that the product solves actual business scenarios.
- **Tone**: Holistic, Strict, Objective, and Delivery-Oriented.
- **Responsibilities**: Business Value Validation, Requirement Fulfillment Verification, Release Readiness, Process Integrity.

### 5. 🚀 Operations Manager (`/Ops`)
- **Role**: Drives user growth and ensures post-launch engagement.
- **Tone**: Professional, Innovative, Efficient, and Empathetic.
- **Responsibilities**: User Growth & Engagement, Go-to-Market Strategy, Market Feedback Loop, User Enablement.

## ⚙️ Workflow Contract (Authoritative)
The real workflow contract is:

`Product -> CEO approval -> Dev <-> QA -> Acceptance -> human Go/No-Go`

This means:
- Product creates the requirement package.
- CEO approval is required before Dev starts implementation.
- Dev and QA iterate until critical verification evidence is complete.
- Acceptance provides the final recommendation.
- A human makes the final Go/No-Go decision.

Role boundaries:
- Dev may use its own implementation methodology and self-verification inside Dev, not QA.
- QA must independently rerun critical verification and cannot accept Dev claims without rerun evidence.
- missing evidence forces blocked.

Contract artifacts (required per session):
- `prd.md`
- `implementation.md`
- `qa_report.md`
- `acceptance_report.md`
- `workflow_summary.md`

Recommended entrypoints for normal use:
- preferred Harness-First entrypoint: `python3 -m ai_company start-session --message "<your original message>"`
- inspect the current supervisor state: `python3 -m ai_company current-stage --session-id <session_id>`
- compile a stage contract: `python3 -m ai_company build-stage-contract --session-id <session_id> --stage <stage>`
- optional compatibility bridge: `./scripts/company-init.sh` then `$ai-team-run`

*Note: The default state root is now app-local and workspace-scoped: `$CODEX_HOME/ai-team/workspaces/<workspace_fingerprint>/` (falling back to `~/.codex/ai-team/workspaces/<workspace_fingerprint>/` when `CODEX_HOME` is not set). Use `--state-root` only when you explicitly want to override that default.*

## 🚀 Quick Start
If you want to use the current Harness-First prototype in this repository, the recommended path is:

1. Open Codex or a shell at the project root of this repository.

2. Start a workflow session from the original user request:

```bash
python3 -m ai_company start-session --message "执行这个需求：<your request>"
```

3. Inspect the current stage summary:

```bash
python3 -m ai_company current-stage
```

4. Build the machine-readable contract for the current worker stage:

```bash
python3 -m ai_company build-stage-contract --session-id <session_id> --stage Product
```

5. After the stage work is done, submit a result bundle back to the harness:

```bash
python3 -m ai_company submit-stage-result --session-id <session_id> --bundle /path/to/stage-result.json
```

6. When the workflow stops at a wait state, record the explicit human decision:

```bash
python3 -m ai_company record-human-decision --session-id <session_id> --decision go
```

Compatibility bridge from the project root:

```bash
./scripts/company-init.sh
./scripts/company-run.sh "执行这个需求：<your request>"
```

`company-init.sh` still generates project-local `.codex/` and `.agents/` files on demand and keeps them out of git, but in the Harness-First direction they are treated as a bridge layer rather than the workflow control plane.

## ✅ What This Workflow Can Do
This workflow is designed to run one requirement through a real multi-role handoff instead of collapsing everything into Dev-only self-verification.

It does all of the following:
- The harness owns the current state, current stage, legal transitions, and wait states instead of leaving those decisions to free-form prompts.
- Product writes `prd.md` with explicit acceptance criteria before Dev starts.
- The workflow stops once for CEO approval after Product.
- Dev implements and records its own self-verification plus command evidence in `implementation.md`.
- QA independently reruns critical verification and writes `qa_report.md`.
- QA can automatically send failures back to Dev for rework.
- Acceptance writes `acceptance_report.md` as an AI recommendation only, and actionable `recommended_no_go` / `blocked` outcomes can be routed back to Product or Dev as structured findings.
- Human feedback can be recorded into the same learning loop through `record-feedback`.
- Each worker stage can now receive a machine-readable contract and submit a structured stage-result bundle back to the harness.
- A human still makes the final Go/No-Go decision.

## 🧾 Recording And Storage
Yes, the workflow records every session locally.

Main storage locations:
- `$CODEX_HOME/ai-team/workspaces/<workspace_fingerprint>/artifacts/<session_id>/`: required handoff artifacts such as `prd.md`, `implementation.md`, `qa_report.md`, `acceptance_report.md`, `workflow_summary.md`, plus machine-readable review artifacts like `acceptance_contract.json` and `review_completion.json` when the workflow declares a review contract
- `$CODEX_HOME/ai-team/workspaces/<workspace_fingerprint>/sessions/<session_id>/`: per-stage journals, findings, metadata, and `review.md`
- `$CODEX_HOME/ai-team/workspaces/<workspace_fingerprint>/memory/<Role>/`: learned lessons and patches written back from downstream findings

`workflow_summary.md` is the quickest single-file index for the current session state and artifact paths.

If `CODEX_HOME` is not configured, the runtime falls back to `~/.codex/ai-team/workspaces/<workspace_fingerprint>/`.

## Local Runtime, Harness, And Learning Loop
This repository now includes a runnable local workflow engine. On this branch, the main direction is a Harness-First supervisor running under Codex app. Its workflow metadata aligns with:

`Product -> CEO approval -> Dev <-> QA -> Acceptance -> human Go/No-Go`

Compared with the original document-only workflow, the runtime adds several concrete capabilities:
- **Harness-owned execution control**: the runtime owns `current_state`, `current_stage`, legal transitions, and human-decision wait states.
- **App-local workspace isolation**: workflow state lives under the Codex app state root instead of a repo-local hidden folder.
- **Machine-readable stage handoffs**: workers can read a compiled stage contract and submit a structured stage-result bundle.
- **Full traceability**: every stage writes an artifact, journal, findings file, and session metadata.
- **Auditable diffs**: every run generates a `review.md` file with diffs across stage artifacts.
- **Self-improving loop**: downstream findings are written back into the runtime memory overlay for each role as lessons, context patches, and skill patches. Future runs automatically load those overlays into the effective role profile.
- **Standardized learning overlays**: learned entries store reusable rules and explicit completion signals instead of vague summaries.

### Directory Layout
- `Product/`, `Dev/`, `QA/`, `Acceptance/`, `Ops/`: seed role definitions with `context.md`, `memory.md`, and `SKILL.md`
- `.codex/agents/`: project-local Codex subagents for `Product`, `Dev`, `QA`, and `Acceptance`, generated by `./scripts/company-init.sh`
- `.agents/skills/ai-team-run/`: project-local run skill generated by `./scripts/company-init.sh`; in the Harness-First direction it is a bridge, not the control plane
- `$CODEX_HOME/ai-team/workspaces/<workspace_fingerprint>/sessions/<session_id>/`: per-run journals and review artifacts
- `$CODEX_HOME/ai-team/workspaces/<workspace_fingerprint>/artifacts/<session_id>/`: stage deliverables such as `prd.md`, `implementation.md`, `qa_report.md`, `acceptance_report.md`, `workflow_summary.md`, `acceptance_contract.json`, and review artifacts like `review_completion.json`
- `$CODEX_HOME/ai-team/workspaces/<workspace_fingerprint>/memory/<Role>/`: runtime learning overlays containing `lessons.md`, `context_patch.md`, and `skill_patch.md`

### Commands
The commands below are the current Harness-First maintainer surface. If you use the skill bridge, treat it as a launcher into this harness rather than as the workflow controller.

Initialize the local state directories:

```bash
python3 -m ai_company init-state
```

Initialize the local Codex workflow setup:

```bash
python3 -m ai_company codex-init
```

Start a workflow session from a raw user request:

```bash
python3 -m ai_company start-session --message "执行这个需求：<your request>"
```

Inspect the latest or a specific session stage:

```bash
python3 -m ai_company current-stage --session-id <session_id>
```

Build a machine-readable stage contract:

```bash
python3 -m ai_company build-stage-contract --session-id <session_id> --stage Product
```

Submit a structured stage-result bundle and let the harness advance the state machine:

```bash
python3 -m ai_company submit-stage-result --session-id <session_id> --bundle /path/to/stage-result.json
```

Record a human decision for a wait state:

```bash
python3 -m ai_company record-human-decision --session-id <session_id> --decision go
```

Run a full deterministic/demo workflow loop (`run` and `agent-run` are deterministic/demo runtime commands; they remain compatibility commands):

```bash
python3 -m ai_company run --request "Build a self-improving AI company loop" --print-review
```

Read the latest review:

```bash
python3 -m ai_company review
```

Record human feedback as a structured learning finding:

```bash
python3 -m ai_company record-feedback --session-id <session_id> --source-stage Acceptance --target-stage Dev --issue "<issue>" --lesson "<lesson>" --context-update "<constraint>" --skill-update "<goal>"
```

For page-root visual parity or `<= 0.5px` Figma acceptance, the required evidence bundle is `runtime_screenshot`, `overlay_diff`, and `page_root_recursive_audit`.

The machine-readable native-node policy lives in `ai_company/acceptance_policy.json`; it excludes host-owned nodes such as `wechat_native_capsule` from business diffs and keeps them in the safe-area-avoidance bucket.

When a session declares a review contract, `start-session` persists `acceptance_contract.json` and scaffolds `review_completion.json`. Acceptance cannot close the workflow until `review_completion.json` explicitly says the review is complete and every required artifact/evidence item is covered.

Host-tool changes are blocked by default. If QA or Acceptance would need to restart external tools or mutate local configuration, the workflow must stop and wait for explicit user approval first.

### Project-Scoped Codex Setup
This repository still supports official project-scoped Codex integration. The hidden files are generated locally on demand, and in the Harness-First direction these generated files are an entry bridge, not the source of truth for workflow state:

- `.codex/agents/*.toml`: local subagents for Product, Dev, QA, and Acceptance
- `.agents/skills/ai-team-run/`: local execution skill

Best practice:
- open Codex at the project root
- use the CLI harness as the authoritative control plane
- if needed, run `./scripts/company-init.sh` once per clone to install the local bridge files
- treat `$ai-team-run` as a trigger/router, not as the stage controller

These generated files are ignored by git so a fresh clone stays clean until initialization happens.

Manual shell fallback:

```bash
./scripts/company-init.sh
./scripts/company-run.sh "执行这个需求：做一个支持下游纠偏和自学习的 AI 公司流程"
```

### agent-friendly Mode
If a human is driving from the shell, `run` is fine for deterministic/demo runtime metadata. If an agent receives a natural-language instruction, use `agent-run` and pass the raw message through unchanged (also deterministic/demo runtime metadata):

```bash
python3 -m ai_company agent-run --message "Run this requirement through the AI Company workflow: build a self-improving agent loop" --print-review
```

This layer does two things:
- detects agent-friendly trigger phrases
- extracts the real requirement from the raw message before executing the workflow

Recommended trigger phrases for agents:
- `/company-run ...`
- `执行这个需求：...`
- `按 AI Company 流程跑这个需求：...`
- `按 AI Company 流程执行：...`
- `Run this requirement through the AI Company workflow: ...`

If no trigger prefix matches, `agent-run` falls back to using the entire message as the request.

For the authoritative Harness-First bootstrap path, use:

```bash
python3 -m ai_company start-session --message "<your original message>"
```

### Install As A Codex Skill
If you want to reuse this outside this repository, install the bundled global skill from this repository:

```bash
./scripts/install-codex-skill.sh
```

The installer copies the skill to:

```bash
~/.codex/skills/ai-company-workflow
```

After that, you can tell Codex:
- `/company-run build a self-improving AI company loop`
- `执行这个需求：做一个支持下游纠偏和自学习的 AI 公司流程`

The installed global skill is the trigger/router layer. The user-facing entrypoint remains the skill itself, and in the Harness-First direction the workflow state machine still belongs to `ai_company`, while the skill only handles discovery, bootstrap, and prompt bridging.

### One-Command Global Install
For teammates on another machine, prefer the global installer. It does both:
- installs the skill into `~/.codex/skills/ai-company-workflow`
- vendors the runtime repository into `~/.codex/vendor/ai-team`

If the repository is public, run:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ZHOUKAILIAN/AI_Team/main/scripts/install-codex-ai-team.sh)
```

If the repository is already cloned locally, run:

```bash
./scripts/install-codex-ai-team.sh
```

After installation, the preferred Codex triggers are:
- `/company-run build a self-improving AI company loop`
- `执行这个需求：做一个支持下游纠偏和自学习的 AI 公司流程`

The stable vendored runtime location is:

```bash
~/.codex/vendor/ai-team
```

The installed skill will prefer this helper:

```bash
~/.codex/skills/ai-company-workflow/scripts/company-run.sh "<your original message>"
```

### How The Learning Loop Works
1. `Product` turns the raw request into a PRD with explicit acceptance criteria.
2. `Dev` implements against the PRD and records self-verification plus command evidence in `implementation.md`.
3. `QA` independently reruns critical verification and emits structured findings when something is missing.
4. `Acceptance` uses those findings to produce the final AI recommendation for the human Go/No-Go decision, and actionable no-go outcomes can emit new findings for `Product` or `Dev`.
5. Human feedback can also be normalized into a structured finding through `record-feedback`.
6. The orchestrator writes the findings back into the target role's runtime learning overlay.
7. The next run automatically loads those learned overlays into the role's effective context, skill, and memory.
8. Visual parity findings can declare explicit required evidence such as `runtime_screenshot`, `overlay_diff`, and `page_root_recursive_audit`, so QA and Acceptance do not confuse green tests with final visual sign-off.

### Current Boundary
- This branch implements the first Harness-First vertical slice: app-local state root, explicit stage machine, `current-stage`, `build-stage-contract`, `submit-stage-result`, and `record-human-decision`.
- The default backend is a deterministic template backend. It is suitable for validating the orchestration model, memory evolution, diff audit, and review flow.
- Its `acceptance_status` values are recommendation-only (`recommended_go`, `recommended_no_go`, or `blocked`) and the workflow summary ends at `WaitForHumanDecision`, not final release approval.
- Worker execution is still submitted back through bundle files. Native plugin UX, automatic worker dispatch, and richer resume tooling are future steps.
- If you want `Dev` to call a real LLM to modify code, or `QA` to run a browser/test suite, you can replace the backend without rewriting the orchestrator, state store, or learning loop.

## Documentation & SOP

### Standard Operating Procedure
- **[文档驱动 AI 团队开发 SOP](docs/SOP_简洁版.md)**: Chinese end-to-end operating guide for doc-driven requirement intake, execution, and acceptance.

### Integration with ai-doc-driven-dev
The SOP describes a recommended two-phase workflow:
1. **Phase 1**: Use `ai-doc-driven-dev` to initialize structured documentation.
2. **Phase 2**: Use `AI_Team` to execute the documented requirement with multi-role AI collaboration.

This creates a complete loop: **Documentation -> Execution -> Validation -> Learning**

---
*Created for efficient autonomous software building using an Agentic AI collaborative model.*
