from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .alignment import load_confirmed_alignment
from .codex_exec import CodexExecConfig, CodexExecRunner
from .execution_context import build_stage_execution_context
from .gatekeeper import evaluate_candidate
from .models import GateResult, StageContract, StageResultEnvelope, StageRunRecord
from .stage_contracts import build_stage_contract
from .stage_machine import StageMachine
from .state import StateStore
from .tech_plan import load_confirmed_tech_plan


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
) -> str:
    if stage == "Product":
        return _product_prompt(
            execution_context=execution_context,
            contract=contract,
            confirmed_alignment=confirmed_alignment or {},
            tech_plan=tech_plan or {},
            raw_request=raw_request,
        )
    if stage == "Dev":
        return _dev_prompt(
            execution_context=execution_context,
            contract=contract,
            confirmed_alignment=confirmed_alignment or {},
            tech_plan=tech_plan or {},
            prd_content=prd_content,
        )
    if stage == "QA":
        return _qa_prompt(
            execution_context=execution_context,
            contract=contract,
            confirmed_alignment=confirmed_alignment or {},
            tech_plan=tech_plan or {},
            prd_content=prd_content,
            dev_implementation_md=dev_implementation_md,
            dev_changed_files=dev_changed_files,
        )
    if stage == "Acceptance":
        return _acceptance_prompt(
            execution_context=execution_context,
            contract=contract,
            confirmed_alignment=confirmed_alignment or {},
            tech_plan=tech_plan or {},
            prd_content=prd_content,
            dev_implementation_md=dev_implementation_md,
            qa_report_content=qa_report_content,
            raw_request=raw_request,
        )
    raise ValueError(f"Unknown stage: {stage}")


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

        codex_dir = session.session_dir / "codex_exec"
        codex_dir.mkdir(parents=True, exist_ok=True)
        output_path = codex_dir / f"{stage.lower()}_last_message.json"
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
        )
        (codex_dir / f"{stage.lower()}_prompt.md").write_text(prompt)
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

        envelope = _envelope_from_model_output(
            raw=result.last_message,
            session_id=session_id,
            stage=stage,
            contract_id=contract.contract_id,
        )
        bundle_path = codex_dir / f"{stage.lower()}_bundle.json"
        bundle_path.write_text(json.dumps(envelope.to_dict(), ensure_ascii=False, indent=2))

        submitted = self.state_store.submit_stage_run_result(run.run_id, envelope)
        return self._verify_submitted_run(submitted, contract, envelope)

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


def _product_prompt(
    *,
    execution_context: dict[str, Any],
    contract: StageContract,
    confirmed_alignment: dict[str, Any],
    tech_plan: dict[str, Any],
    raw_request: str,
) -> str:
    return _common_prompt_header("Product", execution_context, contract) + "\n\n".join(
        [
            "",
            "You are the Product stage agent for AI_Team.",
            "Write a PRD that preserves the human-confirmed requirement and acceptance criteria.",
            "Input:",
            f"- Original requirement: {raw_request}",
            "- Confirmed alignment JSON:",
            json.dumps(confirmed_alignment, ensure_ascii=False, indent=2),
            "- Technical plan JSON:",
            json.dumps(tech_plan, ensure_ascii=False, indent=2),
            'Output: StageResultEnvelope JSON with artifact_name "prd.md".',
            'Evidence must include "explicit_acceptance_criteria".',
        ]
    )


def _dev_prompt(
    *,
    execution_context: dict[str, Any],
    contract: StageContract,
    confirmed_alignment: dict[str, Any],
    tech_plan: dict[str, Any],
    prd_content: str,
) -> str:
    return _common_prompt_header("Dev", execution_context, contract) + "\n\n".join(
        [
            "",
            "You are the Dev stage agent for AI_Team.",
            "Given the task specification, implement the feature completely.",
            "Don't gold-plate, but don't leave it half-done.",
            "Sandbox: workspace-write. You have full access to the repository.",
            "",
            "Input:",
            "- Confirmed alignment JSON:",
            json.dumps(confirmed_alignment, ensure_ascii=False, indent=2),
            "- Technical plan JSON:",
            json.dumps(tech_plan, ensure_ascii=False, indent=2),
            "- PRD:",
            prd_content,
            "== SCOPE ==",
            "- Implement ONLY what the technical plan and acceptance criteria define.",
            '- Do NOT add features, refactor unrelated code, or make "improvements" beyond what was asked.',
            "- Do NOT add error handling, fallbacks, or validation for scenarios that cannot happen.",
            "- Trust internal code and framework guarantees.",
            "- Do NOT create helpers, utilities, or abstractions for one-time operations.",
            "- Three similar lines are better than a premature abstraction.",
            "- Do NOT create documentation files beyond what the stage contract requires.",
            "",
            "== SECURITY ==",
            "- Prioritize writing safe, secure, and correct code.",
            "- Be careful not to introduce security vulnerabilities such as command injection, XSS, SQL injection, and other OWASP top 10 vulnerabilities.",
            "- If you notice that you wrote insecure code, immediately fix it.",
            "",
            "== SELF-VERIFICATION ==",
            "- Run tests and typecheck before reporting done.",
            "- If tests fail, report the failure with output. Do NOT suppress or simplify failures to make the result look clean.",
            "- If you did not run a verification step, say so rather than implying it succeeded.",
            '- Never claim "all tests pass" when output shows failures.',
            "- Never characterize incomplete or broken work as done.",
            "",
            "== OUTPUT ==",
            "- Write implementation.md describing what changed and why.",
            "- Include files modified with absolute paths.",
            "- Include commands run and their actual output.",
            "- Include any limitations or known issues.",
            "- Report back with specific, actionable results, including file paths, commit hashes when available, and test run summaries.",
            "",
            "== BOUNDARY ==",
            "- You are a STAGE AGENT. You only have authority over the Dev stage.",
            "- Do NOT attempt to advance the workflow state machine.",
            "- Do NOT call record-human-decision or modify session state.",
            "- Submit your stage result and stop. The runtime handles what comes next.",
            "- Do NOT run destructive git operations such as force push, hard reset, or branch delete unless explicitly instructed by the stage contract.",
            "",
            'Output: StageResultEnvelope JSON with artifact_name "implementation.md".',
        ]
    )


def _qa_prompt(
    *,
    execution_context: dict[str, Any],
    contract: StageContract,
    confirmed_alignment: dict[str, Any],
    tech_plan: dict[str, Any],
    prd_content: str,
    dev_implementation_md: str,
    dev_changed_files: str,
) -> str:
    return _common_prompt_header("QA", execution_context, contract) + "\n\n".join(
        [
            "",
            "You are the QA stage agent for AI_Team.",
            "",
            "== CRITICAL: CLEAN SANDBOX ==",
            "You are in a CLEAN sandbox.",
            "The Dev agent worked in a DIFFERENT sandbox that you cannot access.",
            "You CANNOT see Dev's environment, Dev's node_modules, or Dev's build artifacts.",
            "Your job is to INDEPENDENTLY VERIFY the implementation.",
            "Prove the code works. Do NOT just confirm it exists.",
            "",
            "Input:",
            "- Confirmed alignment JSON:",
            json.dumps(confirmed_alignment, ensure_ascii=False, indent=2),
            "- Technical plan JSON:",
            json.dumps(tech_plan, ensure_ascii=False, indent=2),
            "- PRD:",
            prd_content,
            "- Dev implementation.md:",
            dev_implementation_md,
            "- Dev changed files snapshot:",
            dev_changed_files,
            "== VERIFICATION PROTOCOL ==",
            "1. Reconstruct the implementation from scratch in this clean sandbox:",
            "   - Apply Dev's changed files to a clean copy of the codebase.",
            "   - Install dependencies from scratch when feasible.",
            "   - Build from source when the project supports it.",
            "2. Run tests independently:",
            "   - Unit tests, integration tests, type checking, linting, and any targeted checks needed for the change.",
            "   - Report the actual command and its output, not only a summary.",
            "3. Verify EACH acceptance criterion:",
            "   - Test the behavior, not just read the code.",
            "   - Try edge cases and error paths when they are in scope.",
            "   - Do NOT assume Dev's self-assessment is correct.",
            "4. Security audit:",
            "   - Check for command injection, XSS, SQL injection, path traversal, hardcoded secrets, unsafe deserialization, and missing input validation at system boundaries.",
            "   - Flag any security concern even if you are not fully certain.",
            "5. Regression check:",
            "   - Verify nothing obvious is broken outside the changed area.",
            "   - Review common bug patterns such as null checks, error handling, and race conditions.",
            "",
            "== INTEGRITY RULES ==",
            "- Be skeptical. If something looks off, dig in.",
            '- Investigate failures. Do NOT dismiss any error as "unrelated" without concrete evidence proving it is unrelated.',
            "- If you cannot reproduce Dev's results from scratch, mark the stage FAILED.",
            "- Do NOT pass something just because Dev says it works.",
            "- Never claim tests pass when output shows failures.",
            "- Never suppress or simplify failing checks to manufacture a green result.",
            '- Your qa_report.md MUST include the commands you ran and their output. "Tests passed" without evidence is not acceptable.',
            "",
            "== SCOPE ==",
            "- Verify ONLY what the acceptance criteria define, plus security problems you notice.",
            "- Do NOT audit unrelated areas beyond the stage contract.",
            "- Do NOT gold-plate the verification. Be thorough, not exhaustive.",
            "",
            "== BOUNDARY ==",
            "- You are a STAGE AGENT. You only have authority over the QA stage.",
            "- Do NOT attempt to advance the workflow state machine.",
            "- Do NOT call record-human-decision or modify session state.",
            "- Do NOT modify the codebase. You verify, you do not fix.",
            "- Submit your stage result and stop. The runtime handles what comes next.",
            "",
            'Output: StageResultEnvelope JSON with artifact_name "qa_report.md" and status "passed", "failed", or "blocked".',
            'Evidence must include "independent_verification".',
        ]
    )


def _acceptance_prompt(
    *,
    execution_context: dict[str, Any],
    contract: StageContract,
    confirmed_alignment: dict[str, Any],
    tech_plan: dict[str, Any],
    prd_content: str,
    dev_implementation_md: str,
    qa_report_content: str,
    raw_request: str,
) -> str:
    return _common_prompt_header("Acceptance", execution_context, contract) + "\n\n".join(
        [
            "",
            "You are the Acceptance stage agent for AI_Team.",
            "You are in a CLEAN sandbox. You cannot run the implementation.",
            "You have the full paper trail: requirement, PRD, Dev, and QA.",
            "Your job is to make a FINAL recommendation: go or no-go.",
            "",
            "Input:",
            f"- Original requirement: {raw_request}",
            "- Confirmed alignment JSON:",
            json.dumps(confirmed_alignment, ensure_ascii=False, indent=2),
            "- Technical plan JSON:",
            json.dumps(tech_plan, ensure_ascii=False, indent=2),
            "- PRD:",
            prd_content,
            "- Dev implementation.md:",
            dev_implementation_md,
            "- QA qa_report.md:",
            qa_report_content,
            "== ASSESSMENT DIMENSIONS ==",
            "1. Requirement coverage:",
            "   - Does the implementation satisfy every acceptance criterion?",
            "   - Cross-reference PRD, Dev, and QA for gaps.",
            "2. Quality assessment:",
            "   - Did QA find issues? What severity?",
            "   - Are there unresolved concerns?",
            "   - Did QA actually exercise edge cases or just rubber-stamp?",
            "   - If QA's report lacks concrete command output, flag it.",
            "3. Security assessment:",
            "   - Did QA flag any security issues? Were they addressed?",
            "   - Review the paper trail for signs of command injection, XSS, missing input validation, or other unsafe patterns.",
            "4. Risk assessment:",
            "   - Look for signs of incomplete work, tech debt, fragility, or explicit out-of-scope areas.",
            "",
            "== INTEGRITY RULES ==",
            "- Do NOT rubber-stamp weak work just to finish the pipeline.",
            "- If QA's evidence is thin, say so. Do not fill the gap with assumptions.",
            "- Cross-reference Dev's claims against QA's findings and flag discrepancies.",
            '- Never claim "all criteria met" when some lack evidence.',
            "- If you are uncertain, say so and explain why. Do NOT fabricate confidence.",
            "",
            "== OUTPUT ==",
            "- Produce acceptance_report.md with a summary of what was built.",
            "- Include a Per-criterion pass/fail/blocked table with evidence citations.",
            "- Include security concerns, even if they are not blocking.",
            "- Include a risk assessment with specific, named risks.",
            "- Set recommendation to recommended_go, recommended_no_go, or blocked.",
            "- Explain the rationale with specific evidence from the paper trail, not general impressions.",
            "",
            "== BOUNDARY ==",
            "- You are a STAGE AGENT. You only have authority over the Acceptance stage.",
            "- Do NOT attempt to advance the workflow state machine.",
            "- Do NOT call record-human-decision or modify session state.",
            "- You recommend go/no-go to the human; the human decides.",
            "- Submit your stage result and stop. The runtime handles what comes next.",
            "",
            'Output: StageResultEnvelope JSON with artifact_name "acceptance_report.md".',
            'Set acceptance_status to "recommended_go", "recommended_no_go", or "blocked".',
            'Evidence must include "product_level_validation".',
        ]
    )


def _common_prompt_header(stage: str, execution_context: dict[str, Any], contract: StageContract) -> str:
    return "\n\n".join(
        [
            f"AI_Team {stage} stage execution.",
            "Return strict JSON only, compatible with StageResultEnvelope. Do not wrap it in markdown.",
            "StageResultEnvelope required keys: session_id, contract_id, stage, status, artifact_name, artifact_content, journal, findings, evidence, summary.",
            "Execution context JSON:",
            json.dumps(execution_context, ensure_ascii=False, indent=2),
            "Stage contract JSON:",
            json.dumps(contract.to_dict(), ensure_ascii=False, indent=2),
        ]
    )


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
