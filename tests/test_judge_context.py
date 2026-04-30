import unittest


class JudgeContextTests(unittest.TestCase):
    def test_compact_prioritizes_policy_contract_evidence_and_indexes_artifact(self) -> None:
        from agent_team.judge_context import build_judge_context_compact
        from agent_team.models import EvidenceItem, GateResult, StageResultEnvelope
        from agent_team.stage_policies import default_policy_registry

        registry = default_policy_registry()
        policy = registry.get("Acceptance")
        contract = registry.build_contract(
            session_id="session-1",
            stage="Acceptance",
            contract_id="contract-acceptance",
            input_artifacts={"prd": ".agent-team/session/prd.md"},
        )
        result = StageResultEnvelope(
            session_id="session-1",
            stage="Acceptance",
            status="completed",
            artifact_name="acceptance_report.md",
            artifact_content="# Acceptance\nThe UI matches the approved Figma frame.\n" + ("detail\n" * 300),
            contract_id="contract-acceptance",
            evidence=[
                EvidenceItem(
                    name="product_level_validation",
                    kind="artifact",
                    summary="Screenshot and visual diff reviewed.",
                    artifact_path=".agent-team/session/target.png",
                )
            ],
        )
        hard_gate = GateResult(status="PASSED", reason="All gates passed.")

        compact = build_judge_context_compact(
            policy=policy,
            contract=contract,
            result=result,
            hard_gate_result=hard_gate,
            original_request_summary="Restore the Figma UI.",
            approved_prd_summary="Match the approved Figma frame.",
            approved_acceptance_matrix=[
                {
                    "id": "AC-001",
                    "scenario": "Figma restoration",
                    "standard": "UI matches the approved frame.",
                    "required_evidence": ["product_level_validation"],
                    "failure_target": "Dev",
                }
            ],
        )

        payload = compact.to_dict()
        self.assertEqual(payload["stage"], "Acceptance")
        self.assertEqual(payload["hard_gate_result"]["status"], "PASSED")
        self.assertEqual(payload["acceptance_matrix"][0]["id"], "AC-001")
        self.assertEqual(payload["artifact_index"][0]["name"], "acceptance_report.md")
        self.assertLess(len(payload["artifact_index"][0]["summary"]), len(result.artifact_content))
        self.assertEqual(payload["evidence_index"][0]["name"], "product_level_validation")


if __name__ == "__main__":
    unittest.main()
