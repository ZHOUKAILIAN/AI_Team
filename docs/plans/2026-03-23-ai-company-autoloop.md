# AI Company Autoloop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local, runnable workflow engine that orchestrates Product -> Dev -> QA -> Acceptance, persists per-agent context and memory, records full execution history, computes artifact diffs, and feeds downstream findings back into agent learning records.

**Architecture:** Implement a Python standard-library CLI and runtime under `src/ai_company/`. The runtime will load role definitions from the existing `Product/`, `Dev/`, `QA/`, and `Acceptance/` folders, execute a deterministic stage pipeline through a pluggable backend, and persist structured session state under `.ai_company_state/`. Learning will be captured as append-only lessons and structured improvement proposals rather than directly mutating role prompts in-place.

**Tech Stack:** Python 3.13, `unittest`, `argparse`, `dataclasses`, `json`, `difflib`, Markdown artifacts

---

### Task 1: Bootstrap the Python project and CLI entrypoint

**Files:**
- Create: `pyproject.toml`
- Create: `src/ai_company/__init__.py`
- Create: `src/ai_company/__main__.py`
- Create: `src/ai_company/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
import subprocess
import sys


def test_cli_help_exits_successfully():
    result = subprocess.run(
        [sys.executable, "-m", "ai_company", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "run" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_cli -v`
Expected: FAIL because the package and entrypoint do not exist yet

**Step 3: Write minimal implementation**

Create a package with a CLI exposing:
- `run`: execute the workflow
- `review`: review the latest session
- `init-state`: create required state directories

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_cli -v`
Expected: PASS

### Task 2: Add role loading, state persistence, and artifact bookkeeping

**Files:**
- Create: `src/ai_company/models.py`
- Create: `src/ai_company/state.py`
- Create: `src/ai_company/roles.py`
- Create: `tests/test_state.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from ai_company.roles import load_role_profiles
from ai_company.state import StateStore


def test_state_store_initializes_session_and_artifacts(tmp_path: Path):
    store = StateStore(tmp_path)
    session = store.create_session("demo")
    assert (tmp_path / "sessions" / session.session_id / "session.json").exists()
    assert (tmp_path / "artifacts" / session.session_id).exists()


def test_load_role_profiles_reads_context_and_memory(repo_root: Path):
    roles = load_role_profiles(repo_root)
    assert "Product" in roles
    assert "Dev" in roles
    assert "Product Manager Onboarding Manual" in roles["Product"].context_text
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_state -v`
Expected: FAIL because the store and role loader do not exist yet

**Step 3: Write minimal implementation**

Implement:
- `RoleProfile` and `SessionRecord` models
- state directory bootstrap under `.ai_company_state/`
- session files, stage logs, and artifact folders
- role loading from `<Role>/context.md` and `<Role>/memory.md`

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_state -v`
Expected: PASS

### Task 3: Implement the stage pipeline and downstream feedback learning loop

**Files:**
- Create: `src/ai_company/backend.py`
- Create: `src/ai_company/orchestrator.py`
- Create: `tests/test_orchestrator.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from ai_company.backend import StaticBackend
from ai_company.orchestrator import WorkflowOrchestrator
from ai_company.state import StateStore


def test_downstream_findings_create_learning_records(tmp_path: Path, repo_root: Path):
    backend = StaticBackend.fixture(
        product_requirements="Users can create a task",
        prd="PRD v1",
        tech_spec="Tech spec v1",
        qa_report="QA found missing delete flow",
        acceptance_report="Rejected because delete flow missing",
        findings=[
            {
                "source_stage": "QA",
                "target_stage": "Product",
                "issue": "Delete flow missing from PRD",
                "severity": "high",
                "lesson": "Enumerate CRUD scope explicitly",
            }
        ],
    )
    store = StateStore(tmp_path)
    result = WorkflowOrchestrator(repo_root=repo_root, state_store=store, backend=backend).run(
        request="Build a task manager"
    )
    product_memory = (repo_root / "Product" / "memory.md").read_text()
    assert result.acceptance_status == "rejected"
    assert "CRUD scope explicitly" in product_memory
    assert (tmp_path / "sessions" / result.session_id / "review.md").exists()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_orchestrator -v`
Expected: FAIL because the workflow engine and learning loop do not exist yet

**Step 3: Write minimal implementation**

Implement:
- deterministic stage order: Product -> Dev -> QA -> Acceptance
- backend contract returning artifact text, findings, and acceptance decision
- learning loop that appends validated lessons to the target role memory
- review report generation for the session

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_orchestrator -v`
Expected: PASS

### Task 4: Add artifact diffs, stage journals, and improvement proposals

**Files:**
- Modify: `src/ai_company/orchestrator.py`
- Modify: `src/ai_company/state.py`
- Create: `src/ai_company/review.py`
- Create: `tests/test_review.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from ai_company.review import build_session_review


def test_review_includes_artifact_diff_and_improvement_proposals(tmp_path: Path):
    review = build_session_review(
        stage_artifacts={
            "Product": "scope: create, edit",
            "QA": "scope missing: delete",
        },
        findings=[
            {
                "source_stage": "QA",
                "target_stage": "Product",
                "issue": "Delete flow missing",
                "severity": "high",
                "proposed_context_update": "Always expand user actions into CRUD coverage.",
            }
        ],
    )
    assert "Delete flow missing" in review
    assert "--- Product" in review
    assert "proposed_context_update" in review
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_review -v`
Expected: FAIL because the review builder does not exist yet

**Step 3: Write minimal implementation**

Generate:
- unified diffs between upstream artifact expectations and downstream findings
- stage journals saved per session
- structured improvement proposals saved under `.ai_company_state/memory/`

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_review -v`
Expected: PASS

### Task 5: Update repo docs and seed the runtime state model

**Files:**
- Modify: `README.md`
- Modify: `README_zh.md`
- Create: `.ai_company_state/README.md`
- Create: `.ai_company_state/memory/.gitkeep`
- Create: `.ai_company_state/sessions/.gitkeep`
- Create: `.ai_company_state/artifacts/.gitkeep`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_readme_documents_run_and_review_commands(repo_root: Path):
    readme = (repo_root / "README_zh.md").read_text()
    assert "python3 -m ai_company run" in readme
    assert "学习闭环" in readme
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_docs -v`
Expected: FAIL because the docs do not describe the runtime yet

**Step 3: Write minimal implementation**

Document:
- how to initialize state
- how to run a workflow
- where artifacts, journals, findings, and learning records are stored
- what remains manual vs. automatic

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_docs -v`
Expected: PASS
