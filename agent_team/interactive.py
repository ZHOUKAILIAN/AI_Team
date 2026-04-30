from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .alignment import (
    AlignmentDraft,
    acceptance_criteria_strings,
    alignment_prompt,
    confirmed_request_text,
    parse_alignment_json,
    render_alignment_for_terminal,
    save_confirmed_alignment,
)
from .codex_exec import CodexExecConfig, CodexExecRunner
from .executor import StageExecutor
from .models import AcceptanceContract
from .skill_registry import STAGES, SkillRegistry
from .stage_harness import StageHarness
from .stage_machine import StageMachine
from .state import StateStore
from .tech_plan import (
    TechPlanDraft,
    parse_tech_plan_json,
    render_tech_plan_for_terminal,
    save_confirmed_tech_plan,
    tech_plan_prompt,
)


class InteractivePrompter:
    def ask(self, message: str) -> str:
        return input(message)

    def show(self, message: str) -> None:
        print(message)

    def wait_key(self, message: str) -> str:
        return self.ask(message)

    def multiselect(self, message: str, options: list[dict[str, str]], initial_values: list[str] | None = None) -> list[str]:
        self.show(message)
        selected = set(initial_values or [])
        for index, option in enumerate(options, start=1):
            marker = "x" if option["value"] in selected else " "
            self.show(f"[{marker}] {index}. {option['label']}")
        raw = self.ask("Select numbers or names separated by commas. Empty = none.\n> ").strip()
        if not raw:
            return []
        chosen: list[str] = []
        by_name = {option["value"]: option["value"] for option in options}
        for part in [item.strip() for item in raw.split(",") if item.strip()]:
            if part.isdigit() and 1 <= int(part) <= len(options):
                chosen.append(options[int(part) - 1]["value"])
            elif part in by_name:
                chosen.append(by_name[part])
        return chosen


class AlignmentRunner(Protocol):
    def align(self, raw_request: str, previous_alignment: str = "", user_revision: str = "") -> AlignmentDraft:
        ...


class TechPlanRunner(Protocol):
    def plan(
        self,
        alignment: AlignmentDraft,
        repo_structure: str,
        previous_plan: str = "",
        user_revision: str = "",
    ) -> TechPlanDraft:
        ...


@dataclass(slots=True)
class ExecutorAlignmentRunner:
    repo_root: Path
    executor: StageExecutor

    def align(self, raw_request: str, previous_alignment: str = "", user_revision: str = "") -> AlignmentDraft:
        output_dir = self.repo_root / ".agent-team" / "_interactive"
        prompt = alignment_prompt(
            raw_request=raw_request,
            previous_alignment=previous_alignment,
            user_revision=user_revision,
        )
        result = self.executor.execute(prompt=prompt, output_dir=output_dir, stage="alignment")
        (output_dir / "alignment_stdout.jsonl").write_text(result.stdout)
        (output_dir / "alignment_stderr.txt").write_text(result.stderr)
        if not result.success:
            raise RuntimeError(f"executor alignment failed: {result.stderr}")
        return parse_alignment_json(result.last_message)


@dataclass(slots=True)
class ExecutorTechPlanRunner:
    repo_root: Path
    executor: StageExecutor

    def plan(
        self,
        alignment: AlignmentDraft,
        repo_structure: str,
        previous_plan: str = "",
        user_revision: str = "",
    ) -> TechPlanDraft:
        output_dir = self.repo_root / ".agent-team" / "_interactive"
        prompt = tech_plan_prompt(
            repo_root=self.repo_root,
            confirmed_alignment=alignment,
            repo_structure=repo_structure,
            previous_plan=previous_plan,
            user_revision=user_revision,
        )
        result = self.executor.execute(prompt=prompt, output_dir=output_dir, stage="technical_plan")
        (output_dir / "technical_plan_stdout.jsonl").write_text(result.stdout)
        (output_dir / "technical_plan_stderr.txt").write_text(result.stderr)
        if not result.success:
            raise RuntimeError(f"executor technical plan failed: {result.stderr}")
        return parse_tech_plan_json(result.last_message)


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
class CodexTechPlanRunner:
    repo_root: Path
    codex_runner: CodexExecRunner
    codex_bin: str = "codex"
    model: str = ""
    sandbox: str = "workspace-write"
    approval: str = "never"
    profile: str = ""

    def plan(
        self,
        alignment: AlignmentDraft,
        repo_structure: str,
        previous_plan: str = "",
        user_revision: str = "",
    ) -> TechPlanDraft:
        output_dir = self.repo_root / ".agent-team" / "_interactive"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "technical_plan_last_message.json"
        prompt = tech_plan_prompt(
            repo_root=self.repo_root,
            confirmed_alignment=alignment,
            repo_structure=repo_structure,
            previous_plan=previous_plan,
            user_revision=user_revision,
        )
        (output_dir / "technical_plan_prompt.md").write_text(prompt)
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
        (output_dir / "technical_plan_stdout.jsonl").write_text(result.stdout)
        (output_dir / "technical_plan_stderr.txt").write_text(result.stderr)
        if not result.success:
            raise RuntimeError(f"codex exec technical plan failed: {result.stderr}")
        return parse_tech_plan_json(result.last_message)


@dataclass(slots=True)
class DevControllerConfig:
    repo_root: Path
    state_store: StateStore
    message: str = ""
    session_id: str = ""


@dataclass(slots=True)
class DevController:
    config: DevControllerConfig
    prompter: InteractivePrompter
    alignment_runner: AlignmentRunner
    tech_plan_runner: TechPlanRunner
    stage_harness: StageHarness
    skill_registry: SkillRegistry | None = None
    skill_overrides: dict[str, list[str]] = field(default_factory=dict)
    skills_empty: bool = False

    def run(self) -> str:
        raw_request = self.config.message or self.prompter.ask("What requirement should Agent Team run?\n> ")
        alignment = self._confirm_alignment(raw_request)
        repo_structure = self._capture_repo_structure()
        tech_plan = self._confirm_tech_plan(alignment, repo_structure)
        self._configure_skills(tech_plan)
        session = self.config.state_store.create_session(
            confirmed_request_text(raw_request, alignment),
            raw_message=raw_request,
            contract=AcceptanceContract(acceptance_criteria=acceptance_criteria_strings(alignment)),
            runtime_mode="interactive_harness",
            initiator="human",
        )
        save_confirmed_alignment(session.session_dir, alignment)
        save_confirmed_tech_plan(session.session_dir, tech_plan)
        self.prompter.show(f"session_id: {session.session_id}")

        choice = self._ask_agent_decision(tech_plan)
        if choice == "q":
            self.prompter.show(f"Session saved. Resume with --session-id {session.session_id}.")
            return session.session_id
        if choice == "m":
            self._print_manual_instructions(session.session_id)
            return session.session_id

        self._run_agent_chain(session.session_id)
        return session.session_id

    def _confirm_alignment(self, raw_request: str) -> AlignmentDraft:
        previous = ""
        revision = ""
        while True:
            draft = self.alignment_runner.align(raw_request, previous, revision)
            rendered = render_alignment_for_terminal(draft)
            self.prompter.show(rendered)
            choice = self.prompter.ask("\nConfirm requirement and acceptance criteria? [y] confirm [e] edit [q] quit\n> ").strip().lower()
            if choice == "y":
                return draft
            if choice == "e":
                previous = rendered
                revision = self.prompter.ask("Add or revise requirement details:\n> ")
                self.prompter.show(revision)
                continue
            if choice == "q":
                raise SystemExit("Interactive dev run cancelled.")
            self.prompter.show("Please choose y, e, or q.")

    def _confirm_tech_plan(self, alignment: AlignmentDraft, repo_structure: str) -> TechPlanDraft:
        previous = ""
        revision = ""
        while True:
            draft = self.tech_plan_runner.plan(alignment, repo_structure, previous, revision)
            rendered = render_tech_plan_for_terminal(draft)
            self.prompter.show(rendered)
            choice = self.prompter.ask("\nConfirm technical plan? [y] confirm [e] edit [q] quit\n> ").strip().lower()
            if choice == "y":
                return draft
            if choice == "e":
                previous = rendered
                revision = self.prompter.ask("Add or revise technical plan details:\n> ")
                self.prompter.show(revision)
                continue
            if choice == "q":
                raise SystemExit("Interactive dev run cancelled.")
            self.prompter.show("Please choose y, e, or q.")

    def _ask_agent_decision(self, tech_plan: TechPlanDraft) -> str:
        self.prompter.show("\nTechnical plan confirmed.")
        self.prompter.show(f"Affected modules: {len(tech_plan.affected_modules)}")
        self.prompter.show(f"Implementation steps: {len(tech_plan.implementation_steps)}")
        while True:
            choice = self.prompter.ask(
                "\nDelegate to agents?\n"
                "[y] Start Product/Dev/QA/Acceptance agent chain\n"
                "[m] Manual execution; keep the session for manual stage submission\n"
                "[q] Quit and keep the session\n> "
            ).strip().lower()
            if choice in {"y", "m", "q"}:
                return choice
            self.prompter.show("Please choose y, m, or q.")

    def _configure_skills(self, tech_plan: TechPlanDraft) -> None:
        if self.skill_registry is None:
            return
        if self.skills_empty:
            self.stage_harness.enabled_skills_by_stage = {}
            return
        if self.skill_overrides:
            self.stage_harness.enabled_skills_by_stage = self.skill_registry.resolve_enabled(self.skill_overrides)
            return
        selected = self._select_skills(tech_plan)
        self.stage_harness.enabled_skills_by_stage = self.skill_registry.resolve_enabled(selected)

    def _select_skills(self, tech_plan: TechPlanDraft) -> dict[str, list[str]]:
        assert self.skill_registry is not None
        prefs = self.skill_registry.load_preferences()
        selected_by_stage: dict[str, list[str]] = {}
        self.prompter.show("\nTechnical plan confirmed.")
        self.prompter.show(f"Affected modules: {len(tech_plan.affected_modules)}")
        self.prompter.show(f"Implementation steps: {len(tech_plan.implementation_steps)}")
        for stage in STAGES:
            available = self.skill_registry.list_skills(stage=stage)
            if not available:
                selected_by_stage[stage] = []
                continue
            if prefs.is_first_time:
                chosen = self.prompter.multiselect(
                    f"\n{stage} stage available skills:",
                    [
                        {
                            "value": skill.name,
                            "label": f"{skill.name} ({skill.source}) {skill.description}",
                        }
                        for skill in available
                    ],
                    initial_values=[],
                )
            else:
                choice = self.prompter.wait_key(
                    f"\nSkills [{stage}]: {prefs.format_last(stage)}  "
                    "press [s] to modify or [Enter] to continue\n> "
                ).strip().lower()
                if choice == "s":
                    chosen = self.prompter.multiselect(
                        f"\n{stage} stage available skills:",
                        [
                            {
                                "value": skill.name,
                                "label": f"{skill.name} ({skill.source}) {skill.description}",
                            }
                            for skill in available
                        ],
                        initial_values=prefs.selected_for(stage),
                    )
                else:
                    chosen = prefs.selected_for(stage)
            self.skill_registry.record(stage, chosen)
            selected_by_stage[stage] = chosen
        return selected_by_stage

    def _run_agent_chain(self, session_id: str) -> None:
        self.stage_harness.run_stage(session_id, "Product")
        self._auto_approve_product_if_waiting(session_id)
        self.stage_harness.run_stage(session_id, "Dev")
        self.stage_harness.run_stage(session_id, "QA")
        self.stage_harness.run_stage(session_id, "Acceptance")
        self.prompter.show(f"Workflow is waiting for final human decision. session_id: {session_id}")

    def _auto_approve_product_if_waiting(self, session_id: str) -> None:
        session = self.config.state_store.load_session(session_id)
        summary = self.config.state_store.load_workflow_summary(session_id)
        if summary.current_state != "WaitForCEOApproval":
            return
        updated = StageMachine().apply_human_decision(summary=summary, decision="go")
        self.config.state_store.save_workflow_summary(session, updated)
        self.config.state_store.set_human_decision(session_id, updated.human_decision)

    def _print_manual_instructions(self, session_id: str) -> None:
        self.prompter.show("Manual execution selected.")
        self.prompter.show(f"Session saved. Resume with: agent-team step --session-id {session_id}")

    def _capture_repo_structure(self) -> str:
        paths: list[str] = []
        excluded = {
            ".agent-team",
            ".git",
            ".mypy_cache",
            ".nox",
            ".pytest_cache",
            ".ruff_cache",
            ".tox",
            ".venv",
            ".worktrees",
            "__pycache__",
            "__pypackages__",
            "build",
            "dist",
            "env",
            "node_modules",
            "site-packages",
            "venv",
        }
        for path in sorted(self.config.repo_root.rglob("*")):
            if len(paths) >= 200:
                break
            relative = path.relative_to(self.config.repo_root)
            if any(part in excluded for part in relative.parts):
                continue
            if path.is_file():
                paths.append(str(relative))
        return "\n".join(paths)
