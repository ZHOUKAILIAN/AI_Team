import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


def evidence(name: str, *, kind: str = "report", summary: str = "Evidence provided.") -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "kind": kind,
        "summary": summary,
    }
    if kind == "command":
        payload["command"] = "python -m unittest"
        payload["exit_code"] = 0
    return payload


class GatekeeperTests(unittest.TestCase):
    def test_missing_required_evidence_fails_gate(self) -> None:
        from ai_company.gatekeeper import Gatekeeper
        from ai_company.models import StageContract, StageResultEnvelope
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Dev",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
                contract_id="contract-dev",
                evidence=[],
            )
            contract = StageContract(
                session_id=session.session_id,
                stage="Dev",
                contract_id="contract-dev",
                goal="Implement",
                required_outputs=["implementation.md"],
                evidence_requirements=["self_verification"],
            )

            gate = Gatekeeper().evaluate(session=session, contract=contract, result=result, acceptance_contract=None)

            self.assertEqual(gate.status, "FAILED")
            self.assertIn("self_verification", gate.missing_evidence)

    def test_qa_findings_can_pass_stage_run_and_route_later(self) -> None:
        from ai_company.gatekeeper import Gatekeeper
        from ai_company.models import Finding, StageContract, StageResultEnvelope
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="QA",
                status="failed",
                artifact_name="qa_report.md",
                artifact_content="# QA\nRegression found.\n",
                contract_id="contract-qa",
                evidence=[evidence("independent_verification", kind="command", summary="QA reran verification.")],
                findings=[Finding(source_stage="QA", target_stage="Dev", issue="Regression found.")],
            )
            contract = StageContract(
                session_id=session.session_id,
                stage="QA",
                contract_id="contract-qa",
                goal="Verify",
                required_outputs=["qa_report.md"],
                evidence_requirements=["independent_verification"],
            )

            gate = Gatekeeper().evaluate(session=session, contract=contract, result=result, acceptance_contract=None)

            self.assertEqual(gate.status, "PASSED")

    def test_worker_blocked_status_blocks_gate_without_advancing(self) -> None:
        from ai_company.gatekeeper import Gatekeeper
        from ai_company.models import StageContract, StageResultEnvelope
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Acceptance",
                status="blocked",
                artifact_name="acceptance_report.md",
                artifact_content="# Acceptance\nCannot verify external tool.\n",
                contract_id="contract-acceptance",
                evidence=[evidence("product_level_validation", summary="Acceptance review could not proceed.")],
                blocked_reason="External tool unavailable.",
            )
            contract = StageContract(
                session_id=session.session_id,
                stage="Acceptance",
                contract_id="contract-acceptance",
                goal="Accept",
                required_outputs=["acceptance_report.md"],
                evidence_requirements=["product_level_validation"],
            )

            gate = Gatekeeper().evaluate(session=session, contract=contract, result=result, acceptance_contract=None)

            self.assertEqual(gate.status, "BLOCKED")
            self.assertIn("External tool unavailable", gate.reason)

    def test_structured_evidence_missing_required_summary_fails_gate(self) -> None:
        from ai_company.gatekeeper import Gatekeeper
        from ai_company.models import EvidenceRequirement, StageContract, StageResultEnvelope
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Dev",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
                contract_id="contract-dev",
                evidence=[
                    {
                        "name": "self_verification",
                        "kind": "command",
                        "command": "python -m unittest",
                        "exit_code": 0,
                    }
                ],
            )
            contract = StageContract(
                session_id=session.session_id,
                stage="Dev",
                contract_id="contract-dev",
                goal="Implement",
                required_outputs=["implementation.md"],
                evidence_requirements=["self_verification"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="self_verification",
                        allowed_kinds=["command", "artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
            )

            gate = Gatekeeper().evaluate(session=session, contract=contract, result=result, acceptance_contract=None)

            self.assertEqual(gate.status, "FAILED")
            self.assertIn("self_verification.summary", gate.missing_evidence)

    def test_structured_command_evidence_passes_gate(self) -> None:
        from ai_company.gatekeeper import Gatekeeper
        from ai_company.models import EvidenceRequirement, StageContract, StageResultEnvelope
        from ai_company.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Dev",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
                contract_id="contract-dev",
                evidence=[
                    {
                        "name": "self_verification",
                        "kind": "command",
                        "summary": "Unit tests passed.",
                        "command": "python -m unittest",
                        "exit_code": 0,
                    }
                ],
            )
            contract = StageContract(
                session_id=session.session_id,
                stage="Dev",
                contract_id="contract-dev",
                goal="Implement",
                required_outputs=["implementation.md"],
                evidence_requirements=["self_verification"],
                evidence_specs=[
                    EvidenceRequirement(
                        name="self_verification",
                        allowed_kinds=["command", "artifact", "report"],
                        required_fields=["summary"],
                    )
                ],
            )

            gate = Gatekeeper().evaluate(session=session, contract=contract, result=result, acceptance_contract=None)

            self.assertEqual(gate.status, "PASSED")


if __name__ == "__main__":
    unittest.main()
