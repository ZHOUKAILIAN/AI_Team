import unittest


class RecordingJudge:
    def __init__(self, verdict: str, *, target_stage: str | None = None) -> None:
        self.verdict = verdict
        self.target_stage = target_stage
        self.calls = []

    def judge(self, context):
        from agent_team.gate_evaluator import JudgeResult

        self.calls.append(context)
        return JudgeResult(
            verdict=self.verdict,
            target_stage=self.target_stage,
            confidence=0.91,
            reasons=["judge reason"],
        )


class GateEvaluatorTests(unittest.TestCase):
    def test_pass_requires_hard_gate_and_judge_pass(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from agent_team.gate_evaluator import GateEvaluator
        from agent_team.models import EvidenceItem, StageResultEnvelope
        from agent_team.stage_policies import default_policy_registry
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("restore figma")
            registry = default_policy_registry()
            contract = registry.build_contract(
                session_id=session.session_id,
                stage="Acceptance",
                contract_id="contract-acceptance",
                input_artifacts={},
            )
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Acceptance",
                status="completed",
                artifact_name="acceptance_report.md",
                artifact_content="# Acceptance\nLooks good.\n",
                contract_id="contract-acceptance",
                evidence=[
                    EvidenceItem(
                        name="product_level_validation",
                        kind="artifact",
                        summary="Visual evidence reviewed.",
                    )
                ],
            )
            judge = RecordingJudge("pass")

            evaluation = GateEvaluator(judge=judge).evaluate(
                session=session,
                policy=registry.get("Acceptance"),
                contract=contract,
                result=result,
                original_request_summary="Restore figma",
                approved_prd_summary="Match frame",
                approved_acceptance_matrix=[],
            )

        self.assertEqual(evaluation.decision.outcome, "pass")
        self.assertEqual(evaluation.decision.judge_verdict, "pass")
        self.assertEqual(len(judge.calls), 1)

    def test_hard_gate_failure_returns_rework_without_calling_judge(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from agent_team.gate_evaluator import GateEvaluator
        from agent_team.models import StageResultEnvelope
        from agent_team.stage_policies import default_policy_registry
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("restore figma")
            registry = default_policy_registry()
            contract = registry.build_contract(
                session_id=session.session_id,
                stage="Dev",
                contract_id="contract-dev",
                input_artifacts={},
            )
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Dev",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
                contract_id="contract-dev",
                evidence=[],
            )
            judge = RecordingJudge("pass")

            evaluation = GateEvaluator(judge=judge).evaluate(
                session=session,
                policy=registry.get("Dev"),
                contract=contract,
                result=result,
                original_request_summary="Restore figma",
                approved_prd_summary="Match frame",
                approved_acceptance_matrix=[],
            )

        self.assertEqual(evaluation.decision.outcome, "rework")
        self.assertEqual(evaluation.decision.target_stage, "Dev")
        self.assertIn("self_verification", evaluation.decision.missing_evidence)
        self.assertEqual(judge.calls, [])

    def test_judge_rework_overrides_hard_gate_pass(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from agent_team.gate_evaluator import GateEvaluator
        from agent_team.models import EvidenceItem, StageResultEnvelope
        from agent_team.stage_policies import default_policy_registry
        from agent_team.state import StateStore

        with TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("restore figma")
            registry = default_policy_registry()
            contract = registry.build_contract(
                session_id=session.session_id,
                stage="QA",
                contract_id="contract-qa",
                input_artifacts={},
            )
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="QA",
                status="completed",
                artifact_name="qa_report.md",
                artifact_content="# QA\nNo obvious issue.\n",
                contract_id="contract-qa",
                evidence=[
                    EvidenceItem(
                        name="independent_verification",
                        kind="command",
                        summary="Tests passed.",
                        command="python3 -m unittest",
                        exit_code=0,
                    )
                ],
            )

            evaluation = GateEvaluator(judge=RecordingJudge("rework", target_stage="Dev")).evaluate(
                session=session,
                policy=registry.get("QA"),
                contract=contract,
                result=result,
                original_request_summary="Restore figma",
                approved_prd_summary="Match frame",
                approved_acceptance_matrix=[],
            )

        self.assertEqual(evaluation.decision.outcome, "rework")
        self.assertEqual(evaluation.decision.target_stage, "Dev")
        self.assertEqual(evaluation.decision.judge_verdict, "rework")


if __name__ == "__main__":
    unittest.main()
