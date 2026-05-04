---
name: techplan
version: 1.0.0
description: Use when Agent Team is drafting or revising the TechPlan stage for the active workflow session.
---

# TechPlan Capability

## Goal

Convert the approved Product handoff into a concrete technical implementation plan that Dev can execute without guessing.

TechPlan owns implementation approach, affected modules, dependencies, implementation steps, risks, and testing strategy. TechPlan does not implement code, verify the implementation, or advance the workflow past its own approval gate.

## Required Inputs

- `session_id`
- `artifact_dir`
- `workflow_summary.md`
- the approved `prd.md`
- any existing `technical_plan.md` or human revision requests for the current round
- repository structure or current codebase context when available

## Required Output

TechPlan produces `technical_plan.md`; the workflow runner persists it in the active session artifact directory.

The technical plan must cover:
- implementation approach
- affected modules
- dependencies
- implementation steps
- risks
- testing strategy
- clarifying questions

## Boundaries

- TechPlan must not modify repository source code.
- TechPlan must not skip Product approval.
- TechPlan must not auto-advance into Dev.
- TechPlan must not replace QA or Acceptance.

## Completion Signals

- `technical_plan.md` exists in the active session artifact directory.
- `technical_plan.md` contains concrete implementation steps and a testing strategy.
- The workflow summary or handoff response clearly says the session is waiting for technical plan approval.
