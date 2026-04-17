# AI_Team Enforced Stage Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runtime-owned stage-run lifecycle and gatekeeper so worker submissions cannot directly advance workflow state.

**Architecture:** Keep `StageMachine` as the high-level workflow transition engine, but put a mandatory `StageRunRecord` and `Gatekeeper` between `submit-stage-result` and `StageMachine.advance()`. CLI commands become the control plane: acquire a run, submit a candidate bundle, verify the candidate, then advance only when the run is `PASSED`.

**Tech Stack:** Python 3.13, dataclasses, file-backed JSON state, `unittest`, existing `ai-team` argparse CLI.

---

## File Structure

- Modify: `ai_company/models.py`
  - Add `StageRunRecord` and `GateResult` dataclasses with JSON helpers.
- Modify: `ai_company/state.py`
  - Persist stage-run JSON files under `sessions/<session_id>/stage_runs/`.
  - Add helpers to create active runs, submit candidate bundles, update gate results, load acceptance contracts, and query active/latest runs.
- Create: `ai_company/gatekeeper.py`
  - Evaluate `ContractGate`, `EvidenceGate`, and existing review gates.
  - Return `GateResult` without advancing workflow state.
- Modify: `ai_company/cli.py`
  - Add `step`, `acquire-stage-run`, and `verify-stage-result`.
  - Change `submit-stage-result` to submit only candidate results.
- Modify: `tests/test_state.py`
  - Add state persistence tests for stage-run lifecycle.
- Create: `tests/test_gatekeeper.py`
  - Add gatekeeper unit tests for pass/fail/blocked decisions.
- Modify: `tests/test_cli.py`
  - Update stage submission tests to use acquire-submit-verify.
  - Add CLI lock and step tests.
- Modify: `README.md` and `docs/workflow-specs/2026-04-17-ai-team-enforced-stage-gates-flow.md`
  - Document enforced CLI order after implementation.

---

### Task 1: Stage Run Models And Persistence

**Files:**
- Modify: `ai_company/models.py`
- Modify: `ai_company/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write failing state tests**

Add tests showing a run can be acquired, submitted, and loaded as the active run:

```python
def test_stage_run_lifecycle_persists_active_candidate(self) -> None:
    from ai_company.models import StageResultEnvelope
    from ai_company.state import StateStore

    with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
        store = StateStore(Path(temp_dir))
        session = store.create_session("build an enforced workflow")

        run = store.create_stage_run(
            session_id=session.session_id,
            stage="Product",
            contract_id="contract-product",
            required_outputs=["prd.md"],
            required_evidence=["explicit_acceptance_criteria"],
            worker="codex",
        )

        self.assertEqual(run.state, "RUNNING")
        self.assertEqual(run.attempt, 1)
        self.assertEqual(store.active_stage_run(session.session_id).run_id, run.run_id)

        result = StageResultEnvelope(
            session_id=session.session_id,
            stage="Product",
            status="completed",
            artifact_name="prd.md",
            artifact_content="# PRD\n\n## Acceptance Criteria\n- Works.\n",
            contract_id="contract-product",
            evidence=[
                {
                    "name": "explicit_acceptance_criteria",
                    "kind": "report",
                    "summary": "PRD includes explicit acceptance criteria.",
                }
            ],
        )
        submitted = store.submit_stage_run_result(run.run_id, result)

        self.assertEqual(submitted.state, "SUBMITTED")
        self.assertTrue(Path(submitted.candidate_bundle_path).exists())
        self.assertEqual(store.active_stage_run(session.session_id, stage="Product").state, "SUBMITTED")
```

Add a second test showing active run locking:

```python
def test_create_stage_run_rejects_existing_active_run(self) -> None:
    from ai_company.state import StateStore, StageRunStateError

    with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
        store = StateStore(Path(temp_dir))
        session = store.create_session("build an enforced workflow")
        store.create_stage_run(
            session_id=session.session_id,
            stage="Product",
            contract_id="contract-product",
            required_outputs=["prd.md"],
            required_evidence=["explicit_acceptance_criteria"],
        )

        with self.assertRaises(StageRunStateError):
            store.create_stage_run(
                session_id=session.session_id,
                stage="Product",
                contract_id="contract-product",
                required_outputs=["prd.md"],
                required_evidence=["explicit_acceptance_criteria"],
            )
```

- [ ] **Step 2: Run state tests to verify RED**

Run:

```bash
/tmp/ai-team-runtime-enforced-venv/bin/python -m unittest tests.test_state.StateTests.test_stage_run_lifecycle_persists_active_candidate tests.test_state.StateTests.test_create_stage_run_rejects_existing_active_run
```

Expected: both tests fail because `StageRunRecord`, `StageRunStateError`, and state helpers do not exist.

- [ ] **Step 3: Implement minimal model and state helpers**

Add `GateResult` and `StageRunRecord` to `ai_company/models.py`. Add `StageRunStateError`, `create_stage_run`, `active_stage_run`, `load_stage_run`, `submit_stage_run_result`, and `update_stage_run` to `ai_company/state.py`.

Required semantics:

```text
create_stage_run -> RUNNING
submit_stage_run_result -> SUBMITTED
terminal states -> PASSED, FAILED, BLOCKED
active states -> READY, RUNNING, SUBMITTED, VERIFYING
```

- [ ] **Step 4: Run state tests to verify GREEN**

Run:

```bash
/tmp/ai-team-runtime-enforced-venv/bin/python -m unittest tests.test_state.StateTests.test_stage_run_lifecycle_persists_active_candidate tests.test_state.StateTests.test_create_stage_run_rejects_existing_active_run
```

Expected: both tests pass.

---

### Task 2: Gatekeeper Unit

**Files:**
- Create: `ai_company/gatekeeper.py`
- Modify: `ai_company/state.py`
- Test: `tests/test_gatekeeper.py`

- [ ] **Step 1: Write failing gatekeeper tests**

Create `tests/test_gatekeeper.py` with these behaviors:

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class GatekeeperTests(unittest.TestCase):
    def test_missing_required_evidence_fails_gate(self) -> None:
        from ai_company.gatekeeper import Gatekeeper
        from ai_company.models import StageContract, StageResultEnvelope
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Dev",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
                contract_id="contract-dev",
                evidence=[],
            )
            contract = StageContract(
                session_id=session.session_id,
                stage="Dev",
                contract_id="contract-dev",
                goal="Implement",
                required_outputs=["implementation.md"],
                evidence_requirements=["self_verification"],
            )

            gate = Gatekeeper().evaluate(session=session, contract=contract, result=result, acceptance_contract=None)

            self.assertEqual(gate.status, "FAILED")
            self.assertIn("self_verification", gate.missing_evidence)

    def test_qa_findings_can_pass_stage_run_and_route_later(self) -> None:
        from ai_company.gatekeeper import Gatekeeper
        from ai_company.models import Finding, StageContract, StageResultEnvelope
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="QA",
                status="failed",
                artifact_name="qa_report.md",
                artifact_content="# QA\nRegression found.\n",
                contract_id="contract-qa",
                evidence=[
                    {
                        "name": "independent_verification",
                        "kind": "command",
                        "summary": "QA reran verification.",
                        "command": "python -m unittest",
                        "exit_code": 0,
                    }
                ],
                findings=[Finding(source_stage="QA", target_stage="Dev", issue="Regression found.")],
            )
            contract = StageContract(
                session_id=session.session_id,
                stage="QA",
                contract_id="contract-qa",
                goal="Verify",
                required_outputs=["qa_report.md"],
                evidence_requirements=["independent_verification"],
            )

            gate = Gatekeeper().evaluate(session=session, contract=contract, result=result, acceptance_contract=None)

            self.assertEqual(gate.status, "PASSED")

    def test_worker_blocked_status_blocks_gate_without_advancing(self) -> None:
        from ai_company.gatekeeper import Gatekeeper
        from ai_company.models import StageContract, StageResultEnvelope
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Acceptance",
                status="blocked",
                artifact_name="acceptance_report.md",
                artifact_content="# Acceptance\nCannot verify external tool.\n",
                contract_id="contract-acceptance",
                evidence=[
                    {
                        "name": "product_level_validation",
                        "kind": "report",
                        "summary": "Acceptance review could not proceed.",
                    }
                ],
                blocked_reason="External tool unavailable.",
            )
            contract = StageContract(
                session_id=session.session_id,
                stage="Acceptance",
                contract_id="contract-acceptance",
                goal="Accept",
                required_outputs=["acceptance_report.md"],
                evidence_requirements=["product_level_validation"],
            )

            gate = Gatekeeper().evaluate(session=session, contract=contract, result=result, acceptance_contract=None)

            self.assertEqual(gate.status, "BLOCKED")
            self.assertIn("External tool unavailable", gate.reason)
```

- [ ] **Step 2: Run gatekeeper tests to verify RED**

Run:

```bash
/tmp/ai-team-runtime-enforced-venv/bin/python -m unittest tests.test_gatekeeper
```

Expected: tests fail because `ai_company.gatekeeper` does not exist.

- [ ] **Step 3: Implement `Gatekeeper`**

Implement `Gatekeeper.evaluate()` so it:

```text
FAILED: session/stage/contract/output/evidence contract is missing or mismatched
BLOCKED: worker reports blocked or existing review gate reports blocked
PASSED: structural contract and evidence requirements are satisfied
```

Use `review_gates.apply_stage_gates()` for acceptance-contract review checks.

- [ ] **Step 4: Run gatekeeper tests to verify GREEN**

Run:

```bash
/tmp/ai-team-runtime-enforced-venv/bin/python -m unittest tests.test_gatekeeper
```

Expected: all gatekeeper tests pass.

---

### Task 3: CLI Control Plane

**Files:**
- Modify: `ai_company/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Update existing submit tests so they call `acquire-stage-run` before `submit-stage-result` and `verify-stage-result` after it. Add these specific checks:

```python
def test_submit_stage_result_requires_active_stage_run(self) -> None:
    # start-session, build Product contract, then submit without acquire
    # Expected: non-zero exit and "No active stage run"
```

```python
def test_acquire_submit_verify_product_moves_to_ceo_wait(self) -> None:
    # start-session
    # build-stage-contract Product
    # acquire-stage-run Product
    # submit-stage-result Product bundle
    # assert submit prints run_state: SUBMITTED and does not print WaitForCEOApproval as current state
    # verify-stage-result
    # assert verify prints gate_status: PASSED and current_state: WaitForCEOApproval
```

```python
def test_step_reports_verify_when_candidate_is_submitted(self) -> None:
    # start-session
    # acquire-stage-run Product
    # submit-stage-result Product bundle
    # step
    # Expected stdout contains next_action: verify-stage-result
```

- [ ] **Step 2: Run CLI tests to verify RED**

Run:

```bash
/tmp/ai-team-runtime-enforced-venv/bin/python -m unittest tests.test_cli.CliTests.test_submit_stage_result_requires_active_stage_run tests.test_cli.CliTests.test_acquire_submit_verify_product_moves_to_ceo_wait tests.test_cli.CliTests.test_step_reports_verify_when_candidate_is_submitted
```

Expected: tests fail because new CLI commands do not exist and submit still advances directly.

- [ ] **Step 3: Implement CLI commands**

Add:

```text
ai-team step
ai-team acquire-stage-run --session-id <id> [--stage <stage>] [--worker <name>]
ai-team verify-stage-result --session-id <id> [--run-id <run_id>]
```

Change:

```text
ai-team submit-stage-result
```

so it only persists candidate bundles and sets run state to `SUBMITTED`.

Required command behavior:

```text
submit without active RUNNING run -> error
verify without active SUBMITTED run -> error
gate PASSED -> mark run PASSED, record artifacts, call StageMachine.advance()
gate FAILED -> mark run FAILED, keep workflow stage unchanged, return non-zero
gate BLOCKED -> mark run BLOCKED, keep workflow stage unchanged, return non-zero
```

- [ ] **Step 4: Run targeted CLI tests to verify GREEN**

Run:

```bash
/tmp/ai-team-runtime-enforced-venv/bin/python -m unittest tests.test_cli.CliTests.test_submit_stage_result_requires_active_stage_run tests.test_cli.CliTests.test_acquire_submit_verify_product_moves_to_ceo_wait tests.test_cli.CliTests.test_step_reports_verify_when_candidate_is_submitted
```

Expected: targeted CLI tests pass.

---

### Task 4: Existing Flow Compatibility And Docs

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `README.md`
- Modify: `docs/workflow-specs/2026-04-17-ai-team-enforced-stage-gates-flow.md`

- [ ] **Step 1: Update existing CLI tests for enforced flow**

Update direct submit tests to the new order:

```text
start-session
build-stage-contract
acquire-stage-run
submit-stage-result
verify-stage-result
record-human-decision when workflow is in wait state
```

- [ ] **Step 2: Update docs**

Ensure docs include this enforced order:

```text
ai-team step
ai-team build-stage-contract
ai-team acquire-stage-run
ai-team submit-stage-result
ai-team verify-stage-result
ai-team step
```

- [ ] **Step 3: Run full test suite**

Run:

```bash
/tmp/ai-team-runtime-enforced-venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Expected: all tests pass.

---

## Self-Review

- Spec coverage: The plan implements first-class stage runs, candidate submission, gatekeeper decisions, blocked/failed semantics, and runtime-only workflow advancement.
- Placeholder scan: No implementation step depends on TBD behavior; gate outcomes and CLI semantics are explicit.
- Type consistency: `StageRunRecord.state`, `GateResult.status`, and CLI printed fields use uppercase run/gate statuses.
