import unittest


class StagePolicyTests(unittest.TestCase):
    def test_default_policy_registry_returns_product_requirements_approval_policy(self) -> None:
        from agent_team.stage_policies import default_policy_registry

        policy = default_policy_registry().get("Product")

        self.assertEqual(policy.stage, "Product")
        self.assertIn("prd.md", policy.required_outputs)
        self.assertEqual(policy.approval_rule, "requires_requirements_approval")
        self.assertIn("explicit_acceptance_criteria", [spec.name for spec in policy.evidence_specs])

    def test_policy_can_compile_to_stage_contract(self) -> None:
        from agent_team.stage_policies import default_policy_registry

        contract = default_policy_registry().build_contract(
            session_id="session-1",
            stage="Dev",
            contract_id="contract-dev",
            input_artifacts={"request": ".agent-team/session/request.md"},
            role_context="Dev role context",
        )

        self.assertEqual(contract.stage, "Dev")
        self.assertEqual(contract.required_outputs, ["implementation.md"])
        self.assertIn("self_verification", contract.evidence_requirements)
        self.assertEqual(contract.role_context, "Dev role context")


if __name__ == "__main__":
    unittest.main()
