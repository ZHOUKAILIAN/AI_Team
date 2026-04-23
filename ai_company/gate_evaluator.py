from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .gatekeeper import evaluate_candidate
from .judge_context import JudgeContextCompact, build_judge_context_compact
from .models import Finding, GateResult, SessionRecord, StageContract, StageResultEnvelope
from .stage_policies import StagePolicy


@dataclass(slots=True)
class JudgeResult:
    verdict: str
    target_stage: str | None = None
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    trace_id: str = ""


@dataclass(slots=True)
class GateDecision:
    outcome: str
    target_stage: str | None = None
    reason: str = ""
    missing_outputs: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    judge_verdict: str = ""
    judge_confidence: float | None = None
    judge_trace_id: str = ""
    derived_status: str = ""


@dataclass(slots=True)
class StageEvaluation:
    policy: StagePolicy
    result: StageResultEnvelope
    hard_gate_result: GateResult
    judge_context: JudgeContextCompact | None
    judge_result: JudgeResult | None
    decision: GateDecision


class Judge(Protocol):
    def judge(self, context: JudgeContextCompact) -> JudgeResult:
        raise NotImplementedError


class NoopJudge:
    def judge(self, context: JudgeContextCompact) -> JudgeResult:
        return JudgeResult(
            verdict="pass",
            confidence=1.0,
            reasons=["Noop judge defaulted to pass."],
        )


class GateEvaluator:
    def __init__(self, *, judge: Judge | None = None) -> None:
        self.judge = judge or NoopJudge()

    def evaluate(
        self,
        *,
        session: SessionRecord,
        policy: StagePolicy,
        contract: StageContract,
        result: StageResultEnvelope,
        original_request_summary: str,
        approved_prd_summary: str,
        approved_acceptance_matrix: list[dict[str, object]],
    ) -> StageEvaluation:
        hard_gate_result, normalized = evaluate_candidate(
            session=session,
            contract=contract,
            result=result,
            acceptance_contract=policy.acceptance_contract,
        )

        if hard_gate_result.status == "BLOCKED":
            return StageEvaluation(
                policy=policy,
                result=normalized,
                hard_gate_result=hard_gate_result,
                judge_context=None,
                judge_result=None,
                decision=GateDecision(
                    outcome="blocked",
                    reason=hard_gate_result.reason,
                    missing_outputs=list(hard_gate_result.missing_outputs),
                    missing_evidence=list(hard_gate_result.missing_evidence),
                    findings=list(hard_gate_result.findings),
                    derived_status="blocked",
                ),
            )

        if hard_gate_result.status != "PASSED":
            return StageEvaluation(
                policy=policy,
                result=normalized,
                hard_gate_result=hard_gate_result,
                judge_context=None,
                judge_result=None,
                decision=GateDecision(
                    outcome="rework",
                    target_stage=_default_rework_target(policy),
                    reason=hard_gate_result.reason,
                    missing_outputs=list(hard_gate_result.missing_outputs),
                    missing_evidence=list(hard_gate_result.missing_evidence),
                    findings=list(hard_gate_result.findings),
                    derived_status="rework",
                ),
            )

        judge_context = build_judge_context_compact(
            policy=policy,
            contract=contract,
            result=normalized,
            hard_gate_result=hard_gate_result,
            original_request_summary=original_request_summary,
            approved_prd_summary=approved_prd_summary,
            approved_acceptance_matrix=approved_acceptance_matrix,
            previous_findings=list(hard_gate_result.findings),
        )
        judge_result = self.judge.judge(judge_context)
        decision = _decision_from_judge(policy=policy, hard_gate_result=hard_gate_result, judge_result=judge_result)

        return StageEvaluation(
            policy=policy,
            result=normalized,
            hard_gate_result=hard_gate_result,
            judge_context=judge_context,
            judge_result=judge_result,
            decision=decision,
        )


def _default_rework_target(policy: StagePolicy) -> str:
    return policy.failback_targets[0] if policy.failback_targets else policy.stage


def _decision_from_judge(*, policy: StagePolicy, hard_gate_result: GateResult, judge_result: JudgeResult) -> GateDecision:
    verdict = judge_result.verdict.strip().lower()

    if verdict == "pass":
        return GateDecision(
            outcome="pass",
            reason="Hard gate and judge both passed.",
            findings=list(hard_gate_result.findings) + list(judge_result.findings),
            judge_verdict=judge_result.verdict,
            judge_confidence=judge_result.confidence,
            judge_trace_id=judge_result.trace_id,
            derived_status="pass",
        )

    if verdict == "blocked":
        return GateDecision(
            outcome="blocked",
            target_stage=judge_result.target_stage,
            reason="; ".join(judge_result.reasons) or "Judge blocked the stage.",
            findings=list(hard_gate_result.findings) + list(judge_result.findings),
            missing_evidence=list(judge_result.missing_evidence),
            judge_verdict=judge_result.verdict,
            judge_confidence=judge_result.confidence,
            judge_trace_id=judge_result.trace_id,
            derived_status="blocked",
        )

    if verdict == "needs_human":
        return GateDecision(
            outcome="await_human",
            target_stage=judge_result.target_stage,
            reason="; ".join(judge_result.reasons) or "Judge requested human review.",
            findings=list(hard_gate_result.findings) + list(judge_result.findings),
            missing_evidence=list(judge_result.missing_evidence),
            judge_verdict=judge_result.verdict,
            judge_confidence=judge_result.confidence,
            judge_trace_id=judge_result.trace_id,
            derived_status="await_human",
        )

    return GateDecision(
        outcome="rework",
        target_stage=judge_result.target_stage or _default_rework_target(policy),
        reason="; ".join(judge_result.reasons) or "Judge requested rework.",
        findings=list(hard_gate_result.findings) + list(judge_result.findings),
        missing_evidence=list(judge_result.missing_evidence),
        judge_verdict=judge_result.verdict,
        judge_confidence=judge_result.confidence,
        judge_trace_id=judge_result.trace_id,
        derived_status="rework",
    )
