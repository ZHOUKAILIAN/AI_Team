from __future__ import annotations

from dataclasses import dataclass, field

from .models import AcceptanceContract, EvidenceRequirement, StageContract
from .workflow import STAGES


DEFAULT_FORBIDDEN_ACTIONS = [
    "must_not_change_stage_order",
    "must_not_skip_required_artifacts",
    "must_not_claim_workflow_done",
    "must_not_rewrite_upper_layer_truth_from_lower_layer",
    "must_not_promote_l5_or_research_to_formal_truth",
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


def technical_design_policy() -> StagePolicy:
    return StagePolicy(
        stage="TechnicalDesign",
        goal=(
            "Draft the Layer 2 technical design from approved ProductDefinition and ProjectRuntime deltas, "
            "current implementation reality, and route constraints. Do not edit product code in this stage."
        ),
        required_outputs=["technical-design.md"],
        evidence_specs=[
            EvidenceRequirement(
                name="technical_design_plan",
                allowed_kinds=["artifact", "report"],
                required_fields=["summary"],
            )
        ],
        approval_rule="requires_technical_design_approval",
        allow_findings=False,
    )


def technical_design_stage_policy() -> StagePolicy:
    return technical_design_policy()


def default_policy_registry() -> PolicyRegistry:
    return PolicyRegistry(
        [
            StagePolicy(
                stage="Route",
                goal=(
                    "Classify the request into affected five-layer responsibilities, red lines, baseline sources, "
                    "and required stages. This is routing and governance classification, not implementation."
                ),
                required_outputs=["route-packet.json"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="route_classification",
                        allowed_kinds=["artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
                allow_findings=False,
            ),
            StagePolicy(
                stage="ProductDefinition",
                goal=(
                    "Extract Layer 1 product-definition candidates from the request, explicitly separate non-L1 "
                    "task content, and stop for product-definition approval."
                ),
                required_outputs=["product-definition-delta.md"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="l1_classification",
                        allowed_kinds=["artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
                approval_rule="requires_product_definition_approval",
                allow_findings=False,
            ),
            StagePolicy(
                stage="ProjectRuntime",
                goal=(
                    "Capture Layer 3 project landing deltas: default entrypoints, run commands, layout, packaging, "
                    "configuration, and project-specific runtime defaults. Do not redefine product semantics."
                ),
                required_outputs=["project-landing-delta.md"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="project_landing_review",
                        allowed_kinds=["artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
            ),
            technical_design_policy(),
            StagePolicy(
                stage="Implementation",
                goal=(
                    "Implement the approved technical design as Layer 2 product implementation reality, then "
                    "provide code review and self-verification evidence."
                ),
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
                failback_targets=["Implementation"],
            ),
            StagePolicy(
                stage="Verification",
                goal=(
                    "Independently verify the implementation against approved L1/L3 deltas, technical design, "
                    "and current implementation reality."
                ),
                required_outputs=["verification-report.md"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="independent_verification",
                        allowed_kinds=["command", "artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
                allowed_agent_statuses=["completed", "failed", "blocked", "partial", "needs_verification"],
                failback_targets=["Implementation"],
            ),
            StagePolicy(
                stage="GovernanceReview",
                goal=(
                    "Review the run for five-layer boundary violations, evidence quality, writeback obligations, "
                    "public/private risk, and merge readiness."
                ),
                required_outputs=["governance-review.md"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="layer_governance_review",
                        allowed_kinds=["artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
                failback_targets=["Route", "ProductDefinition", "ProjectRuntime", "TechnicalDesign", "Implementation"],
            ),
            StagePolicy(
                stage="Acceptance",
                goal=(
                    "Recommend final Go/No-Go from product result and governance evidence. Do not claim the human "
                    "decision."
                ),
                required_outputs=["acceptance-report.md"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="product_and_governance_validation",
                        allowed_kinds=["artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
                failback_targets=["ProductDefinition", "TechnicalDesign", "Implementation", "GovernanceReview"],
            ),
            StagePolicy(
                stage="SessionHandoff",
                goal=(
                    "Preserve Layer 5 local control state: current session facts, next action, unresolved decisions, "
                    "and non-promoted local material."
                ),
                required_outputs=["session-handoff.md"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="local_control_handoff",
                        allowed_kinds=["artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
            ),
        ]
    )
