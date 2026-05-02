from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .alignment import load_confirmed_alignment
from .executor import StageExecutor
from .execution_context import build_stage_execution_context
from .gatekeeper import evaluate_candidate
from .models import StageContract, StageResultEnvelope, StageRunRecord
from .skill_registry import Skill, skill_injection_text
from .stage_contracts import build_stage_contract
from .stage_machine import StageMachine
from .state import StateStore
from .tech_plan import load_confirmed_tech_plan


@dataclass(frozen=True, slots=True)
class DevArtifacts:
    implementation_md: str = ""
    changed_files: str = ""


def stage_prompt(
    *,
    stage: str,
    execution_context: dict[str, Any],
    contract: StageContract,
    confirmed_alignment: dict[str, Any] | None = None,
    tech_plan: dict[str, Any] | None = None,
    prd_content: str = "",
    dev_implementation_md: str = "",
    dev_changed_files: str = "",
    qa_report_content: str = "",
    raw_request: str = "",
    skills: list[Skill] | None = None,
) -> str:
    return build_agent_prompt(
        stage=stage,
        execution_context=execution_context,
        contract=contract,
        alignment=confirmed_alignment or {},
        tech_plan=tech_plan or {},
        prd_content=prd_content,
        dev_artifacts=DevArtifacts(implementation_md=dev_implementation_md, changed_files=dev_changed_files),
        qa_report=qa_report_content,
        raw_request=raw_request,
        skills=skills or [],
    )


def build_agent_prompt(
    *,
    stage: str,
    execution_context: dict[str, Any],
    contract: StageContract,
    alignment: dict[str, Any],
    tech_plan: dict[str, Any],
    prd_content: str,
    dev_artifacts: DevArtifacts,
    qa_report: str,
    raw_request: str,
    skills: list[Skill] | None = None,
) -> str:
    layers = [
        _universal_protection_layer(),
        _role_instruction_layer(stage),
        _skill_injection_layer(skills or []),
        _stage_context_layer(
            stage=stage,
            execution_context=execution_context,
            contract=contract,
            alignment=alignment,
            tech_plan=tech_plan,
            prd_content=prd_content,
            dev_artifacts=dev_artifacts,
            qa_report=qa_report,
            raw_request=raw_request,
        ),
    ]
    return "\n\n".join(layer for layer in layers if layer.strip())


@dataclass(slots=True)
class StageHarness:
    repo_root: Path
    state_store: StateStore
    executor: StageExecutor
    stage_executors: dict[str, StageExecutor] = field(default_factory=dict)
    enabled_skills_by_stage: dict[str, list[Skill]] = field(default_factory=dict)

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
            worker=self._executor_for_stage(stage).__class__.__name__,
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

        exec_dir = session.session_dir / "exec"
        exec_dir.mkdir(parents=True, exist_ok=True)
        stage_skills = self.enabled_skills_by_stage.get(stage, [])
        _install_sandbox_skills(stage_skills, exec_dir)
        prompt = stage_prompt(
            stage=stage,
            execution_context=context.to_dict(),
            contract=contract,
            confirmed_alignment=_alignment_payload(session.session_dir),
            tech_plan=_tech_plan_payload(session.session_dir),
            prd_content=_read_artifact(summary.artifact_paths, "product"),
            dev_implementation_md=_read_artifact(summary.artifact_paths, "dev"),
            dev_changed_files=_changed_files_snapshot(self.repo_root),
            qa_report_content=_read_artifact(summary.artifact_paths, "qa"),
            raw_request=session.request,
            skills=stage_skills,
        )
        result = self._executor_for_stage(stage).execute(
            prompt=prompt,
            output_dir=exec_dir,
            stage=stage,
        )
        (exec_dir / f"{stage.lower()}_stdout.jsonl").write_text(result.stdout)
        (exec_dir / f"{stage.lower()}_stderr.txt").write_text(result.stderr)
        if not result.success:
            raise RuntimeError(f"executor failed for {stage}: {result.stderr}")

        envelope = _envelope_from_model_output(
            raw=result.last_message,
            session_id=session_id,
            stage=stage,
            contract_id=contract.contract_id,
        )
        bundle_path = exec_dir / f"{stage.lower()}_bundle.json"
        bundle_path.write_text(json.dumps(envelope.to_dict(), ensure_ascii=False, indent=2))

        submitted = self.state_store.submit_stage_run_result(run.run_id, envelope)
        return self._verify_submitted_run(submitted, contract, envelope)

    def _executor_for_stage(self, stage: str) -> StageExecutor:
        return self.stage_executors.get(stage, self.executor)

    def _verify_submitted_run(
        self,
        run: StageRunRecord,
        contract: StageContract,
        envelope: StageResultEnvelope,
    ) -> StageRunRecord:
        verifying_run = self.state_store.update_stage_run(run, state="VERIFYING")
        session = self.state_store.load_session(run.session_id)
        summary = self.state_store.load_workflow_summary(run.session_id)
        gate_result, normalized = evaluate_candidate(
            session=session,
            contract=contract,
            result=envelope,
            acceptance_contract=self.state_store.load_acceptance_contract(run.session_id),
        )
        if gate_result.status != "PASSED":
            self.state_store.update_stage_run(
                verifying_run,
                state=gate_result.status,
                gate_result=gate_result,
                blocked_reason=gate_result.reason,
            )
            raise RuntimeError(f"{run.stage} gate failed: {gate_result.reason}")

        stage_record = self.state_store.record_stage_result(run.session_id, normalized)
        updated_summary = StageMachine().advance(summary=summary, stage_result=normalized)
        updated_summary.artifact_paths[normalized.stage.lower()] = str(stage_record.artifact_path)
        updated_summary.artifact_paths.update(stage_record.supplemental_artifact_paths)
        self.state_store.save_workflow_summary(session, updated_summary)
        passed_run = self.state_store.update_stage_run(
            verifying_run,
            state="PASSED",
            gate_result=gate_result,
            blocked_reason="",
            artifact_paths={
                normalized.stage.lower(): str(stage_record.artifact_path),
                **stage_record.supplemental_artifact_paths,
            },
        )
        for finding in normalized.findings:
            self.state_store.apply_learning(finding)
        return passed_run


def _universal_protection_layer() -> str:
    return """== UNIVERSAL PROTECTION ==

You are a STAGE AGENT in the Agent Team workflow. These rules apply regardless of which stage you are executing.

== SCOPE ==
- Do ONLY what your stage defines. Do NOT add features, refactor unrelated code, or make "improvements" beyond what was asked.
- Do NOT add error handling, fallbacks, or validation for scenarios that cannot happen. Trust internal code and framework guarantees.
- Do NOT create helpers, utilities, or abstractions for one-time operations. Three similar lines are better than a premature abstraction.
- Do NOT create documentation files beyond what the stage contract requires.

== SECURITY ==
- Prioritize writing safe, secure, and correct code.
- Be careful not to introduce security vulnerabilities such as command injection, XSS, SQL injection, path traversal, hardcoded secrets, unsafe deserialization, and other OWASP top 10 vulnerabilities.
- If you notice that you wrote insecure code, immediately fix it.
- Check for missing input validation at system boundaries.

== INTEGRITY ==
- Report outcomes faithfully. If tests fail, say so with the relevant output.
- If you did not run a verification step, say that rather than implying it succeeded.
- Never claim "all tests pass" when output shows failures.
- Never suppress or simplify failing checks to manufacture a green result.
- Never characterize incomplete or broken work as done.

== BOUNDARY ==
- You are a STAGE AGENT. You only have authority over your assigned stage.
- Do NOT attempt to advance the workflow state machine.
- Do NOT call record-human-decision or modify session state.
- Submit your stage result and stop. The runtime handles what comes next.
- Do NOT run destructive git operations such as force push, hard reset, or branch delete unless explicitly required by the stage contract.

== OUTPUT FORMAT ==
- Report back with specific, actionable results.
- Include file paths, commands run, and their actual output.
- Use the StageResultEnvelope JSON format defined in your stage context."""


def _role_instruction_layer(stage: str) -> str:
    if stage == "Product":
        return _product_instruction()
    if stage == "Dev":
        return _dev_instruction()
    if stage == "QA":
        return _qa_instruction()
    if stage == "Acceptance":
        return _acceptance_instruction()
    raise ValueError(f"Unknown stage: {stage}")


def _product_instruction() -> str:
    return """== PRODUCT ROLE ==

You are the Product stage agent for Agent Team. Write a PRD that preserves the human-confirmed requirement and acceptance criteria.

== OUTPUT ==
- Write prd.md with product requirements, user scenarios, and explicit acceptance criteria.
- Preserve the confirmed alignment. Do NOT invent new product scope.
- Evidence must include "explicit_acceptance_criteria"."""


def _dev_instruction() -> str:
    return """== DEV ROLE ==

You are the Dev stage agent for Agent Team. Implement the feature according to the technical plan and acceptance criteria in your stage context.
Don't gold-plate, but don't leave it half-done.

Sandbox: workspace-write. You have full access to the repository.

== SELF CODE REVIEW ==
- Before self-verification, review every changed file for correctness, maintainability, security, and scope.
- Fix issues found during self-review before running final verification.
- Include a self_code_review evidence item summarizing reviewed files, fixes made, and remaining risks.

== SELF-VERIFICATION ==
- Before reporting done, run tests and typecheck.
- Include a self_verification evidence item with the actual command evidence.
- Report the actual command output, not only a summary.

== OUTPUT ==
- Write implementation.md describing what changed and why.
- Include files modified with absolute paths.
- Include a Self Code Review section with reviewed files, issues found or fixed, and residual risks.
- Include commands run and their output.
- Include any limitations or known issues.
- Include commit hashes when available and test run summaries."""


def _qa_instruction() -> str:
    return """== QA ROLE ==

== CRITICAL: CLEAN SANDBOX ==
You are in a CLEAN sandbox. The Dev agent worked in a DIFFERENT sandbox that you cannot access.
You CANNOT see Dev's environment, Dev's node_modules, or Dev's build artifacts.
Your job is to INDEPENDENTLY VERIFY the implementation. Prove the code works. Do NOT just confirm it exists.

== VERIFICATION PROTOCOL ==
1. Reconstruct the implementation from scratch in this clean sandbox.
2. Run ALL feasible tests independently and report command plus output.
3. Verify EACH acceptance criterion by testing behavior, not just reading code.
4. Security audit: command injection, XSS, SQL injection, path traversal, hardcoded secrets, unsafe deserialization, missing input validation.
5. Regression check: verify nothing obvious is broken outside the changed area.

== INTEGRITY RULES ==
- Be skeptical. If something looks off, dig in.
- Investigate failures. Do NOT dismiss any error as "unrelated" without concrete evidence proving it is unrelated.
- If you cannot reproduce Dev's results from scratch, mark it FAILED.
- Do NOT pass something just because Dev says it works.
- Your qa_report.md MUST include the commands you ran and their output. "Tests passed" without evidence is not acceptable.
- Do NOT modify the codebase. You verify, you do not fix.

== OUTPUT ==
- Write qa_report.md with per-criterion passed / failed / blocked status and concrete evidence.
- Include test run results with command and output.
- Include security findings, even if non-blocking.
- Final verdict: passed | failed | blocked."""


def _acceptance_instruction() -> str:
    return """== ACCEPTANCE ROLE ==

You are in a CLEAN sandbox. You cannot run the implementation. You have the full paper trail: requirement, PRD, Dev, and QA.
Your job is to make a FINAL recommendation: go or no-go.

== ASSESSMENT DIMENSIONS ==
1. Requirement coverage: does the implementation satisfy every acceptance criterion?
2. Quality: did QA find issues, and did QA exercise edge cases rather than rubber-stamp?
3. Security: did QA flag security issues, and were they addressed?
4. Risk: signs of incomplete work, tech debt, fragility, or explicit out-of-scope areas.

== INTEGRITY RULES ==
- Do NOT rubber-stamp weak work just to finish the pipeline.
- If QA's evidence is thin, say so. Do not fill the gap with assumptions.
- Cross-reference Dev's claims against QA's findings and flag discrepancies.
- Never claim "all criteria met" when some lack evidence.
- If you are uncertain, say so and explain why. Do NOT fabricate confidence.

== OUTPUT ==
- Produce acceptance_report.md with a summary of what was built.
- Include a Per-criterion pass/fail/blocked table with evidence citations.
- Include security concerns, even if they are not blocking.
- Include a risk assessment with specific, named risks.
- Set recommendation to recommended_go, recommended_no_go, or blocked.
- Explain the rationale with specific evidence from the paper trail, not general impressions.
- Remember: you recommend go/no-go; the human decides."""


def _skill_injection_layer(skills: list[Skill]) -> str:
    return skill_injection_text(skills)


def _install_sandbox_skills(skills: list[Skill], exec_dir: Path) -> None:
    for skill in skills:
        if skill.delivery != "sandbox":
            continue
        destination = exec_dir / ".agent-team" / "skills" / skill.name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(skill.path.parent, destination)


def _stage_context_layer(
    *,
    stage: str,
    execution_context: dict[str, Any],
    contract: StageContract,
    alignment: dict[str, Any],
    tech_plan: dict[str, Any],
    prd_content: str,
    dev_artifacts: DevArtifacts,
    qa_report: str,
    raw_request: str,
) -> str:
    parts = [
        "== STAGE CONTEXT ==",
        f"Stage: {stage}",
        "",
        "=== StageResultEnvelope JSON Schema ===",
        "{",
        '  "session_id": "<provided>",',
        '  "stage": "<provided>",',
        '  "contract_id": "<provided>",',
        '  "status": "completed|passed|failed|blocked",',
        '  "summary": "<one-paragraph summary>",',
        '  "artifact_name": "<e.g. implementation.md>",',
        '  "artifact_content": "<full artifact text>",',
        '  "journal": "<Markdown journal of decisions and observations>",',
        '  "evidence": [{"name": "...", "kind": "report|artifact|command|log|screenshot", "summary": "..."}],',
        '  "findings": []',
        "}",
        "",
        "Return strict JSON only, compatible with StageResultEnvelope. Do NOT wrap in markdown.",
        "",
        "=== Execution Context JSON ===",
        json.dumps(execution_context, ensure_ascii=False, indent=2),
        "",
        "=== Stage Contract JSON ===",
        json.dumps(contract.to_dict(), ensure_ascii=False, indent=2),
    ]
    if alignment:
        parts.extend(["", "=== Confirmed Alignment ===", json.dumps(alignment, ensure_ascii=False, indent=2)])
    if tech_plan:
        parts.extend(["", "=== Technical Plan ===", json.dumps(tech_plan, ensure_ascii=False, indent=2)])
    if raw_request:
        parts.extend(["", "=== Original Request ===", raw_request])
    if prd_content:
        parts.extend(["", "=== PRD ===", prd_content])
    if stage in {"QA", "Acceptance"}:
        parts.extend(
            [
                "",
                "=== Dev Implementation Report ===",
                dev_artifacts.implementation_md,
                "",
                "=== Dev Changed Files ===",
                dev_artifacts.changed_files,
            ]
        )
    if stage == "Acceptance" and qa_report:
        parts.extend(["", "=== QA Report ===", qa_report])
    return "\n".join(parts)


def _envelope_from_model_output(
    *,
    raw: str,
    session_id: str,
    stage: str,
    contract_id: str,
) -> StageResultEnvelope:
    payload = json.loads(raw)
    payload["session_id"] = session_id
    payload["stage"] = stage
    payload["contract_id"] = contract_id
    return StageResultEnvelope.from_dict(payload)


def _alignment_payload(session_dir: Path) -> dict[str, Any]:
    alignment = load_confirmed_alignment(session_dir)
    return alignment.to_dict() if alignment is not None else {}


def _tech_plan_payload(session_dir: Path) -> dict[str, Any]:
    tech_plan = load_confirmed_tech_plan(session_dir)
    return tech_plan.to_dict() if tech_plan is not None else {}


def _read_artifact(artifact_paths: dict[str, str], key: str) -> str:
    value = artifact_paths.get(key)
    if not value:
        return ""
    path = Path(value)
    if not path.exists():
        return ""
    return path.read_text()


def _changed_files_snapshot(repo_root: Path) -> str:
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        return ""
    return "Changed file snapshot is collected by the Dev stage artifact in this version."
