# Agent Team Run Interactive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `agent-team run-interactive` as a terminal harness that confirms requirement and acceptance criteria once, then drives Product, Dev, QA, and Acceptance through existing Agent Team runtime gates using `codex exec`.

**Architecture:** Add focused orchestration modules under `agent_team`: alignment parsing/prompting, `codex exec` subprocess wrapper, stage harness, and interactive flow controller. Existing `StateStore`, `StageMachine`, stage contracts, execution contexts, stage result verification, and human decision APIs remain authoritative.

**Tech Stack:** Python 3.13+, argparse, dataclasses, subprocess, JSON, unittest, existing Agent Team runtime modules.

---

## File Structure

- Create `agent_team/alignment.py`
  - Owns alignment dataclasses, JSON parsing, rendering, prompt building, and persistence paths.
- Create `agent_team/codex_exec.py`
  - Owns `codex exec` command construction and subprocess execution.
- Create `agent_team/stage_harness.py`
  - Owns one-stage execution through existing runtime APIs plus `codex exec`.
- Create `agent_team/interactive.py`
  - Owns terminal prompts, confirmation loop, session creation/resume, Product auto-approval, and workflow loop.
- Modify `agent_team/cli.py`
  - Registers `run-interactive` and delegates to `interactive.run_interactive`.
- Modify `agent_team/project_scaffold.py`
  - Updates generated `agent-team-run` skill text to recommend `agent-team run-interactive` for terminal usage.
- Modify `agent_team/assets/codex_skill/agent-team-workflow/SKILL.md`
  - Documents terminal harness behavior.
- Modify `codex-skill/agent-team-workflow/SKILL.md`
  - Keeps installable skill source in sync.
- Create `tests/test_alignment.py`
  - Unit tests for alignment parsing, validation, rendering, and persistence.
- Create `tests/test_codex_exec.py`
  - Unit tests for command construction and output capture.
- Create `tests/test_stage_harness.py`
  - Unit tests for stage prompt construction and stage execution with fake runner.
- Create `tests/test_run_interactive.py`
  - Unit and integration-style tests for CLI flow using fake input and fake Codex.
- Modify `tests/test_cli.py`
  - Adds parser/CLI smoke coverage for `run-interactive --help`.

## Task 1: Alignment Model and Parser

**Files:**
- Create: `agent_team/alignment.py`
- Create: `tests/test_alignment.py`

- [ ] **Step 1: Write failing parser tests**

Create `tests/test_alignment.py` with:

```python
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_team.alignment import (
    AlignmentCriterion,
    AlignmentDraft,
    alignment_prompt,
    load_confirmed_alignment,
    parse_alignment_json,
    render_alignment_for_terminal,
    save_confirmed_alignment,
)


class AlignmentTests(unittest.TestCase):
    def test_parse_alignment_json_requires_acceptance_criteria(self) -> None:
        payload = {
            "requirement_understanding": ["Add a profile editor."],
            "scope": {"in_scope": ["Edit nickname"], "out_of_scope": ["Avatar upload"]},
            "acceptance_criteria": [],
            "clarifying_questions": [],
        }

        with self.assertRaisesRegex(ValueError, "acceptance_criteria"):
            parse_alignment_json(json.dumps(payload))

    def test_parse_alignment_json_returns_structured_draft(self) -> None:
        payload = {
            "requirement_understanding": ["Add a profile editor."],
            "scope": {"in_scope": ["Edit nickname"], "out_of_scope": ["Avatar upload"]},
            "acceptance_criteria": [
                {
                    "id": "AC1",
                    "criterion": "Users can save a nickname.",
                    "verification": "Run profile edit happy-path test.",
                }
            ],
            "clarifying_questions": ["Should nickname length be limited?"],
        }

        draft = parse_alignment_json(json.dumps(payload))

        self.assertEqual(draft.requirement_understanding, ["Add a profile editor."])
        self.assertEqual(draft.scope["in_scope"], ["Edit nickname"])
        self.assertEqual(
            draft.acceptance_criteria,
            [
                AlignmentCriterion(
                    id="AC1",
                    criterion="Users can save a nickname.",
                    verification="Run profile edit happy-path test.",
                )
            ],
        )
        self.assertEqual(draft.clarifying_questions, ["Should nickname length be limited?"])

    def test_render_alignment_for_terminal_is_readable(self) -> None:
        draft = AlignmentDraft(
            requirement_understanding=["Add a profile editor."],
            scope={"in_scope": ["Edit nickname"], "out_of_scope": ["Avatar upload"]},
            acceptance_criteria=[
                AlignmentCriterion(
                    id="AC1",
                    criterion="Users can save a nickname.",
                    verification="Run profile edit happy-path test.",
                )
            ],
            clarifying_questions=[],
        )

        rendered = render_alignment_for_terminal(draft)

        self.assertIn("Requirement understanding", rendered)
        self.assertIn("AC1", rendered)
        self.assertIn("Users can save a nickname.", rendered)
        self.assertIn("Run profile edit happy-path test.", rendered)

    def test_save_and_load_confirmed_alignment_round_trip(self) -> None:
        draft = AlignmentDraft(
            requirement_understanding=["Add a profile editor."],
            scope={"in_scope": ["Edit nickname"], "out_of_scope": []},
            acceptance_criteria=[
                AlignmentCriterion(
                    id="AC1",
                    criterion="Users can save a nickname.",
                    verification="Run profile edit happy-path test.",
                )
            ],
            clarifying_questions=[],
        )

        with TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir)
            path = save_confirmed_alignment(session_dir, draft)

            self.assertEqual(path, session_dir / "confirmed_alignment.json")
            self.assertEqual(load_confirmed_alignment(session_dir), draft)

    def test_alignment_prompt_includes_previous_revision(self) -> None:
        prompt = alignment_prompt(
            raw_request="执行这个需求：Add profile editor",
            previous_alignment='{"acceptance_criteria": []}',
            user_revision="Limit nickname to 20 chars.",
        )

        self.assertIn("Add profile editor", prompt)
        self.assertIn("Limit nickname to 20 chars.", prompt)
        self.assertIn("strict JSON", prompt)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run parser tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_alignment
```

Expected: FAIL because `agent_team.alignment` does not exist.

- [ ] **Step 3: Implement alignment dataclasses and parsing**

Create `agent_team/alignment.py` with:

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


CONFIRMED_ALIGNMENT_NAME = "confirmed_alignment.json"


@dataclass(slots=True)
class AlignmentCriterion:
    id: str
    criterion: str
    verification: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AlignmentCriterion":
        criterion_id = str(payload.get("id", "")).strip()
        criterion = str(payload.get("criterion", "")).strip()
        verification = str(payload.get("verification", "")).strip()
        if not criterion_id:
            raise ValueError("acceptance_criteria item is missing id")
        if not criterion:
            raise ValueError(f"acceptance_criteria {criterion_id} is missing criterion")
        if not verification:
            raise ValueError(f"acceptance_criteria {criterion_id} is missing verification")
        return cls(id=criterion_id, criterion=criterion, verification=verification)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class AlignmentDraft:
    requirement_understanding: list[str]
    scope: dict[str, list[str]]
    acceptance_criteria: list[AlignmentCriterion]
    clarifying_questions: list[str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AlignmentDraft":
        understanding = _string_list(payload.get("requirement_understanding", []))
        if not understanding:
            raise ValueError("requirement_understanding must contain at least one item")

        scope_payload = payload.get("scope", {})
        if not isinstance(scope_payload, dict):
            raise ValueError("scope must be an object")
        scope = {
            "in_scope": _string_list(scope_payload.get("in_scope", [])),
            "out_of_scope": _string_list(scope_payload.get("out_of_scope", [])),
        }

        criteria_payload = payload.get("acceptance_criteria", [])
        if not isinstance(criteria_payload, list) or not criteria_payload:
            raise ValueError("acceptance_criteria must contain at least one item")
        criteria = [
            AlignmentCriterion.from_dict(item if isinstance(item, dict) else {})
            for item in criteria_payload
        ]

        return cls(
            requirement_understanding=understanding,
            scope=scope,
            acceptance_criteria=criteria,
            clarifying_questions=_string_list(payload.get("clarifying_questions", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_understanding": list(self.requirement_understanding),
            "scope": {
                "in_scope": list(self.scope.get("in_scope", [])),
                "out_of_scope": list(self.scope.get("out_of_scope", [])),
            },
            "acceptance_criteria": [item.to_dict() for item in self.acceptance_criteria],
            "clarifying_questions": list(self.clarifying_questions),
        }


def parse_alignment_json(raw: str) -> AlignmentDraft:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"alignment output is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("alignment output must be a JSON object")
    return AlignmentDraft.from_dict(payload)


def render_alignment_for_terminal(draft: AlignmentDraft) -> str:
    lines = ["Requirement understanding:"]
    lines.extend(f"- {item}" for item in draft.requirement_understanding)
    lines.append("")
    lines.append("Scope boundary:")
    lines.append("- In scope:")
    lines.extend(f"  - {item}" for item in draft.scope.get("in_scope", []))
    lines.append("- Out of scope:")
    lines.extend(f"  - {item}" for item in draft.scope.get("out_of_scope", []))
    lines.append("")
    lines.append("Acceptance criteria:")
    for item in draft.acceptance_criteria:
        lines.append(f"{item.id}. {item.criterion}")
        lines.append(f"   Verification: {item.verification}")
    if draft.clarifying_questions:
        lines.append("")
        lines.append("Clarifying questions:")
        lines.extend(f"- {item}" for item in draft.clarifying_questions)
    return "\n".join(lines)


def alignment_prompt(
    *,
    raw_request: str,
    previous_alignment: str = "",
    user_revision: str = "",
) -> str:
    parts = [
        "You are the Intake/Product alignment role for Agent Team.",
        "Align the user's requirement and draft measurable acceptance criteria.",
        "Return strict JSON only. Do not wrap it in markdown.",
        "",
        "Required JSON shape:",
        "{",
        '  "requirement_understanding": ["..."],',
        '  "scope": {"in_scope": ["..."], "out_of_scope": ["..."]},',
        '  "acceptance_criteria": [{"id": "AC1", "criterion": "...", "verification": "..."}],',
        '  "clarifying_questions": ["..."]',
        "}",
        "",
        "Raw request:",
        raw_request.strip(),
    ]
    if previous_alignment.strip():
        parts.extend(["", "Previous alignment JSON:", previous_alignment.strip()])
    if user_revision.strip():
        parts.extend(["", "User revision:", user_revision.strip()])
    return "\n".join(parts)


def save_confirmed_alignment(session_dir: Path, draft: AlignmentDraft) -> Path:
    path = session_dir / CONFIRMED_ALIGNMENT_NAME
    path.write_text(json.dumps(draft.to_dict(), ensure_ascii=False, indent=2))
    return path


def load_confirmed_alignment(session_dir: Path) -> AlignmentDraft | None:
    path = session_dir / CONFIRMED_ALIGNMENT_NAME
    if not path.exists():
        return None
    return parse_alignment_json(path.read_text())


def acceptance_criteria_strings(draft: AlignmentDraft) -> list[str]:
    return [
        f"{item.id}: {item.criterion} Verification: {item.verification}"
        for item in draft.acceptance_criteria
    ]


def confirmed_request_text(raw_request: str, draft: AlignmentDraft) -> str:
    rendered = render_alignment_for_terminal(draft)
    return f"{raw_request.strip()}\n\nConfirmed alignment:\n{rendered}\n"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
```

- [ ] **Step 4: Run parser tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_alignment
```

Expected: OK.

- [ ] **Step 5: Commit alignment parser**

```bash
git add agent_team/alignment.py tests/test_alignment.py
git commit -m "Add Agent Team alignment parser"
```

## Task 2: Codex Exec Wrapper

**Files:**
- Create: `agent_team/codex_exec.py`
- Create: `tests/test_codex_exec.py`

- [ ] **Step 1: Write failing command-construction tests**

Create `tests/test_codex_exec.py` with:

```python
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_team.codex_exec import CodexExecConfig, CodexExecResult, CodexExecRunner


class CodexExecTests(unittest.TestCase):
    def test_build_command_uses_json_and_output_last_message(self) -> None:
        config = CodexExecConfig(
            repo_root=Path("/repo"),
            codex_bin="codex",
            output_last_message=Path("/tmp/last.txt"),
            model="gpt-5.5",
            sandbox="workspace-write",
            approval="never",
            profile="default",
        )

        command = config.build_command("Prompt")

        self.assertEqual(command[:4], ["codex", "exec", "--cd", "/repo"])
        self.assertIn("--json", command)
        self.assertIn("--output-last-message", command)
        self.assertIn("/tmp/last.txt", command)
        self.assertIn("--model", command)
        self.assertIn("gpt-5.5", command)
        self.assertIn("--sandbox", command)
        self.assertIn("workspace-write", command)
        self.assertIn("--ask-for-approval", command)
        self.assertIn("never", command)
        self.assertIn("--profile", command)
        self.assertIn("default", command)
        self.assertEqual(command[-1], "Prompt")

    def test_runner_writes_prompt_and_captures_output(self) -> None:
        calls = []

        def fake_run(command, *, capture_output, text, check):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout='{"event":"done"}\n', stderr="")

        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "last.txt"
            output_path.write_text('{"result": "ok"}')
            runner = CodexExecRunner(run=fake_run)
            result = runner.run(
                CodexExecConfig(
                    repo_root=Path(temp_dir),
                    codex_bin="codex",
                    output_last_message=output_path,
                ),
                "Prompt",
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.last_message, '{"result": "ok"}')
        self.assertEqual(calls[0][-1], "Prompt")

    def test_result_success_reflects_return_code(self) -> None:
        self.assertTrue(CodexExecResult(0, "", "", "").success)
        self.assertFalse(CodexExecResult(1, "", "", "").success)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run wrapper tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_codex_exec
```

Expected: FAIL because `agent_team.codex_exec` does not exist.

- [ ] **Step 3: Implement subprocess wrapper**

Create `agent_team/codex_exec.py` with:

```python
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


RunCallable = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(slots=True)
class CodexExecConfig:
    repo_root: Path
    codex_bin: str = "codex"
    output_last_message: Path | None = None
    model: str = ""
    sandbox: str = "workspace-write"
    approval: str = "never"
    profile: str = ""

    def build_command(self, prompt: str) -> list[str]:
        command = [
            self.codex_bin,
            "exec",
            "--cd",
            str(self.repo_root),
            "--json",
        ]
        if self.output_last_message is not None:
            command.extend(["--output-last-message", str(self.output_last_message)])
        if self.model:
            command.extend(["--model", self.model])
        if self.sandbox:
            command.extend(["--sandbox", self.sandbox])
        if self.approval:
            command.extend(["--ask-for-approval", self.approval])
        if self.profile:
            command.extend(["--profile", self.profile])
        command.append(prompt)
        return command


@dataclass(slots=True)
class CodexExecResult:
    returncode: int
    stdout: str
    stderr: str
    last_message: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


class CodexExecRunner:
    def __init__(self, *, run: RunCallable | None = None) -> None:
        self._run = run or subprocess.run

    def run(self, config: CodexExecConfig, prompt: str) -> CodexExecResult:
        command = config.build_command(prompt)
        result = self._run(command, capture_output=True, text=True, check=False)
        last_message = ""
        if config.output_last_message is not None and config.output_last_message.exists():
            last_message = config.output_last_message.read_text()
        return CodexExecResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            last_message=last_message,
        )
```

- [ ] **Step 4: Run wrapper tests**

Run:

```bash
python3 -m unittest tests.test_codex_exec
```

Expected: OK.

- [ ] **Step 5: Commit wrapper**

```bash
git add agent_team/codex_exec.py tests/test_codex_exec.py
git commit -m "Add Codex exec runner"
```

## Task 3: Stage Harness

**Files:**
- Create: `agent_team/stage_harness.py`
- Create: `tests/test_stage_harness.py`

- [ ] **Step 1: Write failing tests for prompt and stage execution**

Create `tests/test_stage_harness.py` with:

```python
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_team.alignment import AlignmentCriterion, AlignmentDraft, save_confirmed_alignment
from agent_team.codex_exec import CodexExecResult
from agent_team.models import StageContract
from agent_team.stage_harness import StageHarness, stage_prompt


class FakeRunner:
    def __init__(self, last_message: str) -> None:
        self.last_message = last_message
        self.prompts = []

    def run(self, config, prompt):
        self.prompts.append(prompt)
        config.output_last_message.write_text(self.last_message)
        return CodexExecResult(0, "", "", self.last_message)


class StageHarnessTests(unittest.TestCase):
    def test_stage_prompt_includes_context_contract_and_alignment(self) -> None:
        prompt = stage_prompt(
            stage="Product",
            execution_context={"session_id": "s1", "stage": "Product"},
            contract=StageContract(
                session_id="s1",
                stage="Product",
                goal="Draft PRD",
                contract_id="abc",
                required_outputs=["prd.md"],
                evidence_requirements=["explicit_acceptance_criteria"],
            ),
            confirmed_alignment={
                "acceptance_criteria": [{"id": "AC1", "criterion": "It works", "verification": "Run test"}]
            },
        )

        self.assertIn("Product", prompt)
        self.assertIn("StageResultEnvelope", prompt)
        self.assertIn("abc", prompt)
        self.assertIn("explicit_acceptance_criteria", prompt)
        self.assertIn("AC1", prompt)

    def test_run_stage_submits_verified_result(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()
            store = StateStore(Path(temp_dir) / "state")
            alignment = AlignmentDraft(
                requirement_understanding=["Do the thing"],
                scope={"in_scope": ["Thing"], "out_of_scope": []},
                acceptance_criteria=[
                    AlignmentCriterion("AC1", "Thing is done", "Inspect PRD")
                ],
                clarifying_questions=[],
            )
            session = store.create_session("Do the thing", raw_message="Do the thing")
            save_confirmed_alignment(session.session_dir, alignment)
            bundle = {
                "session_id": session.session_id,
                "contract_id": "model-output-contract-id",
                "stage": "Product",
                "status": "completed",
                "artifact_name": "prd.md",
                "artifact_content": "# Product PRD\n\n## Acceptance Criteria\n- Thing is done\n",
                "journal": "# Journal\n",
                "findings": [],
                "evidence": [
                    {
                        "name": "explicit_acceptance_criteria",
                        "kind": "report",
                        "summary": "Criteria documented.",
                    }
                ],
                "summary": "Drafted PRD",
            }
            runner = FakeRunner(json.dumps(bundle))
            harness = StageHarness(repo_root=repo_root, state_store=store, codex_runner=runner)

            record = harness.run_stage(session.session_id, "Product")

        self.assertEqual(record.stage, "Product")
        self.assertTrue(runner.prompts)
```

- [ ] **Step 2: Run stage harness tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_stage_harness
```

Expected: FAIL because `agent_team.stage_harness` does not exist.

- [ ] **Step 3: Implement stage harness**

Create `agent_team/stage_harness.py` with:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .alignment import load_confirmed_alignment
from .codex_exec import CodexExecConfig, CodexExecRunner
from .execution_context import build_stage_execution_context
from .models import StageContract, StageResultEnvelope, StageRunRecord
from .stage_contracts import build_stage_contract
from .state import StateStore


def stage_prompt(
    *,
    stage: str,
    execution_context: dict[str, Any],
    contract: StageContract,
    confirmed_alignment: dict[str, Any],
) -> str:
    return "\n".join(
        [
            f"You are the {stage} stage worker for Agent Team.",
            "Use the provided execution context and stage contract as the source of truth.",
            "Return strict JSON only, compatible with StageResultEnvelope.",
            "Do not wrap the JSON in markdown.",
            "",
            "StageResultEnvelope required keys:",
            "session_id, contract_id, stage, status, artifact_name, artifact_content, journal, findings, evidence, summary",
            "",
            "Execution context JSON:",
            json.dumps(execution_context, ensure_ascii=False, indent=2),
            "",
            "Stage contract JSON:",
            json.dumps(contract.to_dict(), ensure_ascii=False, indent=2),
            "",
            "Confirmed alignment JSON:",
            json.dumps(confirmed_alignment, ensure_ascii=False, indent=2),
        ]
    )


@dataclass(slots=True)
class StageHarness:
    repo_root: Path
    state_store: StateStore
    codex_runner: CodexExecRunner
    codex_bin: str = "codex"
    model: str = ""
    sandbox: str = "workspace-write"
    approval: str = "never"
    profile: str = ""

    def run_stage(self, session_id: str, stage: str) -> StageRunRecord:
        session = self.state_store.load_session(session_id)
        contract = build_stage_contract(
            repo_root=self.repo_root,
            state_store=self.state_store,
            session_id=session_id,
            stage=stage,
        )
        run = self.state_store.create_stage_run(
            session_id=session_id,
            stage=stage,
            contract_id=contract.contract_id,
            required_outputs=list(contract.required_outputs),
            required_evidence=list(contract.evidence_requirements),
            worker="codex-exec",
        )
        context = build_stage_execution_context(
            repo_root=self.repo_root,
            state_store=self.state_store,
            session_id=session_id,
            stage=stage,
            contract=contract,
        )
        context_path = self.state_store.save_execution_context(context)
        summary = self.state_store.load_workflow_summary(session_id)
        summary.artifact_paths["execution_context"] = str(context_path)
        self.state_store.save_workflow_summary(session, summary)

        confirmed_alignment = load_confirmed_alignment(session.session_dir)
        confirmed_payload = confirmed_alignment.to_dict() if confirmed_alignment is not None else {}
        codex_dir = session.session_dir / "codex_exec"
        codex_dir.mkdir(parents=True, exist_ok=True)
        output_path = codex_dir / f"{stage.lower()}_last_message.json"
        prompt_path = codex_dir / f"{stage.lower()}_prompt.md"
        prompt = stage_prompt(
            stage=stage,
            execution_context=context.to_dict(),
            contract=contract,
            confirmed_alignment=confirmed_payload,
        )
        prompt_path.write_text(prompt)
        result = self.codex_runner.run(
            CodexExecConfig(
                repo_root=self.repo_root,
                codex_bin=self.codex_bin,
                output_last_message=output_path,
                model=self.model,
                sandbox=self.sandbox,
                approval=self.approval,
                profile=self.profile,
            ),
            prompt,
        )
        (codex_dir / f"{stage.lower()}_stdout.jsonl").write_text(result.stdout)
        (codex_dir / f"{stage.lower()}_stderr.txt").write_text(result.stderr)
        if not result.success:
            raise RuntimeError(f"codex exec failed for {stage}: {result.stderr}")

        payload = json.loads(result.last_message)
        payload["session_id"] = session_id
        payload["stage"] = stage
        payload["contract_id"] = contract.contract_id
        envelope = StageResultEnvelope.from_dict(payload)
        bundle_path = codex_dir / f"{stage.lower()}_bundle.json"
        bundle_path.write_text(json.dumps(envelope.to_dict(), ensure_ascii=False, indent=2))
        submitted = self.state_store.submit_stage_run_result(run.run_id, envelope)

        from .cli import _evaluate_stage_result_for_verification
        from argparse import Namespace
        from .stage_machine import StageMachine

        verify_args = Namespace(
            repo_root=self.repo_root,
            state_root=self.state_store.root,
            session_id=session_id,
            judge="off",
            model="",
            docker_image="",
            openai_api_key="",
            openai_base_url="",
            openai_proxy_url="",
            openai_user_agent="Agent Team-Runtime/0.1",
            openai_oa="",
            acceptance_matrix=None,
        )
        current_summary = self.state_store.load_workflow_summary(session_id)
        verifying_run = self.state_store.update_stage_run(submitted, state="VERIFYING")
        gate_result, normalized_result, _ = _evaluate_stage_result_for_verification(
            args=verify_args,
            store=self.state_store,
            summary=current_summary,
            contract=contract,
            result=envelope,
        )
        if gate_result.status != "PASSED":
            self.state_store.update_stage_run(
                verifying_run,
                state=gate_result.status,
                gate_result=gate_result,
                blocked_reason=gate_result.reason,
            )
            raise RuntimeError(f"{stage} gate failed: {gate_result.reason}")

        stage_record = self.state_store.record_stage_result(session_id, normalized_result)
        updated_summary = StageMachine().advance(summary=current_summary, stage_result=normalized_result)
        updated_summary.artifact_paths[normalized_result.stage.lower()] = str(stage_record.artifact_path)
        updated_summary.artifact_paths.update(stage_record.supplemental_artifact_paths)
        self.state_store.save_workflow_summary(session, updated_summary)
        passed_run = self.state_store.update_stage_run(
            verifying_run,
            state="PASSED",
            gate_result=gate_result,
            blocked_reason="",
            artifact_paths={
                normalized_result.stage.lower(): str(stage_record.artifact_path),
                **stage_record.supplemental_artifact_paths,
            },
        )
        for finding in normalized_result.findings:
            self.state_store.apply_learning(finding)
        return passed_run
```

- [ ] **Step 4: Run stage harness tests**

Run:

```bash
python3 -m unittest tests.test_stage_harness
```

Expected: OK.

- [ ] **Step 5: Commit stage harness**

```bash
git add agent_team/stage_harness.py tests/test_stage_harness.py
git commit -m "Add stage execution harness"
```

## Task 4: Interactive Flow Controller

**Files:**
- Create: `agent_team/interactive.py`
- Create: `tests/test_run_interactive.py`

- [ ] **Step 1: Write failing tests for choices and Product auto-approval**

Create `tests/test_run_interactive.py` with:

```python
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_team.alignment import AlignmentCriterion, AlignmentDraft
from agent_team.interactive import InteractiveConfig, InteractivePrompter, RunInteractiveController


class FakePrompter(InteractivePrompter):
    def __init__(self, answers):
        self.answers = list(answers)
        self.messages = []

    def ask(self, message: str) -> str:
        self.messages.append(message)
        return self.answers.pop(0)

    def show(self, message: str) -> None:
        self.messages.append(message)


class FakeAlignmentRunner:
    def align(self, raw_request, previous_alignment="", user_revision=""):
        return AlignmentDraft(
            requirement_understanding=["Do the thing"],
            scope={"in_scope": ["Thing"], "out_of_scope": []},
            acceptance_criteria=[
                AlignmentCriterion("AC1", "Thing is done", "Inspect output")
            ],
            clarifying_questions=[],
        )


class FakeStageHarness:
    def __init__(self) -> None:
        self.stages = []

    def run_stage(self, session_id: str, stage: str):
        self.stages.append(stage)
        return None


class RunInteractiveTests(unittest.TestCase):
    def test_confirmed_alignment_starts_session_and_runs_product(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir) / "state")
            stage_harness = FakeStageHarness()
            controller = RunInteractiveController(
                config=InteractiveConfig(repo_root=Path(temp_dir), state_store=store),
                prompter=FakePrompter(["A real requirement", "y"]),
                alignment_runner=FakeAlignmentRunner(),
                stage_harness=stage_harness,
            )

            session_id = controller.run()

        self.assertTrue(session_id)
        self.assertEqual(stage_harness.stages, ["Product"])

    def test_edit_reruns_alignment_before_confirmation(self) -> None:
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir) / "state")
            prompter = FakePrompter(["Requirement", "e", "Add detail", "y"])
            controller = RunInteractiveController(
                config=InteractiveConfig(repo_root=Path(temp_dir), state_store=store),
                prompter=prompter,
                alignment_runner=FakeAlignmentRunner(),
                stage_harness=FakeStageHarness(),
            )

            session_id = controller.run()

        self.assertTrue(session_id)
        self.assertIn("Add detail", "\n".join(prompter.messages))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run interactive tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_run_interactive
```

Expected: FAIL because `agent_team.interactive` does not exist.

- [ ] **Step 3: Implement interactive controller**

Create `agent_team/interactive.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .alignment import (
    AlignmentDraft,
    alignment_prompt,
    acceptance_criteria_strings,
    confirmed_request_text,
    parse_alignment_json,
    render_alignment_for_terminal,
    save_confirmed_alignment,
)
from .codex_exec import CodexExecConfig, CodexExecRunner
from .models import AcceptanceContract
from .stage_harness import StageHarness
from .state import StateStore
from .stage_machine import StageMachine


class InteractivePrompter:
    def ask(self, message: str) -> str:
        return input(message)

    def show(self, message: str) -> None:
        print(message)


class AlignmentRunner(Protocol):
    def align(self, raw_request: str, previous_alignment: str = "", user_revision: str = "") -> AlignmentDraft:
        ...


@dataclass(slots=True)
class CodexAlignmentRunner:
    repo_root: Path
    codex_runner: CodexExecRunner
    codex_bin: str = "codex"
    model: str = ""
    sandbox: str = "workspace-write"
    approval: str = "never"
    profile: str = ""

    def align(self, raw_request: str, previous_alignment: str = "", user_revision: str = "") -> AlignmentDraft:
        output_dir = self.repo_root / ".agent-team" / "_interactive"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "alignment_last_message.json"
        prompt = alignment_prompt(
            raw_request=raw_request,
            previous_alignment=previous_alignment,
            user_revision=user_revision,
        )
        (output_dir / "alignment_prompt.md").write_text(prompt)
        result = self.codex_runner.run(
            CodexExecConfig(
                repo_root=self.repo_root,
                codex_bin=self.codex_bin,
                output_last_message=output_path,
                model=self.model,
                sandbox=self.sandbox,
                approval=self.approval,
                profile=self.profile,
            ),
            prompt,
        )
        (output_dir / "alignment_stdout.jsonl").write_text(result.stdout)
        (output_dir / "alignment_stderr.txt").write_text(result.stderr)
        if not result.success:
            raise RuntimeError(f"codex exec alignment failed: {result.stderr}")
        return parse_alignment_json(result.last_message)


@dataclass(slots=True)
class InteractiveConfig:
    repo_root: Path
    state_store: StateStore
    message: str = ""
    session_id: str = ""


@dataclass(slots=True)
class RunInteractiveController:
    config: InteractiveConfig
    prompter: InteractivePrompter
    alignment_runner: AlignmentRunner
    stage_harness: StageHarness

    def run(self) -> str:
        raw_request = self.config.message or self.prompter.ask("What requirement should Agent Team run?\n> ")
        draft = self._confirm_alignment(raw_request)
        confirmed_request = confirmed_request_text(raw_request, draft)
        contract = AcceptanceContract(acceptance_criteria=acceptance_criteria_strings(draft))
        session = self.config.state_store.create_session(
            confirmed_request,
            raw_message=raw_request,
            contract=contract,
            runtime_mode="interactive_harness",
        )
        save_confirmed_alignment(session.session_dir, draft)
        self.prompter.show(f"session_id: {session.session_id}")
        self.stage_harness.run_stage(session.session_id, "Product")
        self._auto_approve_product_if_waiting(session.session_id)
        return session.session_id

    def _confirm_alignment(self, raw_request: str) -> AlignmentDraft:
        previous = ""
        revision = ""
        while True:
            draft = self.alignment_runner.align(raw_request, previous, revision)
            rendered = render_alignment_for_terminal(draft)
            self.prompter.show(rendered)
            choice = self.prompter.ask("\nChoose [y] confirm and continue, [e] edit, [q] quit:\n> ").strip().lower()
            if choice == "y":
                return draft
            if choice == "e":
                previous = rendered
                revision = self.prompter.ask("Add or revise details:\n> ")
                self.prompter.show(revision)
                continue
            if choice == "q":
                raise SystemExit("Interactive run cancelled.")
            self.prompter.show("Please choose y, e, or q.")

    def _auto_approve_product_if_waiting(self, session_id: str) -> None:
        session = self.config.state_store.load_session(session_id)
        summary = self.config.state_store.load_workflow_summary(session_id)
        if summary.current_state != "WaitForCEOApproval":
            return
        updated = StageMachine().apply_human_decision(summary=summary, decision="go")
        self.config.state_store.save_workflow_summary(session, updated)
        self.config.state_store.set_human_decision(session_id, updated.human_decision)
```

- [ ] **Step 4: Run interactive controller tests**

Run:

```bash
python3 -m unittest tests.test_run_interactive
```

Expected: OK.

- [ ] **Step 5: Commit controller**

```bash
git add agent_team/interactive.py tests/test_run_interactive.py
git commit -m "Add interactive workflow controller"
```

## Task 5: CLI Command Registration

**Files:**
- Modify: `agent_team/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI help test**

Add this test to `tests/test_cli.py` near other CLI help tests:

```python
    def test_cli_help_lists_run_interactive(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("run-interactive", result.stdout)

    def test_run_interactive_help_exits_successfully(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "run-interactive", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("--message", result.stdout)
        self.assertIn("--session-id", result.stdout)
        self.assertIn("--codex-bin", result.stdout)
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_cli.CliTests.test_cli_help_lists_run_interactive tests.test_cli.CliTests.test_run_interactive_help_exits_successfully
```

Expected: FAIL because command is not registered.

- [ ] **Step 3: Register `run-interactive` parser and handler**

Modify `agent_team/cli.py` imports:

```python
from .codex_exec import CodexExecRunner
from .interactive import CodexAlignmentRunner, InteractiveConfig, InteractivePrompter, RunInteractiveController
from .stage_harness import StageHarness
```

Add parser after `start-session`:

```python
    run_interactive_parser = subparsers.add_parser(
        "run-interactive",
        help="Run the real Agent Team workflow through an interactive terminal harness backed by codex exec.",
    )
    run_interactive_parser.add_argument("--message", help="Initial requirement message. If omitted, prompt in terminal.")
    run_interactive_parser.add_argument("--session-id", help="Existing workflow session to resume.")
    run_interactive_parser.add_argument("--dry-run", action="store_true", help="Print planned actions without executing stages.")
    run_interactive_parser.add_argument("--codex-bin", default="codex", help="Path to the codex executable.")
    run_interactive_parser.add_argument("--model", default="", help="Optional Codex model override.")
    run_interactive_parser.add_argument("--sandbox", default="workspace-write", help="Codex sandbox mode.")
    run_interactive_parser.add_argument("--approval", default="never", help="Codex approval policy.")
    run_interactive_parser.add_argument("--profile", default="", help="Optional Codex config profile.")
    run_interactive_parser.set_defaults(handler=_handle_run_interactive)
```

Add handler near `_handle_start_session`:

```python
def _handle_run_interactive(args: argparse.Namespace) -> int:
    if args.dry_run:
        print("run-interactive dry run")
        print(f"repo_root: {args.repo_root}")
        print(f"codex_bin: {args.codex_bin}")
        return 0

    store = StateStore(args.state_root)
    runner = CodexExecRunner()
    alignment_runner = CodexAlignmentRunner(
        repo_root=args.repo_root,
        codex_runner=runner,
        codex_bin=args.codex_bin,
        model=args.model,
        sandbox=args.sandbox,
        approval=args.approval,
        profile=args.profile,
    )
    stage_harness = StageHarness(
        repo_root=args.repo_root,
        state_store=store,
        codex_runner=runner,
        codex_bin=args.codex_bin,
        model=args.model,
        sandbox=args.sandbox,
        approval=args.approval,
        profile=args.profile,
    )
    controller = RunInteractiveController(
        config=InteractiveConfig(
            repo_root=args.repo_root,
            state_store=store,
            message=args.message or "",
            session_id=args.session_id or "",
        ),
        prompter=InteractivePrompter(),
        alignment_runner=alignment_runner,
        stage_harness=stage_harness,
    )
    session_id = controller.run()
    print(f"session_id: {session_id}")
    print(f"panel: agent-team panel --session-id {session_id}")
    return 0
```

- [ ] **Step 4: Run CLI help tests**

Run:

```bash
python3 -m unittest tests.test_cli.CliTests.test_cli_help_lists_run_interactive tests.test_cli.CliTests.test_run_interactive_help_exits_successfully
```

Expected: OK.

- [ ] **Step 5: Commit CLI registration**

```bash
git add agent_team/cli.py tests/test_cli.py
git commit -m "Register run-interactive CLI command"
```

## Task 6: End-to-End Fake Codex Integration

**Files:**
- Modify: `tests/test_run_interactive.py`

- [ ] **Step 1: Add fake-codex integration test**

Append to `tests/test_run_interactive.py`:

```python
    def test_run_interactive_with_fake_codex_reaches_post_product_dev_state(self) -> None:
        import os
        import stat
        import subprocess
        import sys

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_codex = temp_path / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "args = sys.argv\n"
                "out = args[args.index('--output-last-message') + 1]\n"
                "prompt = args[-1]\n"
                "if 'Intake/Product alignment role' in prompt:\n"
                "    payload = {\n"
                "      'requirement_understanding': ['Do the fake feature'],\n"
                "      'scope': {'in_scope': ['Fake feature'], 'out_of_scope': []},\n"
                "      'acceptance_criteria': [{'id': 'AC1', 'criterion': 'Fake feature is specified', 'verification': 'Inspect PRD'}],\n"
                "      'clarifying_questions': []\n"
                "    }\n"
                "else:\n"
                "    payload = {\n"
                "      'session_id': 'model-output-session-id',\n"
                "      'contract_id': 'model-output-contract-id',\n"
                "      'stage': 'Product',\n"
                "      'status': 'completed',\n"
                "      'artifact_name': 'prd.md',\n"
                "      'artifact_content': '# Product PRD\\\\n\\\\n## Acceptance Criteria\\\\n- Fake feature is specified\\\\n',\n"
                "      'journal': '# Product Journal\\\\n',\n"
                "      'findings': [],\n"
                "      'evidence': [{'name': 'explicit_acceptance_criteria', 'kind': 'report', 'summary': 'Criteria documented.'}],\n"
                "      'summary': 'Drafted PRD'\n"
                "    }\n"
                "open(out, 'w').write(json.dumps(payload))\n"
                "print(json.dumps({'event': 'done'}))\n"
            )
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IEXEC)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(temp_path),
                    "--state-root",
                    str(temp_path / "state"),
                    "run-interactive",
                    "--message",
                    "执行这个需求：Do the fake feature",
                    "--codex-bin",
                    str(fake_codex),
                ],
                input="y\n",
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("session_id:", result.stdout)
            status = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_team",
                    "--repo-root",
                    str(temp_path),
                    "--state-root",
                    str(temp_path / "state"),
                    "status",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(status.returncode, 0)
            self.assertIn("role: Dev", status.stdout)
            self.assertIn("status: in_progress", status.stdout)
```

- [ ] **Step 2: Run fake-codex integration test**

Run:

```bash
python3 -m unittest tests.test_run_interactive.RunInteractiveTests.test_run_interactive_with_fake_codex_reaches_post_product_dev_state
```

Expected: OK.

- [ ] **Step 3: Commit integration test**

```bash
git add tests/test_run_interactive.py
git commit -m "Cover run-interactive fake Codex flow"
```

## Task 7: Skill and Usage Documentation

**Files:**
- Modify: `agent_team/project_scaffold.py`
- Modify: `agent_team/assets/codex_skill/agent-team-workflow/SKILL.md`
- Modify: `codex-skill/agent-team-workflow/SKILL.md`
- Modify: `tests/test_skill_package.py`
- Modify: `tests/test_docs.py`

- [ ] **Step 1: Write failing docs/package tests**

Add assertions:

In `tests/test_skill_package.py`, inside `test_codex_init_generates_project_local_agents_and_run_skill`, add:

```python
            run_skill = (project_root / ".agents" / "skills" / "agent-team-run" / "SKILL.md").read_text()
            self.assertIn("agent-team run-interactive", run_skill)
            self.assertIn("terminal workflows", run_skill)
```

In `tests/test_docs.py`, add:

```python
    def test_usage_docs_mention_run_interactive(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        readme = (repo_root / "README.md").read_text()
        self.assertIn("agent-team run-interactive", readme)
```

- [ ] **Step 2: Run docs tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_skill_package.SkillPackageTests.test_codex_init_generates_project_local_agents_and_run_skill tests.test_docs
```

Expected: FAIL because docs do not mention `run-interactive`.

- [ ] **Step 3: Update generated run skill and packaged skill docs**

In `agent_team/project_scaffold.py`, update `_run_skill()` `Available assets` or `Workflow Contract` section with:

```markdown
- `agent-team run-interactive`: recommended terminal harness for real project workflows; it asks for the requirement, confirms acceptance criteria, then uses `codex exec` to drive stages through runtime gates.
```

In both skill files, add a terminal usage section:

````markdown
## Terminal Usage

For terminal-first workflows, prefer:

```bash
agent-team run-interactive
```

This asks for the requirement, confirms acceptance criteria once, then drives Product, Dev, QA, and Acceptance through `codex exec` while preserving Agent Team runtime gates.
````

In `README.md`, add a short usage example near existing CLI usage:

````markdown
### Interactive terminal workflow

```bash
cd /path/to/project
agent-team run-interactive
```

The command prompts for the requirement, confirms acceptance criteria, then uses `codex exec` to run Agent Team stages through the normal runtime gates.
````

- [ ] **Step 4: Run docs/package tests**

Run:

```bash
python3 -m unittest tests.test_skill_package.SkillPackageTests.test_codex_init_generates_project_local_agents_and_run_skill tests.test_docs
```

Expected: OK.

- [ ] **Step 5: Commit docs update**

```bash
git add agent_team/project_scaffold.py agent_team/assets/codex_skill/agent-team-workflow/SKILL.md codex-skill/agent-team-workflow/SKILL.md README.md tests/test_skill_package.py tests/test_docs.py
git commit -m "Document run-interactive terminal workflow"
```

## Task 8: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
python3 -m unittest \
  tests.test_alignment \
  tests.test_codex_exec \
  tests.test_stage_harness \
  tests.test_run_interactive \
  tests.test_cli \
  tests.test_skill_package \
  tests.test_docs
```

Expected: all tests pass.

- [ ] **Step 2: Run full test suite**

Run:

```bash
python3 -m unittest
```

Expected: all tests pass. If optional OpenAI sandbox tests skip or report Docker unavailability according to existing expectations, keep the existing behavior and record the exact output.

- [ ] **Step 3: Manual dry-run smoke**

Run:

```bash
python3 -m agent_team --repo-root . run-interactive --dry-run
```

Expected output includes:

```text
run-interactive dry run
repo_root:
codex_bin:
```

- [ ] **Step 4: Review git diff**

Run:

```bash
git diff --stat HEAD
git status --short
```

Expected: no unstaged implementation files after commits; unrelated pre-existing untracked files may remain untouched.
