from __future__ import annotations

from dataclasses import dataclass, field

from .models import AcceptanceContract, EvidenceRequirement, StageContract


DEFAULT_FORBIDDEN_ACTIONS = [
    "must_not_change_stage_order",
    "must_not_skip_required_artifacts",
    "must_not_claim_workflow_done",
]


@dataclass(slots=True)
class StagePolicy:
    stage: str
    goal: str
    required_outputs: list[str]
    evidence_specs: list[EvidenceRequirement]
    required_checks: list[str] = field(default_factory=list)
    allowed_agent_statuses: list[str] = field(default_factory=lambda: ["completed", "failed", "blocked"])
    pass_rule: str = "hard_gate_and_judge_must_pass"
    failback_targets: list[str] = field(default_factory=list)
    approval_rule: str | None = None
    acceptance_contract: AcceptanceContract | None = None
    allow_findings: bool = True
    blocking_conditions: list[str] = field(default_factory=list)

    @property
    def evidence_requirements(self) -> list[str]:
        return [spec.name for spec in self.evidence_specs if spec.required]


class PolicyRegistry:
    def __init__(self, policies: list[StagePolicy]) -> None:
        self._policies = {policy.stage: policy for policy in policies}

    def get(self, stage: str) -> StagePolicy:
        try:
            return self._policies[stage]
        except KeyError as exc:
            raise KeyError(f"Unsupported stage policy: {stage}") from exc

    def build_contract(
        self,
        *,
        session_id: str,
        stage: str,
        contract_id: str,
        input_artifacts: dict[str, str],
        role_context: str = "",
    ) -> StageContract:
        policy = self.get(stage)
        return StageContract(
            session_id=session_id,
            stage=stage,
            contract_id=contract_id,
            goal=policy.goal,
            input_artifacts=dict(input_artifacts),
            required_outputs=list(policy.required_outputs),
            forbidden_actions=list(DEFAULT_FORBIDDEN_ACTIONS),
            evidence_requirements=policy.evidence_requirements,
            evidence_specs=list(policy.evidence_specs),
            role_context=role_context,
        )


def default_policy_registry() -> PolicyRegistry:
    return PolicyRegistry(
        [
            StagePolicy(
                stage="Product",
                goal="Draft a PRD with explicit acceptance criteria and stop for requirements approval.",
                required_outputs=["prd.md"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="explicit_acceptance_criteria",
                        allowed_kinds=["artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
                approval_rule="requires_requirements_approval",
                allow_findings=False,
            ),
            StagePolicy(
                stage="TechPlan",
                goal="Draft a concrete technical implementation plan from the approved PRD without editing code.",
                required_outputs=["technical_plan.md"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="implementation_plan",
                        allowed_kinds=["artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
                approval_rule="requires_technical_plan_approval",
                allow_findings=False,
            ),
            StagePolicy(
                stage="Dev",
                goal="Implement the approved PRD, review the changed code, and provide self-verification evidence.",
                required_outputs=["implementation.md"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="self_code_review",
                        allowed_kinds=["artifact", "report"],
                        required_fields=["summary"],
                    ),
                    EvidenceRequirement(
                        name="self_verification",
                        allowed_kinds=["command", "artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
                failback_targets=["Dev"],
            ),
            StagePolicy(
                stage="QA",
                goal="Independently rerun critical verification and report passed, failed, or blocked.",
                required_outputs=["qa_report.md"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="independent_verification",
                        allowed_kinds=["command", "artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
                failback_targets=["Dev"],
            ),
            StagePolicy(
                stage="Acceptance",
                goal="Validate user-visible behavior against the approved acceptance criteria.",
                required_outputs=["acceptance_report.md"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="product_level_validation",
                        allowed_kinds=["artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
                failback_targets=["Product", "Dev"],
            ),
        ]
    )
