# Agent Team Feedback Learning Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add actionable rework routing for QA and Acceptance failures, plus a human-feedback learning intake, so Agent Team can feed downstream defects back into Product/Dev and write standardized learning overlays.

**Architecture:** Keep the file-backed workflow and `Finding` model as the core contract. Extend the orchestrator to support rework loops, extend the CLI/state layer to record human feedback, and standardize learning overlay formatting so future role loading gets precise constraints and completion signals.

**Tech Stack:** Python 3.13, unittest, file-backed workflow artifacts, Markdown skill/docs files

---

### Task 1: Add failing tests for feedback recording and learning formatting

**Files:**
- Modify: `tests/test_state.py`
- Modify: `tests/test_cli.py`
- Test: `tests/test_state.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing state test for standardized overlay formatting**

```python
def test_apply_learning_writes_standardized_overlay_sections(self) -> None:
    from agent_team.models import Finding
    from agent_team.state import StateStore

    with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
        root = Path(temp_dir)
        store = StateStore(root)
        store.apply_learning(
            Finding(
                source_stage="Acceptance",
                target_stage="Dev",
                issue="Acceptance found a missing error state",
                severity="high",
                lesson="Preserve product-visible error states in regression coverage.",
                proposed_context_update="Review product-visible error states before closing implementation.",
                proposed_skill_update="Require user-visible verification evidence before claiming the fix is complete.",
            )
        )

        lessons = (root / "memory" / "Dev" / "lessons.md").read_text()
        context_patch = (root / "memory" / "Dev" / "context_patch.md").read_text()
        skill_patch = (root / "memory" / "Dev" / "skill_patch.md").read_text()

        self.assertIn("- source: Acceptance", lessons)
        self.assertIn("Constraint:", context_patch)
        self.assertIn("Completion signal:", context_patch)
        self.assertIn("Goal:", skill_patch)
        self.assertIn("Completion signal:", skill_patch)
```

- [ ] **Step 2: Run the state test to verify it fails**

Run: `python3 -m unittest tests.test_state.StateTests.test_apply_learning_writes_standardized_overlay_sections -v`

Expected: FAIL because the current overlay writer does not emit the standardized labels.

- [ ] **Step 3: Write the failing CLI test for human feedback intake**

```python
def test_record_feedback_persists_learning_and_feedback_metadata(self) -> None:
    repo_root = Path(__file__).resolve().parents[1]

    with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
        bootstrap = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_team",
                "--repo-root",
                str(repo_root),
                "--state-root",
                temp_dir,
                "start-session",
                "--message",
                "执行这个需求：做一个支持反馈回流的流程",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        session_id = dict(
            line.split(": ", 1) for line in bootstrap.stdout.splitlines() if ": " in line
        )["session_id"]

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_team",
                "--repo-root",
                str(repo_root),
                "--state-root",
                temp_dir,
                "record-feedback",
                "--session-id",
                session_id,
                "--source-stage",
                "Acceptance",
                "--target-stage",
                "Dev",
                "--issue",
                "User reported an unhandled empty state",
                "--lesson",
                "Cover empty states in product-level validation.",
                "--context-update",
                "Review empty-state behavior before handoff.",
                "--skill-update",
                "Require visible empty-state evidence before reporting success.",
                "--severity",
                "high",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("recorded_feedback:", result.stdout)
```

- [ ] **Step 4: Run the CLI test to verify it fails**

Run: `python3 -m unittest tests.test_cli.CliTests.test_record_feedback_persists_learning_and_feedback_metadata -v`

Expected: FAIL because `record-feedback` does not exist yet.

- [ ] **Step 5: Commit**

```bash
git add tests/test_state.py tests/test_cli.py
git commit -m "test: cover feedback recording and learning overlay format"
```

### Task 2: Add failing tests for QA and Acceptance rework routing

**Files:**
- Modify: `tests/test_orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing orchestrator test for Acceptance rework routing**

```python
def test_acceptance_failure_creates_rework_learning_for_dev(self) -> None:
    from agent_team.backend import StaticBackend
    from agent_team.orchestrator import WorkflowOrchestrator
    from agent_team.state import StateStore

    repo_root = Path(__file__).resolve().parents[1]

    with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
        state_root = Path(temp_dir)
        backend = StaticBackend.fixture(
            product_requirements="Users can submit a form",
            prd="PRD v1",
            tech_spec="Tech spec v1",
            qa_report="QA passed after rerun",
            acceptance_report="recommended_no_go because empty-state UX is missing",
            findings=[],
        )

        result = WorkflowOrchestrator(
            repo_root=repo_root,
            state_store=StateStore(state_root),
            backend=backend,
        ).run(request="Build a form flow")

        learned_memory = (state_root / "memory" / "Dev" / "lessons.md").read_text()
        self.assertEqual(result.acceptance_status, "recommended_no_go")
        self.assertIn("Acceptance", learned_memory)
        self.assertIn("empty-state UX", learned_memory)
```

- [ ] **Step 2: Write the failing orchestrator test for QA rework rounds**

```python
def test_qa_findings_increment_rework_round(self) -> None:
    from agent_team.backend import StaticBackend
    from agent_team.orchestrator import WorkflowOrchestrator
    from agent_team.state import StateStore

    repo_root = Path(__file__).resolve().parents[1]

    with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
        state_root = Path(temp_dir)
        backend = StaticBackend.fixture(
            product_requirements="Users can create a task",
            prd="PRD v1",
            tech_spec="Tech spec v1",
            qa_report="QA found retry-state regression",
            acceptance_report="blocked",
            findings=[
                {
                    "source_stage": "QA",
                    "target_stage": "Dev",
                    "issue": "Retry-state regression",
                    "severity": "high",
                    "lesson": "Preserve retry states during rework.",
                }
            ],
        )

        result = WorkflowOrchestrator(
            repo_root=repo_root,
            state_store=StateStore(state_root),
            backend=backend,
        ).run(request="Build a task manager")

        review = (state_root / "sessions" / result.session_id / "review.md").read_text()
        self.assertIn("qa_round: 1", review)
```

- [ ] **Step 3: Run the orchestrator tests to verify they fail**

Run: `python3 -m unittest tests.test_orchestrator.OrchestratorTests.test_acceptance_failure_creates_rework_learning_for_dev tests.test_orchestrator.OrchestratorTests.test_qa_findings_increment_rework_round -v`

Expected: FAIL because Acceptance failures are not converted into findings and QA rounds stay at `0`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_orchestrator.py
git commit -m "test: cover acceptance rework routing and qa rounds"
```

### Task 3: Implement feedback recording and standardized learning overlays

**Files:**
- Modify: `agent_team/models.py`
- Modify: `agent_team/state.py`
- Modify: `agent_team/cli.py`
- Test: `tests/test_state.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Add feedback metadata model support**

```python
@model_dataclass
class FeedbackRecord:
    session_id: str
    source_stage: str
    target_stage: str
    issue: str
    severity: str
    created_at: str
    evidence: str = ""
```

- [ ] **Step 2: Add state helpers for feedback persistence and standardized formatting**

```python
def record_feedback(self, session_id: str, finding: Finding) -> Path:
    feedback_dir = self.root / "sessions" / session_id / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    record_path = feedback_dir / f"{self._timestamp().replace(':', '-')}.json"
    self._write_json(record_path, {"recorded_at": self._timestamp(), **finding.to_dict()})
    self.apply_learning(finding)
    return record_path
```

```python
(
    f"## {self._timestamp()}\n"
    f"Constraint: {finding.proposed_context_update}\n"
    f"Completion signal: add explicit verification evidence for this rule.\n"
)
```

- [ ] **Step 3: Add the CLI subcommand**

```python
feedback_parser = subparsers.add_parser(
    "record-feedback",
    help="Record human feedback as a structured learning finding.",
)
feedback_parser.add_argument("--session-id", required=True)
feedback_parser.add_argument("--source-stage", required=True)
feedback_parser.add_argument("--target-stage", required=True)
feedback_parser.add_argument("--issue", required=True)
feedback_parser.add_argument("--severity", default="medium")
feedback_parser.add_argument("--lesson", default="")
feedback_parser.add_argument("--context-update", default="")
feedback_parser.add_argument("--skill-update", default="")
feedback_parser.add_argument("--evidence", default="")
feedback_parser.set_defaults(handler=_handle_record_feedback)
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `python3 -m unittest tests.test_state.StateTests.test_apply_learning_writes_standardized_overlay_sections tests.test_cli.CliTests.test_record_feedback_persists_learning_and_feedback_metadata -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent_team/models.py agent_team/state.py agent_team/cli.py tests/test_state.py tests/test_cli.py
git commit -m "feat: add feedback intake and standardize learning overlays"
```

### Task 4: Implement QA and Acceptance rework routing

**Files:**
- Modify: `agent_team/backend.py`
- Modify: `agent_team/orchestrator.py`
- Modify: `tests/test_orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Add Acceptance finding synthesis**

```python
def _acceptance_findings(self, acceptance_report: str, findings: list[Finding]) -> list[Finding]:
    if "recommended_no_go" not in acceptance_report.lower() and "blocked" not in acceptance_report.lower():
        return []
    return [
        Finding(
            source_stage="Acceptance",
            target_stage="Dev",
            issue="Acceptance rejected the current product-level outcome.",
            severity="high",
            lesson="Preserve product-visible outcomes until Acceptance evidence is complete.",
            proposed_context_update="Review user-visible behavior against the PRD before closing implementation.",
            proposed_skill_update="Require product-level evidence in the handoff before reporting success.",
            evidence=acceptance_report,
        )
    ]
```

- [ ] **Step 2: Update the orchestrator to count QA rounds and apply Acceptance findings**

```python
if stage == "QA" and output.findings:
    summary.qa_status = "blocked"
    summary.qa_round += 1
```

```python
for finding in output.findings:
    self.state_store.apply_learning(finding)
    findings.append(finding)
```

- [ ] **Step 3: Run the orchestrator tests to verify they pass**

Run: `python3 -m unittest tests.test_orchestrator -v`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add agent_team/backend.py agent_team/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: route qa and acceptance failures into rework learning"
```

### Task 5: Update skills and docs to match runtime behavior

**Files:**
- Modify: `QA/SKILL.md`
- Modify: `Acceptance/SKILL.md`
- Modify: `Dev/SKILL.md`
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `SKILL.md`
- Modify: `codex-skill/agent-team-workflow/SKILL.md`
- Test: `tests/test_docs.py`
- Test: `tests/test_skill_package.py`

- [ ] **Step 1: Update docs to describe the new routing and feedback intake**

```md
- Acceptance failures produce structured findings that route back to Product or Dev.
- Human feedback can be recorded through `record-feedback` and enters the same learning overlay pipeline.
- Learning overlays store reusable rules with explicit completion signals.
```

- [ ] **Step 2: Update role skills to match the runtime contract**

```md
If Acceptance blocks or recommends no-go, emit structured findings that identify the owner of the rework and the evidence missing for closure.
```

- [ ] **Step 3: Run docs and skill package tests**

Run: `python3 -m unittest tests.test_docs tests.test_skill_package -v`

Expected: PASS

- [ ] **Step 4: Run the full targeted regression suite**

Run: `python3 -m unittest tests.test_cli tests.test_orchestrator tests.test_state tests.test_docs tests.test_skill_package -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add QA/SKILL.md Acceptance/SKILL.md Dev/SKILL.md README.md README_zh.md SKILL.md codex-skill/agent-team-workflow/SKILL.md tests/test_docs.py tests/test_skill_package.py
git commit -m "docs: align workflow skills with feedback learning loop"
```
