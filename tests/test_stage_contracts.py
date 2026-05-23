import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class StageContractTests(unittest.TestCase):
    def test_product_definition_contract_contains_required_outputs_and_forbidden_actions(self) -> None:
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("classify stable product semantics", runtime_mode="harness")

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="ProductDefinition",
            )

        self.assertEqual(contract.stage, "ProductDefinition")
        self.assertIn("product-definition-delta.md", contract.required_outputs)
        self.assertIn("l1_classification", contract.evidence_requirements)
        self.assertIn("must_not_change_stage_order", contract.forbidden_actions)
        self.assertEqual(contract.input_artifacts, {})

    def test_product_definition_contract_uses_l1_language(self) -> None:
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("Build a harness-first workflow", runtime_mode="harness")

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="ProductDefinition",
            )

        self.assertIn("Layer 1", contract.goal)
        self.assertNotIn("CEO approval", contract.goal)

    def test_technical_design_contract_uses_technical_design_role_context(self) -> None:
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("Build a harness-first workflow", runtime_mode="harness")
            summary = store.load_workflow_summary(session.session_id)
            summary.current_state = "TechnicalDesign"
            summary.current_stage = "TechnicalDesign"
            store.save_workflow_summary(session, summary)

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="TechnicalDesign",
            )

        self.assertEqual(contract.stage, "TechnicalDesign")
        self.assertIn("technical-design.md", contract.required_outputs)
        self.assertIn("technical_design_plan", contract.evidence_requirements)
        self.assertIn("TechnicalDesign Contract", contract.role_context)
        self.assertIn("technical-design.md", contract.role_context)

    def test_verification_contract_requires_independent_evidence(self) -> None:
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("Build a harness-first workflow", runtime_mode="harness")

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="Verification",
            )

        self.assertIn("verification-report.md", contract.required_outputs)
        self.assertIn("independent_verification", contract.evidence_requirements)
        self.assertEqual(contract.evidence_specs[0].name, "independent_verification")
        self.assertIn("summary", contract.evidence_specs[0].required_fields)
        self.assertIn("command", contract.evidence_specs[0].allowed_kinds)

    def test_contract_role_context_includes_learned_context_memory_and_skill(self) -> None:
        from agent_team.models import Finding
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("Build a harness-first workflow", runtime_mode="harness")
            store.apply_learning(
                Finding(
                    source_stage="Verification",
                    target_stage="Implementation",
                    issue="Missing empty-state evidence.",
                    lesson="Preserve empty-state validation in follow-up rounds.",
                    proposed_context_update="Review empty-state behavior before handoff.",
                    proposed_contract_update="Require visible empty-state evidence before reporting success.",
                )
            )

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="Implementation",
            )

        self.assertIn("Review empty-state behavior before handoff.", contract.role_context)
        self.assertIn("Require visible empty-state evidence", contract.role_context)


    def test_service_health_verification_profile_adds_required_evidence(self) -> None:
        from dataclasses import replace
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("Add minimal API health service", runtime_mode="harness")
            summary = store.load_workflow_summary(session.session_id)
            store.save_workflow_summary(
                session,
                replace(
                    summary,
                    current_state="Verification",
                    current_stage="Verification",
                    verification_profile="service_health",
                ),
            )

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="Verification",
            )

        self.assertIn("independent_verification", contract.evidence_requirements)
        self.assertIn("service_health_contract", contract.evidence_requirements)
        self.assertIn("service_health_in_process", contract.evidence_requirements)
        self.assertIn("service_health_capability", contract.evidence_requirements)


    def test_service_health_governance_requires_audit_evidence(self) -> None:
        from dataclasses import replace
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("Add minimal API health service", runtime_mode="harness")
            summary = store.load_workflow_summary(session.session_id)
            store.save_workflow_summary(
                session,
                replace(
                    summary,
                    current_state="GovernanceReview",
                    current_stage="GovernanceReview",
                    verification_profile="service_health",
                ),
            )

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="GovernanceReview",
            )

        self.assertIn("layer_governance_review", contract.evidence_requirements)
        self.assertIn("service_health_evidence_audit", contract.evidence_requirements)

    def test_session_handoff_contract_does_not_include_retrieved_memory(self) -> None:
        from agent_team.models import Finding
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("Add minimal API health service", runtime_mode="harness")
            store.apply_learning(
                Finding(
                    source_stage="GovernanceReview",
                    target_stage="SessionHandoff",
                    issue="Old governance mapping defect should not leak into unrelated handoffs.",
                    lesson="Mention agt-control/project/doc-map.json governance mapping.",
                    proposed_context_update="Old governance mapping issue from another session.",
                    proposed_contract_update="Old unrelated requirement.",
                )
            )

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="SessionHandoff",
            )

        self.assertIn("Current-Session Only", contract.role_context)
        self.assertNotIn("Relevant Memory", contract.role_context)
        self.assertNotIn("doc-map.json governance mapping", contract.role_context)

    def test_implementation_contract_excludes_state_artifacts_from_inputs(self) -> None:
        from agent_team.execution_context import build_stage_execution_context
        from agent_team.models import EvidenceItem, StageResultEnvelope
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("Build a harness-first workflow", runtime_mode="harness")
            technical_design_result = StageResultEnvelope(
                session_id=session.session_id,
                contract_id="technical-design-contract",
                stage="TechnicalDesign",
                status="completed",
                artifact_name="technical-design.md",
                artifact_content="# Technical Design\n",
                journal="# TechnicalDesign Journal\n",
                evidence=[
                    EvidenceItem(
                        name="technical_design_plan",
                        kind="report",
                        summary="Technical design documented.",
                    )
                ],
                summary="Drafted technical design",
            )
            stage_record = store.record_stage_result(session.session_id, technical_design_result)
            summary = store.load_workflow_summary(session.session_id)
            summary.artifact_paths["technical_design"] = str(stage_record.artifact_path)
            store.save_workflow_summary(session, summary)

            initial_contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="Implementation",
            )
            context = build_stage_execution_context(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="Implementation",
                contract=initial_contract,
            )
            context_path = store.save_execution_context(context)

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="Implementation",
            )

        self.assertIn("technical_design", contract.input_artifacts)
        self.assertNotIn("session", contract.input_artifacts)
        self.assertNotIn("workflow_summary", contract.input_artifacts)
        self.assertNotIn("execution_context", contract.input_artifacts)
        self.assertNotIn(str(context_path), contract.input_artifacts.values())

    def test_session_handoff_contract_inputs_exclude_state_files_and_include_formal_artifacts(self) -> None:
        from agent_team.stage_contracts import build_stage_contract
        from agent_team.state import StateStore

        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("Build a harness-first workflow", runtime_mode="harness")
            artifact_dir = session.artifact_dir
            route_path = artifact_dir / "route-packet.json"
            product_definition_path = artifact_dir / "product-definition-delta.md"
            project_runtime_path = artifact_dir / "project-landing-delta.md"
            technical_design_path = artifact_dir / "technical-design.md"
            implementation_path = artifact_dir / "implementation.md"
            verification_path = artifact_dir / "verification-report.md"
            governance_review_path = artifact_dir / "governance-review.md"
            acceptance_path = artifact_dir / "acceptance-report.md"
            execution_context_path = session.session_dir / "execution-context.json"
            for path, content in (
                (route_path, "{}"),
                (product_definition_path, "# Product Definition Delta\n"),
                (project_runtime_path, "# Project Landing Delta\n"),
                (technical_design_path, "# Technical Design\n"),
                (implementation_path, "# Implementation\n"),
                (verification_path, "# Verification Report\n"),
                (governance_review_path, "# Governance Review\n"),
                (acceptance_path, "# Acceptance Report\n"),
                (execution_context_path, "{}"),
            ):
                path.write_text(content)
            summary = store.load_workflow_summary(session.session_id)
            summary.artifact_paths.update(
                {
                    "route": str(route_path),
                    "product_definition": str(product_definition_path),
                    "project_runtime": str(project_runtime_path),
                    "technical_design": str(technical_design_path),
                    "implementation": str(implementation_path),
                    "verification": str(verification_path),
                    "governance_review": str(governance_review_path),
                    "acceptance": str(acceptance_path),
                    "execution_context": str(execution_context_path),
                }
            )
            store.save_workflow_summary(session, summary)

            contract = build_stage_contract(
                repo_root=repo_root,
                state_store=store,
                session_id=session.session_id,
                stage="SessionHandoff",
            )

        self.assertEqual(
            contract.input_artifacts,
            {
                "route": str(route_path),
                "product_definition": str(product_definition_path),
                "project_runtime": str(project_runtime_path),
                "technical_design": str(technical_design_path),
                "implementation": str(implementation_path),
                "verification": str(verification_path),
                "governance_review": str(governance_review_path),
                "acceptance": str(acceptance_path),
            },
        )


if __name__ == "__main__":
    unittest.main()
