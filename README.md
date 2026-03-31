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
- superpower TDD belongs to Dev (implementation discipline), not QA.
- QA must independently rerun critical verification and cannot accept Dev claims without rerun evidence.
- missing evidence forces blocked.

Contract artifacts (required per session):
- `prd.md`
- `implementation.md`
- `qa_report.md`
- `acceptance_report.md`
- `workflow_summary.md`

Contract entry command for agent-friendly requests:

```bash
python3 -m ai_company start-session --message "<your original message>"
```

*Note: All execution states, session memories, and artifact hand-offs are stored locally in the `.ai_company_state/` directory to keep the workspace clean.*

## Local Runtime And Learning Loop
This repository now includes a runnable local workflow engine. Its workflow metadata aligns with:

`Product -> CEO approval -> Dev <-> QA -> Acceptance -> human Go/No-Go`

Compared with the original document-only workflow, the runtime adds three concrete capabilities:
- **Full traceability**: every stage writes an artifact, journal, findings file, and session metadata.
- **Auditable diffs**: every run generates a `review.md` file with diffs across stage artifacts.
- **Self-improving loop**: downstream findings are written back into `.ai_company_state/memory/<Role>/` as lessons, context patches, and skill patches. Future runs automatically load those overlays into the effective role profile.

### Directory Layout
- `Product/`, `Dev/`, `QA/`, `Acceptance/`, `Ops/`: seed role definitions with `context.md`, `memory.md`, and `SKILL.md`
- `.ai_company_state/sessions/<session_id>/`: per-run journals and review artifacts
- `.ai_company_state/artifacts/<session_id>/`: stage deliverables such as `prd.md`, `implementation.md`, `qa_report.md`, `acceptance_report.md`, and `workflow_summary.md`
- `.ai_company_state/memory/<Role>/`: runtime learning overlays containing `lessons.md`, `context_patch.md`, and `skill_patch.md`

### Commands
Initialize the local state directories:

```bash
python3 -m ai_company init-state
```

Run a full workflow loop (`run` and `agent-run` are deterministic/demo runtime commands):

```bash
python3 -m ai_company run --request "Build a self-improving AI company loop" --print-review
```

Read the latest review:

```bash
python3 -m ai_company review
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

For the authoritative workflow bootstrap path, use:

```bash
python3 -m ai_company start-session --message "<your original message>"
```

### Install As A Codex Skill
If you want to reuse this in future Codex sessions, install the bundled skill from this repository:

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

The installed skill is the trigger/router layer. The actual execution goes through:

```bash
python3 -m ai_company start-session --message "<your original message>"
```

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
2. `Dev` converts the PRD into a technical plan.
3. `QA` checks the handoff quality and emits structured findings when something is missing.
4. `Acceptance` uses those findings to produce the final recommendation for the human Go/No-Go decision.
5. The orchestrator writes the findings back into the target role's runtime learning overlay.
6. The next run automatically loads those learned overlays into the role's effective context, skill, and memory.

### Current Boundary
- The default backend is a deterministic template backend. It is suitable for validating the orchestration model, memory evolution, diff audit, and review flow.
- If you want `Dev` to call a real LLM to modify code, or `QA` to run a browser/test suite, you can replace the backend without rewriting the orchestrator, state store, or learning loop.

---
*Created for efficient autonomous software building using an Agentic AI collaborative model.*
