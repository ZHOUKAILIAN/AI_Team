# Remove Ops Role Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Ops from the default Agent Team role set and documentation while keeping historical `Ops` artifact-name compatibility.

**Architecture:** Ops is removed from default role discovery, project scaffolding, role assets, and user-facing docs. The low-level `artifact_name_for_stage("Ops")` compatibility mapping remains so old session data can still be interpreted.

**Tech Stack:** Python 3.13, unittest, packaged resource files, Markdown docs.

---

### Task 1: Remove Ops From Default Runtime Role Lists

**Files:**
- Modify: `agent_team/roles.py`
- Modify: `agent_team/project_structure.py`
- Modify: `agent_team/state.py`
- Modify: `tests/test_project_structure.py`
- Modify: `tests/test_state.py`

- [ ] **Step 1: Write failing tests for default role removal and compatibility**

Add this assertion to `tests/test_project_structure.py::test_ensure_project_structure_creates_default_docs_when_missing` after the existing role file assertions:

```python
self.assertFalse((repo_root / "agent-team" / "project" / "roles" / "ops.context.md").exists())
```

Add this assertion to `tests/test_state.py::test_load_role_profiles_uses_packaged_assets_when_repo_roles_are_missing` after the existing role assertions:

```python
self.assertNotIn("Ops", roles)
```

Rename `tests/test_state.py::test_artifact_name_for_dev_stage_is_implementation` to `test_artifact_name_for_stage_keeps_ops_compatibility` and replace its body with:

```python
from agent_team.state import artifact_name_for_stage

self.assertEqual(artifact_name_for_stage("Dev"), "implementation.md")
self.assertEqual(artifact_name_for_stage("Ops"), "release_notes.md")
```

Add this test to `tests/test_state.py` near `test_apply_learning_ignores_unknown_target_stage`:

```python
def test_apply_learning_ignores_ops_as_removed_default_role(self) -> None:
    from agent_team.models import Finding
    from agent_team.state import StateStore

    with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
        root = Path(temp_dir)
        StateStore(root).apply_learning(
            Finding(
                source_stage="Acceptance",
                target_stage="Ops",
                issue="legacy release note follow-up",
                lesson="legacy ops learning should not create a default role overlay",
            )
        )

        self.assertFalse((root / "memory" / "Ops").exists())
```

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run:

```bash
python -m unittest tests.test_project_structure tests.test_state
```

Expected: failures mentioning `ops.context.md`, `Ops` still present in loaded roles, or `memory/Ops` being created.

- [ ] **Step 3: Update runtime role defaults**

In `agent_team/roles.py`, change:

```python
DEFAULT_ROLE_NAMES = ("Product", "TechPlan", "Dev", "QA", "Acceptance", "Ops")
```

to:

```python
DEFAULT_ROLE_NAMES = ("Product", "TechPlan", "Dev", "QA", "Acceptance")
```

In `agent_team/project_structure.py`, change `ROLE_SLUGS` from:

```python
ROLE_SLUGS = {
    "Product": "product",
    "TechPlan": "techplan",
    "Dev": "dev",
    "QA": "qa",
    "Acceptance": "acceptance",
    "Ops": "ops",
}
```

to:

```python
ROLE_SLUGS = {
    "Product": "product",
    "TechPlan": "techplan",
    "Dev": "dev",
    "QA": "qa",
    "Acceptance": "acceptance",
}
```

In `agent_team/state.py`, change:

```python
VALID_ROLE_NAMES = {"Product", "TechPlan", "Dev", "QA", "Acceptance", "Ops"}
```

to:

```python
VALID_ROLE_NAMES = {"Product", "TechPlan", "Dev", "QA", "Acceptance"}
```

Keep this mapping unchanged:

```python
"Ops": "release_notes.md",
```

- [ ] **Step 4: Run targeted tests and verify they pass**

Run:

```bash
python -m unittest tests.test_project_structure tests.test_state
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add agent_team/roles.py agent_team/project_structure.py agent_team/state.py tests/test_project_structure.py tests/test_state.py
git commit -m "refactor: remove ops from default roles"
```

---

### Task 2: Delete Ops Assets and Remove Role Text References

**Files:**
- Delete: `Ops/SKILL.md`
- Delete: `Ops/context.md`
- Delete: `Ops/memory.md`
- Delete: `agent_team/assets/roles/Ops/SKILL.md`
- Delete: `agent_team/assets/roles/Ops/context.md`
- Delete: `agent_team/assets/roles/Ops/memory.md`
- Modify: `Product/context.md`
- Modify: `agent_team/assets/roles/Product/context.md`
- Modify: `agent_team/assets/roles/Product/SKILL.md`

- [ ] **Step 1: Write failing packaged asset tests**

Add this test to `tests/test_packaged_assets.py`:

```python
def test_ops_role_assets_are_removed(self) -> None:
    repo_root = Path(__file__).resolve().parents[1]

    self.assertFalse((repo_root / "Ops").exists())
    self.assertFalse((repo_root / "agent_team" / "assets" / "roles" / "Ops").exists())
```

- [ ] **Step 2: Run the packaged asset test and verify it fails**

Run:

```bash
python -m unittest tests.test_packaged_assets
```

Expected: failure because `Ops/` and `agent_team/assets/roles/Ops/` still exist.

- [ ] **Step 3: Delete Ops asset trees**

Delete these directories:

```text
Ops/
agent_team/assets/roles/Ops/
```

Use non-interactive deletion:

```bash
rm -rf Ops agent_team/assets/roles/Ops
```

- [ ] **Step 4: Remove Ops references from Product role text**

In `Product/context.md` and `agent_team/assets/roles/Product/context.md`, change:

```markdown
- **Cross-Functional Alignment**: Maintain a shared understanding of product goals, priorities, and roadmap across Dev, QA, and Ops teams.
```

to:

```markdown
- **Cross-Functional Alignment**: Maintain a shared understanding of product goals, priorities, and roadmap across Dev and QA teams.
```

In `agent_team/assets/roles/Product/SKILL.md`, change:

```markdown
- Product must not overwrite TechPlan, Dev, QA, Acceptance, or Ops artifacts.
```

to:

```markdown
- Product must not overwrite TechPlan, Dev, QA, or Acceptance artifacts.
```

- [ ] **Step 5: Run asset and role-text checks**

Run:

```bash
python -m unittest tests.test_packaged_assets
rg -n "\\bOps\\b|ops team|Ops artifacts" Product agent_team/assets/roles --glob '!agent_team/assets/roles/Ops/**'
```

Expected: unittest passes; `rg` returns no matches.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add -A Ops agent_team/assets/roles/Ops Product/context.md agent_team/assets/roles/Product/context.md agent_team/assets/roles/Product/SKILL.md tests/test_packaged_assets.py
git commit -m "refactor: remove ops role assets"
```

---

### Task 3: Update User-Facing Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/workflow-specs/2026-04-11-agent-team-cli-runtime-design.md`
- Modify: `docs/workflow-specs/2026-04-11-agent-team-codex-harness-solution.md`
- Modify: `tests/test_docs.py`

- [ ] **Step 1: Write failing docs tests**

In `tests/test_docs.py::test_readme_positions_project_as_cli_runtime_framework`, add:

```python
self.assertNotIn("Ops", readme)
```

In `tests/test_docs.py::test_readme_keeps_authoritative_team_workflow_contract`, add:

```python
self.assertNotIn("Ops", readme)
```

Add this test to `tests/test_docs.py`:

```python
def test_runtime_docs_do_not_list_ops_as_default_role(self) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    docs = [
        repo_root / "docs" / "workflow-specs" / "2026-04-11-agent-team-cli-runtime-design.md",
        repo_root / "docs" / "workflow-specs" / "2026-04-11-agent-team-codex-harness-solution.md",
    ]

    for path in docs:
        self.assertNotIn("Ops", path.read_text(), msg=str(path))
```

- [ ] **Step 2: Run docs tests and verify they fail**

Run:

```bash
python -m unittest tests.test_docs
```

Expected: failure because README and workflow docs still mention Ops.

- [ ] **Step 3: Update README**

In `README.md`, remove `Ops` from the default team list:

```markdown
- `Product`
- `TechPlan`
- `Dev`
- `QA`
- `Acceptance`
```

Replace role path bullets that include Ops with:

```markdown
- `Product/`
- `Dev/`
- `QA/`
- `Acceptance/`
- `agent_team/assets/roles/`
```

Ensure the authoritative flow remains:

```text
Product -> CEO approval -> TechPlan -> Dev <-> QA -> Acceptance -> human Go/No-Go
```

- [ ] **Step 4: Update workflow docs**

In `docs/workflow-specs/2026-04-11-agent-team-cli-runtime-design.md`, change:

```markdown
- Product / Dev / QA / Acceptance / Ops 这些角色定义
```

to:

```markdown
- Product / TechPlan / Dev / QA / Acceptance 这些角色定义
```

In `docs/workflow-specs/2026-04-11-agent-team-codex-harness-solution.md`, remove `Ops/` from the role directory list and keep the remaining role directories.

- [ ] **Step 5: Run docs tests and verify they pass**

Run:

```bash
python -m unittest tests.test_docs
rg -n "\\bOps\\b" README.md docs/workflow-specs
```

Expected: unittest passes; `rg` returns no matches.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add README.md docs/workflow-specs/2026-04-11-agent-team-cli-runtime-design.md docs/workflow-specs/2026-04-11-agent-team-codex-harness-solution.md tests/test_docs.py
git commit -m "docs: remove ops from default team docs"
```

---

### Task 4: Final Regression and Residual Search

**Files:**
- Verify only, no planned source edits.

- [ ] **Step 1: Run focused regression tests**

Run:

```bash
python -m unittest tests.test_project_structure tests.test_state tests.test_packaged_assets tests.test_docs tests.test_runtime_driver tests.test_cli
```

Expected: all tests pass.

- [ ] **Step 2: Run residual Ops search**

Run:

```bash
rg -n "\\bOps\\b|ops team|Ops artifacts" README.md docs agent_team Product Dev QA Acceptance tests --glob '!agent_team/web_dist/**'
```

Expected: no matches except the compatibility mapping in `agent_team/state.py` and any deliberate test assertion that verifies the compatibility mapping.

- [ ] **Step 3: Confirm deleted assets**

Run:

```bash
test ! -e Ops
test ! -e agent_team/assets/roles/Ops
```

Expected: both commands exit with code 0.

- [ ] **Step 4: Commit any final cleanup**

If Task 4 surfaced final cleanup changes, commit them:

```bash
git add -A
git commit -m "test: verify ops removal compatibility"
```

If there are no final cleanup changes, skip this commit.
