# AI_Team Harness-First Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current bootstrap-oriented AI_Team runtime into a first-pass Harness-First CLI supervisor with app-local state, explicit stage transitions, stage contract generation, result submission, and human decision recording.

**Architecture:** Keep `ai_company` as the executable runtime, add a real stage controller and stage-contract/result protocol, and move default session state out of repo-local `.ai_company_state` into an app-local workspace-scoped directory. The first iteration remains CLI-first under Codex app and does not yet require a native plugin layer.

**Tech Stack:** Python 3, `argparse`, dataclasses, file-based state storage, `unittest`

---

## File Structure

- Create: `ai_company/harness_paths.py`
- Create: `ai_company/stage_machine.py`
- Create: `ai_company/stage_contracts.py`
- Modify: `ai_company/cli.py`
- Modify: `ai_company/models.py`
- Modify: `ai_company/state.py`
- Modify: `ai_company/workflow_summary.py`
- Modify: `ai_company/project_scaffold.py`
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `SKILL.md`
- Modify: `codex-skill/ai-company-workflow/SKILL.md`
- Test: `tests/test_cli.py`
- Test: `tests/test_state.py`
- Test: `tests/test_orchestrator.py`
- Create Test: `tests/test_stage_machine.py`
- Create Test: `tests/test_stage_contracts.py`
- Create Test: `tests/test_harness_paths.py`

### Task 1: App-Local Harness State Root

**Files:**
- Create: `ai_company/harness_paths.py`
- Modify: `ai_company/cli.py`
- Modify: `tests/test_cli.py`
- Create Test: `tests/test_harness_paths.py`

- [ ] **Step 1: Write the failing tests for app-local default state root**

```python
def test_default_state_root_prefers_codex_home_workspace_directory(self) -> None:
    from ai_company.harness_paths import default_state_root

    repo_root = Path("/tmp/demo-repo")
    codex_home = Path("/tmp/codex-home")

    root = default_state_root(repo_root=repo_root, codex_home=codex_home)

    self.assertEqual(
        root,
        codex_home / "ai-team" / "workspaces" / "demo-repo-" + "...",
    )
```

```python
def test_start_session_uses_app_local_state_root_when_not_provided(self) -> None:
    env = os.environ.copy()
    env["CODEX_HOME"] = temp_dir
    result = subprocess.run(
        [sys.executable, "-m", "ai_company", "--repo-root", str(repo_root), "start-session", "--message", raw_message],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    self.assertEqual(result.returncode, 0)
    self.assertIn(str(Path(temp_dir) / "ai-team" / "workspaces"), result.stdout)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_cli tests.test_harness_paths -v`
Expected: FAIL because `default_state_root` does not exist and CLI still defaults to repo-local `.ai_company_state`.

- [ ] **Step 3: Implement workspace-scoped path resolution**

```python
def default_state_root(*, repo_root: Path, codex_home: Path | None = None) -> Path:
    home = codex_home or _default_codex_home()
    fingerprint = workspace_fingerprint(repo_root)
    return home / "ai-team" / "workspaces" / fingerprint
```

```python
args.state_root = (
    args.state_root.resolve()
    if args.state_root is not None
    else default_state_root(repo_root=args.repo_root)
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_cli tests.test_harness_paths -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai_company/harness_paths.py ai_company/cli.py tests/test_cli.py tests/test_harness_paths.py
git commit -m "feat: add app-local harness state root"
```

### Task 2: Explicit Stage Machine

**Files:**
- Create: `ai_company/stage_machine.py`
- Modify: `ai_company/models.py`
- Modify: `ai_company/state.py`
- Create Test: `tests/test_stage_machine.py`
- Modify: `tests/test_state.py`

- [ ] **Step 1: Write the failing tests for legal stage transitions**

```python
def test_advance_from_wait_for_ceo_approval_requires_human_decision(self) -> None:
    machine = StageMachine()
    summary = WorkflowSummary(
        session_id="s1",
        runtime_mode="session_bootstrap",
        current_state="WaitForCEOApproval",
        current_stage="ProductDraft",
    )

    with self.assertRaises(StageTransitionError):
        machine.advance(summary=summary, action="advance")
```

```python
def test_record_human_decision_go_moves_session_into_dev(self) -> None:
    machine = StageMachine()
    updated = machine.apply_human_decision(summary=summary, decision="go")
    self.assertEqual(updated.current_state, "Dev")
    self.assertEqual(updated.current_stage, "Dev")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_stage_machine tests.test_state -v`
Expected: FAIL because `StageMachine` and transition validation do not exist.

- [ ] **Step 3: Implement stage machine and persisted summary helpers**

```python
class StageMachine:
    def current_stage(self, summary: WorkflowSummary) -> str:
        return summary.current_stage

    def apply_human_decision(self, summary: WorkflowSummary, decision: str, target_stage: str | None = None) -> WorkflowSummary:
        ...

    def advance(self, summary: WorkflowSummary, stage_result: StageResultEnvelope) -> WorkflowSummary:
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_stage_machine tests.test_state -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai_company/stage_machine.py ai_company/models.py ai_company/state.py tests/test_stage_machine.py tests/test_state.py
git commit -m "feat: add explicit harness stage machine"
```

### Task 3: Stage Contract Compilation

**Files:**
- Create: `ai_company/stage_contracts.py`
- Modify: `ai_company/models.py`
- Modify: `ai_company/cli.py`
- Create Test: `tests/test_stage_contracts.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests for `build-stage-contract`**

```python
def test_build_stage_contract_outputs_product_contract_json(self) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_company",
            "--repo-root",
            str(repo_root),
            "--state-root",
            temp_dir,
            "build-stage-contract",
            "--session-id",
            session_id,
            "--stage",
            "Product",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    self.assertEqual(result.returncode, 0)
    self.assertIn('"stage": "Product"', result.stdout)
    self.assertIn('"required_outputs"', result.stdout)
```

```python
def test_product_contract_disallows_stage_transition_override(self) -> None:
    contract = build_stage_contract(...)
    self.assertIn("must_not_change_stage_order", contract.forbidden_actions)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_stage_contracts tests.test_cli -v`
Expected: FAIL because the command and contract builder do not exist.

- [ ] **Step 3: Implement machine-readable stage contracts**

```python
@model_dataclass
class StageContract:
    session_id: str
    stage: str
    goal: str
    input_artifacts: dict[str, str]
    required_outputs: list[str]
    forbidden_actions: list[str]
    evidence_requirements: list[str] = field(default_factory=list)
```

```python
def build_stage_contract(...):
    return StageContract(
        session_id=session.session_id,
        stage=stage,
        goal="...",
        input_artifacts=...,
        required_outputs=[...],
        forbidden_actions=[...],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_stage_contracts tests.test_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai_company/stage_contracts.py ai_company/models.py ai_company/cli.py tests/test_stage_contracts.py tests/test_cli.py
git commit -m "feat: add stage contract builder command"
```

### Task 4: Structured Stage Result Submission And Advance

**Files:**
- Modify: `ai_company/models.py`
- Modify: `ai_company/state.py`
- Modify: `ai_company/cli.py`
- Modify: `ai_company/stage_machine.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_stage_machine.py`

- [ ] **Step 1: Write the failing tests for `submit-stage-result` and `advance`**

```python
def test_submit_stage_result_persists_bundle_and_updates_latest_stage_record(self) -> None:
    bundle = temp_path / "product_bundle.json"
    bundle.write_text(json.dumps({...}))
    result = subprocess.run([... "submit-stage-result" ...], ...)
    self.assertEqual(result.returncode, 0)
    self.assertIn("stored_bundle:", result.stdout)
```

```python
def test_advance_moves_from_product_to_wait_for_ceo_approval(self) -> None:
    result = subprocess.run([... "advance" ...], ...)
    self.assertEqual(result.returncode, 0)
    self.assertIn("current_state: WaitForCEOApproval", result.stdout)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_cli tests.test_state tests.test_stage_machine -v`
Expected: FAIL because bundle submission and manual advance commands do not exist.

- [ ] **Step 3: Implement result-envelope persistence and harness advance**

```python
@model_dataclass
class StageResultEnvelope:
    session_id: str
    stage: str
    status: str
    artifact_name: str
    artifact_content: str
    journal: str = ""
    findings: list[Finding] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    suggested_next_owner: str = ""
    summary: str = ""
```

```python
def submit_stage_result(...):
    envelope = StageResultEnvelope.from_dict(payload)
    stage_record = store.record_stage_result(...)
    summary = machine.advance(summary=summary, stage_result=envelope)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_cli tests.test_state tests.test_stage_machine -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai_company/models.py ai_company/state.py ai_company/cli.py ai_company/stage_machine.py tests/test_cli.py tests/test_state.py tests/test_stage_machine.py
git commit -m "feat: add structured stage result submission"
```

### Task 5: Resume, Human Decision, And Workflow Summary Visibility

**Files:**
- Modify: `ai_company/cli.py`
- Modify: `ai_company/workflow_summary.py`
- Modify: `ai_company/state.py`
- Modify: `tests/test_cli.py`
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `SKILL.md`
- Modify: `codex-skill/ai-company-workflow/SKILL.md`

- [ ] **Step 1: Write the failing tests for `current-stage`, `resume`, and `record-human-decision`**

```python
def test_current_stage_reports_machine_readable_stage(self) -> None:
    result = subprocess.run([... "current-stage" ...], ...)
    self.assertEqual(result.returncode, 0)
    self.assertIn("current_stage:", result.stdout)
```

```python
def test_record_human_decision_rework_routes_back_to_dev(self) -> None:
    result = subprocess.run([... "record-human-decision", "--decision", "rework", "--target-stage", "Dev"], ...)
    self.assertEqual(result.returncode, 0)
    self.assertIn("current_stage: Dev", result.stdout)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_cli -v`
Expected: FAIL because these commands do not exist.

- [ ] **Step 3: Implement CLI visibility and human decision handling**

```python
current_stage_parser = subparsers.add_parser("current-stage", ...)
resume_parser = subparsers.add_parser("resume", ...)
human_decision_parser = subparsers.add_parser("record-human-decision", ...)
```

```python
print(f"current_state: {summary.current_state}")
print(f"current_stage: {summary.current_stage}")
print(f"human_decision: {summary.human_decision}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai_company/cli.py ai_company/workflow_summary.py ai_company/state.py tests/test_cli.py README.md README_zh.md SKILL.md codex-skill/ai-company-workflow/SKILL.md
git commit -m "feat: expose harness stage and human decision commands"
```

### Task 6: Full Regression

**Files:**
- Test: `tests/test_cli.py`
- Test: `tests/test_orchestrator.py`
- Test: `tests/test_state.py`
- Test: `tests/test_docs.py`
- Test: `tests/test_skill_package.py`

- [ ] **Step 1: Run targeted harness regression suite**

Run: `python3 -m unittest tests.test_cli tests.test_state tests.test_stage_machine tests.test_stage_contracts tests.test_harness_paths -v`
Expected: PASS

- [ ] **Step 2: Run full test suite**

Run: `python3 -m unittest discover -s tests`
Expected: PASS

- [ ] **Step 3: Review diff for scope drift**

Run: `git diff --stat`
Expected: only harness-first prototype files and docs touched

- [ ] **Step 4: Commit final integration pass**

```bash
git add ai_company tests README.md README_zh.md SKILL.md codex-skill/ai-company-workflow/SKILL.md docs/workflow-specs/2026-04-11-ai-team-codex-harness-design.md docs/superpowers/plans/2026-04-11-ai-team-harness-first-prototype.md
git commit -m "feat: add harness-first prototype runtime"
```
