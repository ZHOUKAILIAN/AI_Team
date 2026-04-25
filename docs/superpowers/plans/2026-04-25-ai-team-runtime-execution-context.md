# AI_Team Runtime Execution Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 execution-context handoff so Dev receives a stable `StageExecutionContext` after Product PRD approval.

**Architecture:** Add a focused `ai_company/execution_context.py` module that builds and serializes execution contexts from existing session state, artifacts, contracts, findings, and acceptance contracts. Wire it into `record-human-decision go`, `build-stage-contract`, `step`, and a new `build-execution-context` CLI command without changing stage ownership rules.

**Tech Stack:** Python dataclasses, existing `StateStore`, `StageContract`, `WorkflowSummary`, `argparse`, `unittest`.

---

### Task 1: Add Execution Context Builder

**Files:**
- Create: `ai_company/execution_context.py`
- Test: `tests/test_execution_context.py`

- [ ] **Step 1: Write failing tests**

Add tests for:

```python
def test_build_dev_execution_context_uses_approved_prd_and_contract():
    # Create a session, write an approved Product artifact, build a Dev contract,
    # and assert that the Dev context includes PRD summary, contract id,
    # required outputs, required evidence, and acceptance criteria.
```

```python
def test_build_dev_execution_context_includes_actionable_findings():
    # Store a QA finding routed to Dev and assert it appears in the context.
```

- [ ] **Step 2: Run tests to verify red**

Run: `python3 -m unittest tests.test_execution_context -v`

Expected: import failure because `ai_company.execution_context` does not exist.

- [ ] **Step 3: Implement builder**

Create:

```python
@dataclass(slots=True)
class ExecutionContextBudget:
    max_context_tokens: int = 24000
    max_artifact_snippet_chars: int = 4000
    max_findings: int = 20
```

```python
@dataclass(slots=True)
class StageExecutionContext:
    session_id: str
    stage: str
    round_index: int
    context_id: str
    contract_id: str
    original_request_summary: str
    approved_prd_summary: str
    acceptance_matrix: list[dict[str, Any]]
    constraints: list[str]
    required_outputs: list[str]
    required_evidence: list[str]
    relevant_artifacts: list[ArtifactRef]
    actionable_findings: list[Finding]
    repo_context_summary: str
    role_context_digest: str
    budget: ExecutionContextBudget
```

Expose:

```python
def build_stage_execution_context(
    *,
    repo_root: Path,
    state_store: StateStore,
    session_id: str,
    stage: str,
    contract: StageContract,
) -> StageExecutionContext:
    session = state_store.load_session(session_id)
    summary = state_store.load_workflow_summary(session_id)
    prd_path = Path(summary.artifact_paths["product"])
    approved_prd = prd_path.read_text()
    context_id = hashlib.sha256(
        f"{session_id}|{stage}|{contract.contract_id}|{approved_prd}".encode("utf-8")
    ).hexdigest()[:16]
    role_digest = hashlib.sha256(contract.role_context.encode("utf-8")).hexdigest()
    return StageExecutionContext(
        session_id=session_id,
        stage=stage,
        round_index=1,
        context_id=context_id,
        contract_id=contract.contract_id,
        original_request_summary=session.request,
        approved_prd_summary=approved_prd[:4000],
        acceptance_matrix=[],
        constraints=[],
        required_outputs=list(contract.required_outputs),
        required_evidence=list(contract.evidence_requirements),
        relevant_artifacts=[],
        actionable_findings=[],
        repo_context_summary="Repo-local role files available for the stage.",
        role_context_digest=f"sha256:{role_digest}; chars:{len(contract.role_context)}",
        budget=ExecutionContextBudget(),
    )
```

- [ ] **Step 4: Run tests to verify green**

Run: `python3 -m unittest tests.test_execution_context -v`

Expected: all tests pass.

### Task 2: Persist Execution Contexts

**Files:**
- Modify: `ai_company/state.py`
- Test: `tests/test_execution_context.py`

- [ ] **Step 1: Write failing persistence test**

Add a test asserting:

```python
path = store.save_execution_context(context)
assert path.name == "dev_round_1.json"
loaded = store.load_execution_context(session_id, "Dev")
assert loaded["context_id"] == context.context_id
```

- [ ] **Step 2: Run tests to verify red**

Run: `python3 -m unittest tests.test_execution_context -v`

Expected: `StateStore` has no `save_execution_context`.

- [ ] **Step 3: Implement persistence helpers**

Add:

```python
def save_execution_context(self, context: StageExecutionContextLike) -> Path:
    session = self.load_session(context.session_id)
    path = session.session_dir / "execution_context" / f"{context.stage.lower()}_round_{context.round_index}.json"
    self._write_json(path, context.to_dict())
    return path
```

```python
def latest_execution_context_path(self, session_id: str, stage: str) -> Path | None:
    session = self.load_session(session_id)
    context_dir = session.session_dir / "execution_context"
    matches = sorted(context_dir.glob(f"{stage.lower()}_round_*.json")) if context_dir.exists() else []
    return matches[-1] if matches else None
```

```python
def load_execution_context(self, session_id: str, stage: str) -> dict[str, object] | None:
    path = self.latest_execution_context_path(session_id, stage)
    return json.loads(path.read_text()) if path else None
```

The file path should be:

```text
<session_dir>/execution_context/<stage_lower>_round_<round_index>.json
```

- [ ] **Step 4: Run tests to verify green**

Run: `python3 -m unittest tests.test_execution_context -v`

Expected: all tests pass.

### Task 3: Wire Context into CLI and Contracts

**Files:**
- Modify: `ai_company/cli.py`
- Modify: `ai_company/stage_contracts.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_stage_contracts.py`

- [ ] **Step 1: Write failing CLI tests**

Add tests asserting:

```python
record-human-decision --decision go
```

creates:

```text
<state_root>/<session_id>/execution_context/dev_round_1.json
```

and prints:

```text
execution_context:
```

Add a test for:

```text
ai-team build-execution-context --session-id <id> --stage Dev
```

returning JSON with `stage == "Dev"` and `contract_id`.

- [ ] **Step 2: Write failing contract test**

Add a test asserting that a Dev `StageContract` includes:

```python
contract.input_artifacts["execution_context"]
```

when a Dev execution context exists.

- [ ] **Step 3: Run targeted tests to verify red**

Run:

```bash
python3 -m unittest tests.test_cli.CliTests.test_record_human_decision_routes_wait_state_to_dev -v
python3 -m unittest tests.test_stage_contracts.StageContractTests.test_dev_contract_references_latest_execution_context -v
```

Expected: tests fail because CLI command and contract reference are missing.

- [ ] **Step 4: Implement CLI wiring**

Add parser:

```text
build-execution-context --session-id <id> --stage <stage>
```

Enhance `record-human-decision`:

```python
if summary.current_state == "WaitForCEOApproval" and updated_summary.current_state == "Dev":
    contract = build_stage_contract(
        repo_root=args.repo_root,
        state_store=store,
        session_id=args.session_id,
        stage="Dev",
    )
    context = build_stage_execution_context(
        repo_root=args.repo_root,
        state_store=store,
        session_id=args.session_id,
        stage="Dev",
        contract=contract,
    )
    context_path = store.save_execution_context(context)
    updated_summary.artifact_paths["execution_context"] = str(context_path)
```

Enhance `build_stage_contract` to attach latest context path for the target stage.

- [ ] **Step 5: Run targeted tests to verify green**

Run:

```bash
python3 -m unittest tests.test_execution_context tests.test_stage_contracts tests.test_cli -v
```

Expected: all targeted tests pass.

### Task 4: Verify and Commit

**Files:**
- Modify: all changed files

- [ ] **Step 1: Run full test suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 2: Review git diff**

Run: `git diff --stat && git diff -- ai_company tests docs/superpowers`

Expected: only execution-context Phase 1 implementation, design doc, and plan doc changed.

- [ ] **Step 3: Commit**

Run:

```bash
git add ai_company tests docs/superpowers/specs/2026-04-25-ai-team-runtime-agent-context-evolution-design.md docs/superpowers/plans/2026-04-25-ai-team-runtime-execution-context.md
git commit -m "feat: add stage execution context handoff"
```

Expected: commit succeeds.

## Self-Review

| Check | Result |
| --- | --- |
| Covers approved Phase 1 scope | Yes |
| Avoids implementing subagents before execution context | Yes |
| Avoids changing workflow ownership rules | Yes |
| Includes failing tests before implementation | Yes |
| Uses exact files and commands | Yes |
