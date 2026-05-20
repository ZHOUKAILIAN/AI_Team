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
        from agent_team.gatekeeper import Gatekeeper
        from agent_team.models import StageContract, StageResultEnvelope
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Implementation",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
                contract_id="contract-implementation",
                evidence=[],
            )
            contract = StageContract(
                session_id=session.session_id,
                stage="Implementation",
                contract_id="contract-implementation",
                goal="Implement",
                required_outputs=["implementation.md"],
                evidence_requirements=["self_verification"],
            )

            gate = Gatekeeper().evaluate(session=session, contract=contract, result=result, acceptance_contract=None)

            self.assertEqual(gate.status, "FAILED")
            self.assertIn("self_verification", gate.missing_evidence)

    def test_verification_findings_can_pass_stage_run_and_route_later(self) -> None:
        from agent_team.gatekeeper import Gatekeeper
        from agent_team.models import Finding, StageContract, StageResultEnvelope
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Verification",
                status="failed",
                artifact_name="verification-report.md",
                artifact_content="# Verification\nRegression found.\n",
                contract_id="contract-verification",
                evidence=[evidence("independent_verification", kind="command", summary="Verification reran verification.")],
                findings=[Finding(source_stage="Verification", target_stage="Implementation", issue="Regression found.")],
            )
            contract = StageContract(
                session_id=session.session_id,
                stage="Verification",
                contract_id="contract-verification",
                goal="Verify",
                required_outputs=["verification-report.md"],
                evidence_requirements=["independent_verification"],
            )

            gate = Gatekeeper().evaluate(session=session, contract=contract, result=result, acceptance_contract=None)

            self.assertEqual(gate.status, "PASSED")

    def test_worker_blocked_status_blocks_gate_without_advancing(self) -> None:
        from agent_team.gatekeeper import Gatekeeper
        from agent_team.models import StageContract, StageResultEnvelope
        from agent_team.state import StateStore

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
        from agent_team.gatekeeper import Gatekeeper
        from agent_team.models import EvidenceRequirement, StageContract, StageResultEnvelope
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Implementation",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
                contract_id="contract-implementation",
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
                stage="Implementation",
                contract_id="contract-implementation",
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
        from agent_team.gatekeeper import Gatekeeper
        from agent_team.models import EvidenceRequirement, StageContract, StageResultEnvelope
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Implementation",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
                contract_id="contract-implementation",
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
                stage="Implementation",
                contract_id="contract-implementation",
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

    def test_evidence_by_name_normalizes_to_exact_contract_key(self) -> None:
        from agent_team.gatekeeper import Gatekeeper
        from agent_team.models import EvidenceRequirement, StageContract, StageResultEnvelope
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope.from_dict(
                {
                    "session_id": session.session_id,
                    "stage": "Implementation",
                    "status": "completed",
                    "artifact_name": "implementation.md",
                    "artifact_content": "# Implementation\n",
                    "contract_id": "contract-implementation",
                    "evidence_by_name": {
                        "self_verification": {
                            "kind": "command",
                            "summary": "Semantic checks passed.",
                            "command": "python scripts/check.py",
                            "exit_code": 0,
                        }
                    },
                }
            )
            contract = StageContract(
                session_id=session.session_id,
                stage="Implementation",
                contract_id="contract-implementation",
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

            self.assertEqual([item.name for item in result.evidence], ["self_verification"])
            self.assertEqual(gate.status, "PASSED")

    def test_structured_sub_evidence_name_does_not_satisfy_parent_requirement(self) -> None:
        from agent_team.gatekeeper import Gatekeeper
        from agent_team.models import EvidenceRequirement, StageContract, StageResultEnvelope
        from agent_team.state import StateStore

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            store = StateStore(Path(temp_dir))
            session = store.create_session("build an enforced workflow")
            result = StageResultEnvelope(
                session_id=session.session_id,
                stage="Implementation",
                status="completed",
                artifact_name="implementation.md",
                artifact_content="# Implementation\n",
                contract_id="contract-implementation",
                evidence=[
                    {
                        "name": "self_verification_semantics",
                        "kind": "command",
                        "summary": "Semantic checks passed.",
                        "command": "python scripts/check.py",
                        "exit_code": 0,
                    }
                ],
            )
            contract = StageContract(
                session_id=session.session_id,
                stage="Implementation",
                contract_id="contract-implementation",
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
            self.assertEqual(gate.missing_evidence, ["self_verification"])
            self.assertIn("derived key(s): self_verification_semantics", gate.reason)
            self.assertIn("use the exact required key", gate.reason)


if __name__ == "__main__":
    unittest.main()
