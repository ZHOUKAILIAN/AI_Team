# Judge Context Gate Evaluator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first local runtime slice for stage policies, judge context compaction, and gate decisions so Agent Team can later plug in OpenAI Agents SDK SandboxAgent for independent judging.

**Architecture:** Keep runtime state control local and deterministic. Add `StagePolicy` as the source of stage standards, `JudgeContextCompact` as the read-only judge input package, and `GateEvaluator` as the merger of hard gates plus judge verdicts. Do not import OpenAI Agents SDK in this slice; expose a small judge interface that a later SandboxAgent adapter can implement.

**Tech Stack:** Python 3.13 dataclasses, `unittest`, existing `agent_team.models`, existing `agent_team.gatekeeper.evaluate_candidate`.

---

### Task 1: Stage Policy Registry

**Files:**
- Create: `agent_team/stage_policies.py`
- Test: `tests/test_stage_policies.py`

- [ ] **Step 1: Write failing tests**

```python
import unittest


class StagePolicyTests(unittest.TestCase):
    def test_default_policy_registry_returns_product_requirements_approval_policy(self) -> None:
        from agent_team.stage_policies import default_policy_registry

        policy = default_policy_registry().get("Product")

        self.assertEqual(policy.stage, "Product")
        self.assertIn("prd.md", policy.required_outputs)
        self.assertEqual(policy.approval_rule, "requires_requirements_approval")
        self.assertIn("explicit_acceptance_criteria", [spec.name for spec in policy.evidence_specs])

    def test_policy_can_compile_to_stage_contract(self) -> None:
        from agent_team.stage_policies import default_policy_registry

        contract = default_policy_registry().build_contract(
            session_id="session-1",
            stage="Dev",
            contract_id="contract-dev",
            input_artifacts={"request": ".agent-team/session/request.md"},
            role_context="Dev role context",
        )

        self.assertEqual(contract.stage, "Dev")
        self.assertEqual(contract.required_outputs, ["implementation.md"])
        self.assertIn("self_verification", contract.evidence_requirements)
        self.assertEqual(contract.role_context, "Dev role context")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_stage_policies`

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_team.stage_policies'`.

- [ ] **Step 3: Implement minimal policy registry**

Create `StagePolicy`, `PolicyRegistry`, and `default_policy_registry()` in `agent_team/stage_policies.py`. Default policies must cover `Product`, `Dev`, `QA`, and `Acceptance`, and compile to the existing `StageContract` model.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_stage_policies`

Expected: OK.

### Task 2: Judge Context Compact

**Files:**
- Create: `agent_team/judge_context.py`
- Test: `tests/test_judge_context.py`

- [ ] **Step 1: Write failing tests**

```python
import unittest


class JudgeContextTests(unittest.TestCase):
    def test_compact_prioritizes_policy_contract_evidence_and_indexes_artifact(self) -> None:
        from agent_team.judge_context import build_judge_context_compact
        from agent_team.models import EvidenceItem, GateResult, StageResultEnvelope
        from agent_team.stage_policies import default_policy_registry

        registry = default_policy_registry()
        policy = registry.get("Acceptance")
        contract = registry.build_contract(
            session_id="session-1",
            stage="Acceptance",
            contract_id="contract-acceptance",
            input_artifacts={"prd": ".agent-team/session/prd.md"},
        )
        result = StageResultEnvelope(
            session_id="session-1",
            stage="Acceptance",
            status="completed",
            artifact_name="acceptance_report.md",
            artifact_content="# Acceptance\nThe UI matches the approved Figma frame.\n" + ("detail\n" * 300),
            contract_id="contract-acceptance",
            evidence=[
                EvidenceItem(
                    name="product_level_validation",
                    kind="artifact",
                    summary="Screenshot and visual diff reviewed.",
                    artifact_path=".agent-team/session/target.png",
                )
            ],
        )
        hard_gate = GateResult(status="PASSED", reason="All gates passed.")

        compact = build_judge_context_compact(
            policy=policy,
            contract=contract,
            result=result,
            hard_gate_result=hard_gate,
            original_request_summary="Restore the Figma UI.",
            approved_prd_summary="Match the approved Figma frame.",
            approved_acceptance_matrix=[
                {
                    "id": "AC-001",
                    "scenario": "Figma restoration",
                    "standard": "UI matches the approved frame.",
                    "required_evidence": ["product_level_validation"],
                    "failure_target": "Dev",
                }
            ],
        )

        payload = compact.to_dict()
        self.assertEqual(payload["stage"], "Acceptance")
        self.assertEqual(payload["hard_gate_result"]["status"], "PASSED")
        self.assertEqual(payload["acceptance_matrix"][0]["id"], "AC-001")
        self.assertEqual(payload["artifact_index"][0]["name"], "acceptance_report.md")
        self.assertLess(len(payload["artifact_index"][0]["summary"]), len(result.artifact_content))
        self.assertEqual(payload["evidence_index"][0]["name"], "product_level_validation")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_judge_context`

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_team.judge_context'`.

- [ ] **Step 3: Implement compact builder**

Create a compact dataclass and `build_judge_context_compact(...)`. Include stage, request summary, approved PRD summary, acceptance matrix, policy, contract, artifact index, evidence index, hard gate result, previous findings, and budget metadata. Summarize long artifact content instead of embedding full text.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_judge_context`

Expected: OK.

### Task 3: Gate Evaluator With Judge Interface

**Files:**
- Create: `agent_team/gate_evaluator.py`
- Test: `tests/test_gate_evaluator.py`

- [ ] **Step 1: Write failing tests**

```python
import unittest


class RecordingJudge:
    def __init__(self, verdict: str, *, target_stage: str | None = None) -> None:
        self.verdict = verdict
        self.target_stage = target_stage
        self.calls = []

    def judge(self, context):
        from agent_team.gate_evaluator import JudgeResult

        self.calls.append(context)
        return JudgeResult(
            verdict=self.verdict,
            target_stage=self.target_stage,
            confidence=0.91,
            reasons=["judge reason"],
        )


class GateEvaluatorTests(unittest.TestCase):
    def test_pass_requires_hard_gate_and_judge_pass(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from agent_team.gate_evaluator import GateEvaluator
        from agent_team.models import EvidenceItem, StageResultEnvelope
        from agent_team.stage_policies import default_policy_registry
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("restore figma")
            registry = default_policy_registry()
            contract = registry.build_contract(
                session_id=session.session_id,
                stage="Acceptance",
                contract_id="contract-acceptance",
                input_artifacts={},
            )
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Acceptance",
                status="completed",
                artifact_name="acceptance_report.md",
                artifact_content="# Acceptance\nLooks good.\n",
                contract_id="contract-acceptance",
                evidence=[
                    EvidenceItem(
                        name="product_level_validation",
                        kind="artifact",
                        summary="Visual evidence reviewed.",
                    )
                ],
            )
            judge = RecordingJudge("pass")

            evaluation = GateEvaluator(judge=judge).evaluate(
                session=session,
                policy=registry.get("Acceptance"),
                contract=contract,
                result=result,
                original_request_summary="Restore figma",
                approved_prd_summary="Match frame",
                approved_acceptance_matrix=[],
            )

        self.assertEqual(evaluation.decision.outcome, "pass")
        self.assertEqual(evaluation.decision.judge_verdict, "pass")
        self.assertEqual(len(judge.calls), 1)

    def test_hard_gate_failure_returns_rework_without_calling_judge(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from agent_team.gate_evaluator import GateEvaluator
        from agent_team.models import StageResultEnvelope
        from agent_team.stage_policies import default_policy_registry
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("restore figma")
            registry = default_policy_registry()
            contract = registry.build_contract(
                session_id=session.session_id,
                stage="Dev",
                contract_id="contract-dev",
                input_artifacts={},
            )
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Dev",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
                contract_id="contract-dev",
                evidence=[],
            )
            judge = RecordingJudge("pass")

            evaluation = GateEvaluator(judge=judge).evaluate(
                session=session,
                policy=registry.get("Dev"),
                contract=contract,
                result=result,
                original_request_summary="Restore figma",
                approved_prd_summary="Match frame",
                approved_acceptance_matrix=[],
            )

        self.assertEqual(evaluation.decision.outcome, "rework")
        self.assertEqual(evaluation.decision.target_stage, "Dev")
        self.assertIn("self_verification", evaluation.decision.missing_evidence)
        self.assertEqual(judge.calls, [])

    def test_judge_rework_overrides_hard_gate_pass(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from agent_team.gate_evaluator import GateEvaluator
        from agent_team.models import EvidenceItem, StageResultEnvelope
        from agent_team.stage_policies import default_policy_registry
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("restore figma")
            registry = default_policy_registry()
            contract = registry.build_contract(
                session_id=session.session_id,
                stage="QA",
                contract_id="contract-qa",
                input_artifacts={},
            )
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="QA",
                status="completed",
                artifact_name="qa_report.md",
                artifact_content="# QA\nNo obvious issue.\n",
                contract_id="contract-qa",
                evidence=[
                    EvidenceItem(
                        name="independent_verification",
                        kind="command",
                        summary="Tests passed.",
                        command="python3 -m unittest",
                        exit_code=0,
                    )
                ],
            )

            evaluation = GateEvaluator(judge=RecordingJudge("rework", target_stage="Dev")).evaluate(
                session=session,
                policy=registry.get("QA"),
                contract=contract,
                result=result,
                original_request_summary="Restore figma",
                approved_prd_summary="Match frame",
                approved_acceptance_matrix=[],
            )

        self.assertEqual(evaluation.decision.outcome, "rework")
        self.assertEqual(evaluation.decision.target_stage, "Dev")
        self.assertEqual(evaluation.decision.judge_verdict, "rework")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_gate_evaluator`

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_team.gate_evaluator'`.

- [ ] **Step 3: Implement evaluator**

Create `JudgeResult`, `GateDecision`, `StageEvaluation`, `NoopJudge`, and `GateEvaluator`. Reuse `evaluate_candidate(...)` for hard gates. Only call judge after hard gate passes. Merge outcomes with fail-closed semantics: hard gate failures rework/block without judge, judge `pass` permits pass, judge `rework` routes rework, judge `blocked` blocks, judge `needs_human` awaits human.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_gate_evaluator`

Expected: OK.

### Task 4: Verification

**Files:**
- No new files.

- [ ] **Step 1: Run targeted tests**

Run: `python3 -m unittest tests.test_stage_policies tests.test_judge_context tests.test_gate_evaluator tests.test_gatekeeper tests.test_stage_contracts`

Expected: OK.

- [ ] **Step 2: Run full suite and record known failure**

Run: `python3 -m unittest discover -s tests`

Expected: Existing worktree-specific failure may remain in `test_status_prints_user_friendly_project_role_and_status`, because it expects `project: agent-team-runtime` while the worktree directory is `orchestration-options-comparison`.

- [ ] **Step 3: Run whitespace check**

Run: `git diff --check`

Expected: no output.

### Self-Review

- Spec coverage: Implements the first local slice for policies, judge compact input, and hard-gate/judge decision merge. Does not implement real OpenAI Agents SDK SandboxAgent adapter yet.
- Placeholder scan: No TBD/TODO placeholders.
- Type consistency: `StagePolicy`, `JudgeContextCompact`, `JudgeResult`, `GateDecision`, and `StageEvaluation` names are consistent across tasks.
