# Agent Team Single-Session Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current deterministic Agent Team execution path with a single-session, file-backed workflow that runs `Product -> CEO approval -> Dev <-> QA -> Acceptance -> human Go/No-Go`, while preserving `superpower` TDD inside `Dev`.

**Architecture:** Keep the Python runtime as the session/bootstrap, persistence, and review layer, but stop treating it as the real QA/Acceptance executor. Add an explicit `workflow_summary.md` contract plus bootstrap commands that the skill can use, then rewrite the root and packaged skills so the real workflow runs inside the active Codex session with stage files as handoff artifacts.

**Tech Stack:** Python 3.13, `unittest`, `argparse`, `dataclasses`, `json`, Markdown artifacts, shell helper scripts

---

## File Structure

### Runtime and Persistence

- Modify: `agent_team/models.py`
  Responsibility: add a first-class workflow summary model for the single-session flow.
- Create: `agent_team/workflow_summary.py`
  Responsibility: render a `WorkflowSummary` into `workflow_summary.md` with stable field order.
- Modify: `agent_team/state.py`
  Responsibility: create/save/update the workflow summary and align artifact naming with `implementation.md`.
- Modify: `agent_team/cli.py`
  Responsibility: add session bootstrap commands for the skill-driven workflow and keep legacy deterministic commands explicit.
- Modify: `agent_team/review.py`
  Responsibility: surface workflow summary status in generated reviews.

### Skill and Packaging Layer

- Modify: `SKILL.md`
  Responsibility: define the real state-machine workflow that runs in the active Codex session.
- Modify: `codex-skill/agent-team-workflow/SKILL.md`
  Responsibility: mirror the root skill so installed sessions behave the same way.
- Modify: `codex-skill/agent-team-workflow/scripts/agent-team-run.sh`
  Responsibility: bootstrap a workflow session instead of executing the deterministic backend as if it were real QA/Acceptance.

### Tests

- Create: `tests/test_workflow_summary.py`
  Responsibility: verify workflow summary rendering and persistence.
- Modify: `tests/test_state.py`
  Responsibility: assert workflow summary creation and new artifact naming.
- Modify: `tests/test_cli.py`
  Responsibility: verify session bootstrap commands and output.
- Modify: `tests/test_review.py`
  Responsibility: verify review output reflects workflow summary status.
- Modify: `tests/test_skill_package.py`
  Responsibility: verify installed skill text and helper script match the new bootstrap flow.
- Modify: `tests/test_docs.py`
  Responsibility: verify repo docs describe the single-session workflow accurately.

### Docs

- Modify: `README.md`
- Modify: `README_zh.md`
  Responsibility: explain the new single-session workflow, approval pause, QA independence, and blocked-on-missing-evidence rule.

---

### Task 1: Add workflow summary model and persistence helpers

**Files:**
- Create: `agent_team/workflow_summary.py`
- Modify: `agent_team/models.py`
- Modify: `agent_team/state.py`
- Create: `tests/test_workflow_summary.py`
- Modify: `tests/test_state.py`

- [ ] **Step 1: Write the failing tests**

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class WorkflowSummaryTests(unittest.TestCase):
    def test_render_workflow_summary_lists_stage_statuses_and_paths(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.workflow_summary import render_workflow_summary

        summary = WorkflowSummary(
            session_id="session-123",
            current_state="WaitForCEOApproval",
            current_stage="ProductDraft",
            prd_status="ready_for_review",
            dev_status="pending",
            qa_status="pending",
            acceptance_status="pending",
            human_decision="pending",
            qa_round=0,
            blocked_reason="",
            artifact_paths={
                "prd": "/tmp/prd.md",
                "workflow_summary": "/tmp/workflow_summary.md",
            },
        )

        rendered = render_workflow_summary(summary)

        self.assertIn("session_id: session-123", rendered)
        self.assertIn("current_state: WaitForCEOApproval", rendered)
        self.assertIn("prd_status: ready_for_review", rendered)
        self.assertIn("- prd: /tmp/prd.md", rendered)

    def test_state_store_creates_workflow_summary_for_new_session(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build a workflow")
            summary_path = store.workflow_summary_path(session.session_id)

            self.assertTrue(summary_path.exists())
            content = summary_path.read_text()
            self.assertIn("current_state: Intake", content)
            self.assertIn("prd_status: pending", content)


if __name__ == "__main__":
    unittest.main()
```

```python
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class StateTests(unittest.TestCase):
    def test_dev_artifact_name_matches_single_session_contract(self) -> None:
        from agent_team.state import artifact_name_for_stage

        self.assertEqual(artifact_name_for_stage("Dev"), "implementation.md")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_workflow_summary tests.test_state -v`
Expected: FAIL because `WorkflowSummary`, `render_workflow_summary()`, `workflow_summary_path()`, and the new Dev artifact name do not exist yet

- [ ] **Step 3: Write the minimal implementation**

Add the workflow summary model in `agent_team/models.py`:

```python
@dataclass(slots=True)
class WorkflowSummary:
    session_id: str
    current_state: str
    current_stage: str
    prd_status: str = "pending"
    dev_status: str = "pending"
    qa_status: str = "pending"
    acceptance_status: str = "pending"
    human_decision: str = "pending"
    qa_round: int = 0
    blocked_reason: str = ""
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

Create `agent_team/workflow_summary.py`:

```python
from __future__ import annotations

from .models import WorkflowSummary


def render_workflow_summary(summary: WorkflowSummary) -> str:
    lines = [
        "# Workflow Summary",
        "",
        f"session_id: {summary.session_id}",
        f"current_state: {summary.current_state}",
        f"current_stage: {summary.current_stage}",
        f"prd_status: {summary.prd_status}",
        f"dev_status: {summary.dev_status}",
        f"qa_status: {summary.qa_status}",
        f"acceptance_status: {summary.acceptance_status}",
        f"human_decision: {summary.human_decision}",
        f"qa_round: {summary.qa_round}",
        f"blocked_reason: {summary.blocked_reason or '-'}",
        "",
        "## Artifact Paths",
    ]

    for key, value in summary.artifact_paths.items():
        lines.append(f"- {key}: {value}")

    return "\n".join(lines).rstrip() + "\n"
```

Update `agent_team/state.py`:

```python
from .models import Finding, SessionRecord, StageOutput, StageRecord, WorkflowSummary
from .workflow_summary import render_workflow_summary


class StateStore:
    def create_session(self, request: str) -> SessionRecord:
        self.ensure_layout()
        session_id = self._next_session_id(request)
        artifact_dir = self.root / "artifacts" / session_id
        session_dir = self.root / "sessions" / session_id
        stages_dir = session_dir / "stages"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        stages_dir.mkdir(parents=True, exist_ok=True)

        session = SessionRecord(
            session_id=session_id,
            request=request,
            created_at=datetime.now(UTC).isoformat(),
            session_dir=session_dir,
            artifact_dir=artifact_dir,
        )
        self._write_json(session_dir / "session.json", session.to_dict())
        (artifact_dir / "request.md").write_text(f"# Workflow Request\n\n{request.strip()}\n")
        self.save_workflow_summary(
            session,
            WorkflowSummary(
                session_id=session.session_id,
                current_state="Intake",
                current_stage="Intake",
                artifact_paths={
                    "request": str(artifact_dir / "request.md"),
                    "workflow_summary": str(artifact_dir / "workflow_summary.md"),
                },
            ),
        )
        return session

    def workflow_summary_path(self, session_id: str) -> Path:
        return self.root / "artifacts" / session_id / "workflow_summary.md"

    def save_workflow_summary(self, session: SessionRecord, summary: WorkflowSummary) -> Path:
        path = self.workflow_summary_path(session.session_id)
        path.write_text(render_workflow_summary(summary))
        return path
```

Update artifact naming in `agent_team/state.py`:

```python
def artifact_name_for_stage(stage: str) -> str:
    return {
        "Product": "prd.md",
        "Dev": "implementation.md",
        "QA": "qa_report.md",
        "Acceptance": "acceptance_report.md",
        "Ops": "release_notes.md",
    }.get(stage, f"{stage.lower()}.md")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_workflow_summary tests.test_state -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent_team/models.py agent_team/state.py agent_team/workflow_summary.py tests/test_workflow_summary.py tests/test_state.py
git commit -m "feat: add workflow summary persistence"
```

### Task 2: Add CLI bootstrap commands for the skill-driven workflow

**Files:**
- Modify: `agent_team/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class CliTests(unittest.TestCase):
    def test_start_session_bootstraps_single_session_workflow(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            result = subprocess.run(
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
                    "执行这个需求：做一个必须先确认验收标准的流程",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("session_id:", result.stdout)
        self.assertIn("summary_path:", result.stdout)
        self.assertIn("artifact_dir:", result.stdout)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_cli -v`
Expected: FAIL because the `start-session` subcommand does not exist yet

- [ ] **Step 3: Write the minimal implementation**

Extend `agent_team/cli.py`:

```python
start_parser = subparsers.add_parser(
    "start-session",
    help="Create a session scaffold for the single-session Agent Team workflow.",
)
start_parser.add_argument("--message", required=True, help="Raw user message for the workflow.")
start_parser.set_defaults(handler=_handle_start_session)
```

```python
def _handle_start_session(args: argparse.Namespace) -> int:
    request = extract_request_from_message(args.message) or args.message.strip()
    store = StateStore(args.state_root)
    session = store.create_session(request)
    print(f"session_id: {session.session_id}")
    print(f"artifact_dir: {session.artifact_dir}")
    print(f"summary_path: {store.workflow_summary_path(session.session_id)}")
    return 0
```

Keep `run` and `agent-run`, but update their help text to describe them as deterministic runtime/demo commands rather than the preferred real workflow path.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_cli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent_team/cli.py tests/test_cli.py
git commit -m "feat: add workflow session bootstrap command"
```

### Task 3: Rewrite the root and packaged skills around the single-session state machine

**Files:**
- Modify: `SKILL.md`
- Modify: `codex-skill/agent-team-workflow/SKILL.md`
- Modify: `codex-skill/agent-team-workflow/scripts/agent-team-run.sh`
- Modify: `tests/test_skill_package.py`

- [ ] **Step 1: Write the failing tests**

```python
import unittest
from pathlib import Path


class SkillPackageTests(unittest.TestCase):
    def test_installable_skill_describes_single_session_state_machine(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        skill_path = repo_root / "codex-skill" / "agent-team-workflow" / "SKILL.md"
        content = skill_path.read_text()

        self.assertIn("start-session", content)
        self.assertIn("workflow_summary.md", content)
        self.assertIn("WaitForCEOApproval", content)
        self.assertIn("blocked", content)
        self.assertIn("recommended_go", content)

    def test_helper_script_bootstraps_session_instead_of_running_deterministic_backend(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        helper_script = repo_root / "codex-skill" / "agent-team-workflow" / "scripts" / "agent-team-run.sh"
        content = helper_script.read_text()

        self.assertIn("start-session", content)
        self.assertNotIn("agent-run --message", content)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_skill_package -v`
Expected: FAIL because the packaged skill and helper script still describe the deterministic `agent-run` flow

- [ ] **Step 3: Write the minimal implementation**

Update `SKILL.md` and `codex-skill/agent-team-workflow/SKILL.md` so they:

- describe the real state machine:
  - `Intake`
  - `ProductDraft`
  - `WaitForCEOApproval`
  - `Dev`
  - `QA`
  - `Acceptance`
  - `WaitForHumanDecision`
- require `prd.md`, `implementation.md`, `qa_report.md`, `acceptance_report.md`, and `workflow_summary.md`
- state that `QA` must independently rerun verification
- state that missing evidence forces `blocked`
- state that `Acceptance` recommends, but the human decides

Use wording like this in both skills:

```markdown
Bootstrap the workflow session first:
`python3 -m agent_team start-session --message "<the user's original message>"`

Then execute the workflow in the current Codex session using the artifact contract:
- `prd.md`
- `implementation.md`
- `qa_report.md`
- `acceptance_report.md`
- `workflow_summary.md`

Do not treat deterministic runtime output as real QA or Acceptance evidence.
```

Update `codex-skill/agent-team-workflow/scripts/agent-team-run.sh`:

```bash
cd "${RUNTIME_DIR}"
python3 -m agent_team start-session --message "${RAW_MESSAGE}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_skill_package -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add SKILL.md codex-skill/agent-team-workflow/SKILL.md codex-skill/agent-team-workflow/scripts/agent-team-run.sh tests/test_skill_package.py
git commit -m "feat: rewrite workflow skills for single-session execution"
```

### Task 4: Surface real workflow status in reviews and keep the deterministic runtime explicitly secondary

**Files:**
- Modify: `agent_team/review.py`
- Modify: `agent_team/cli.py`
- Modify: `tests/test_review.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest


class ReviewTests(unittest.TestCase):
    def test_review_includes_workflow_summary_statuses(self) -> None:
        from agent_team.models import WorkflowSummary
        from agent_team.review import build_session_review

        review = build_session_review(
            stage_artifacts={"Product": "accepted criteria", "QA": "passed"},
            findings=[],
            workflow_summary=WorkflowSummary(
                session_id="session-123",
                current_state="WaitForHumanDecision",
                current_stage="Acceptance",
                prd_status="approved",
                dev_status="completed",
                qa_status="passed",
                acceptance_status="recommended_go",
                human_decision="pending",
                qa_round=2,
                blocked_reason="",
                artifact_paths={},
            ),
        )

        self.assertIn("current_state: WaitForHumanDecision", review)
        self.assertIn("human_decision: pending", review)
        self.assertIn("qa_round: 2", review)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_review -v`
Expected: FAIL because `build_session_review()` does not accept workflow summary status yet

- [ ] **Step 3: Write the minimal implementation**

Update `agent_team/review.py`:

```python
from .models import Finding, WorkflowSummary


def build_session_review(
    *,
    stage_artifacts: dict[str, str],
    findings: list[Finding | dict[str, str]],
    acceptance_status: str = "pending",
    workflow_summary: WorkflowSummary | None = None,
) -> str:
    normalized_findings = [_normalize_finding(item) for item in findings]
    lines = ["# Session Review", ""]

    if workflow_summary is not None:
        lines.extend(
            [
                "## Workflow Status",
                "",
                f"current_state: {workflow_summary.current_state}",
                f"current_stage: {workflow_summary.current_stage}",
                f"prd_status: {workflow_summary.prd_status}",
                f"dev_status: {workflow_summary.dev_status}",
                f"qa_status: {workflow_summary.qa_status}",
                f"acceptance_status: {workflow_summary.acceptance_status}",
                f"human_decision: {workflow_summary.human_decision}",
                f"qa_round: {workflow_summary.qa_round}",
                "",
            ]
        )

    lines.extend(
        [
            f"acceptance_status: {acceptance_status}",
            "",
            "## Findings",
            "",
        ]
    )
```

Update CLI help strings so `run` and `agent-run` are clearly described as deterministic/demo commands, while `start-session` is the preferred entrypoint for the real skill-driven workflow.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_review -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent_team/review.py agent_team/cli.py tests/test_review.py
git commit -m "feat: expose workflow summary status in reviews"
```

### Task 5: Update README and docs to describe the new workflow contract

**Files:**
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `tests/test_docs.py`

- [ ] **Step 1: Write the failing tests**

```python
import unittest
from pathlib import Path


class DocsTests(unittest.TestCase):
    def test_readme_describes_single_session_workflow(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        readme = (repo_root / "README_zh.md").read_text()

        self.assertIn("workflow_summary.md", readme)
        self.assertIn("start-session", readme)
        self.assertIn("Product -> Dev <-> QA -> Acceptance", readme)
        self.assertIn("必须先确认验收标准", readme)

    def test_readme_describes_human_final_decision(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        readme = (repo_root / "README.md").read_text()

        self.assertIn("human Go/No-Go", readme)
        self.assertIn("blocked", readme)
        self.assertIn("independently rerun critical verification", readme)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_docs -v`
Expected: FAIL because the READMEs still describe the deterministic runtime as the main execution flow

- [ ] **Step 3: Write the minimal implementation**

Update both READMEs so they:

- describe the real workflow as `Product -> CEO approval -> Dev <-> QA -> Acceptance -> human Go/No-Go`
- explain that `superpower` TDD belongs to `Dev`, not `QA`
- explain that `QA` must independently rerun critical verification
- explain that missing evidence forces `blocked`
- document `workflow_summary.md`, `implementation.md`, and `start-session`
- clearly label `run` and `agent-run` as deterministic/demo runtime commands if they remain

Add wording like this:

```markdown
Preferred bootstrap command for the real workflow:
`python3 -m agent_team start-session --message "执行这个需求：..."`

The real workflow then runs in the active Codex session with stage artifacts:
- `prd.md`
- `implementation.md`
- `qa_report.md`
- `acceptance_report.md`
- `workflow_summary.md`

`QA` must independently rerun critical verification.
If real evidence is missing, the status must be `blocked`.
`Acceptance` gives a recommendation, but the human CEO makes the final Go/No-Go decision.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_docs -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md README_zh.md tests/test_docs.py
git commit -m "docs: describe the single-session Agent Team workflow"
```

### Task 6: Run the full regression suite and verify the packaging flow

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `tests/test_skill_package.py`
- Modify: `tests/test_docs.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_review.py`

- [ ] **Step 1: Run the targeted test suites before final polish**

Run: `python3 -m unittest tests.test_workflow_summary tests.test_state tests.test_cli tests.test_review tests.test_docs tests.test_skill_package -v`
Expected: PASS

- [ ] **Step 2: Run the full unit test suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 3: Verify the install script still packages the new flow**

Run: `python3 -m unittest tests.test_skill_package.SkillPackageTests.test_global_install_script_vendors_repo_and_skill -v`
Expected: PASS

- [ ] **Step 4: Verify the vendored helper script bootstraps a session**

Run: `python3 -m unittest tests.test_skill_package.SkillPackageTests.test_installed_helper_script_runs_from_vendored_runtime -v`
Expected: PASS with output containing `session_id:` and `summary_path:`

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py tests/test_skill_package.py tests/test_docs.py tests/test_state.py tests/test_review.py
git commit -m "test: verify single-session workflow end to end"
```
