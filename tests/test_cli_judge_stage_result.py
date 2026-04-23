import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


def evidence(name: str, *, kind: str = "artifact", summary: str = "Evidence provided.") -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "kind": kind,
        "summary": summary,
    }
    if kind == "command":
        payload["command"] = "python3 -m unittest"
        payload["exit_code"] = 0
    return payload


class JudgeStageResultCliTests(unittest.TestCase):
    def test_judge_stage_result_noop_outputs_context_and_decision_json(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            start = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个支持 sandbox judge 的验收流转",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(start.returncode, 0)
            session_id = dict(
                line.split(": ", 1) for line in start.stdout.splitlines() if ": " in line
            )["session_id"]

            acquire = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "acquire-stage-run",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(acquire.returncode, 0)
            run_id = dict(
                line.split(": ", 1) for line in acquire.stdout.splitlines() if ": " in line
            )["run_id"]

            bundle_path = Path(temp_dir) / "acceptance_bundle.json"
            bundle_path.write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "stage": "Product",
                        "status": "completed",
                        "artifact_name": "prd.md",
                        "artifact_content": "# PRD\n\n## Acceptance Matrix\n| ID | Standard |\n| --- | --- |\n| AC-001 | Works |\n",
                        "contract_id": dict(
                            line.split(": ", 1) for line in acquire.stdout.splitlines() if ": " in line
                        )["contract_id"],
                        "evidence": [evidence("explicit_acceptance_criteria", summary="Acceptance criteria listed.")],
                    }
                )
            )

            submit = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "submit-stage-result",
                    "--session-id",
                    session_id,
                    "--bundle",
                    str(bundle_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(submit.returncode, 0)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "judge-stage-result",
                    "--session-id",
                    session_id,
                    "--run-id",
                    run_id,
                    "--judge",
                    "noop",
                    "--print-context",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["decision"]["outcome"], "pass")
        self.assertEqual(payload["decision"]["judge_verdict"], "pass")
        self.assertEqual(payload["judge_result"]["verdict"], "pass")
        self.assertEqual(payload["judge_context"]["stage"], "Product")
        self.assertEqual(payload["hard_gate_result"]["status"], "PASSED")

    def test_verify_stage_result_with_noop_judge_advances_and_prints_judge_decision(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            start = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个支持 judge verify 的流程",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(start.returncode, 0)
            session_id = dict(
                line.split(": ", 1) for line in start.stdout.splitlines() if ": " in line
            )["session_id"]

            contract = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "build-stage-contract",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(contract.returncode, 0)
            contract_payload = json.loads(contract.stdout)

            acquire = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "acquire-stage-run",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(acquire.returncode, 0)

            bundle_path = Path(temp_dir) / "product_bundle.json"
            bundle_path.write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "stage": "Product",
                        "status": "completed",
                        "artifact_name": "prd.md",
                        "artifact_content": "# PRD\n\n## Acceptance Criteria\n- Verify judge flow.\n",
                        "contract_id": contract_payload["contract_id"],
                        "evidence": [evidence("explicit_acceptance_criteria", summary="Acceptance criteria listed.")],
                    }
                )
            )

            submit = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "submit-stage-result",
                    "--session-id",
                    session_id,
                    "--bundle",
                    str(bundle_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(submit.returncode, 0)

            verify = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "verify-stage-result",
                    "--session-id",
                    session_id,
                    "--judge",
                    "noop",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(verify.returncode, 0)
        self.assertIn("gate_status: PASSED", verify.stdout)
        self.assertIn("judge_verdict: pass", verify.stdout)
        self.assertIn("decision_outcome: pass", verify.stdout)
        self.assertIn("current_state: WaitForCEOApproval", verify.stdout)

    def test_verify_stage_result_with_unavailable_openai_sandbox_fails_closed(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            start = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "start-session",
                    "--message",
                    "执行这个需求：做一个支持 sandbox judge 的 fail-closed 流程",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(start.returncode, 0)
            session_id = dict(
                line.split(": ", 1) for line in start.stdout.splitlines() if ": " in line
            )["session_id"]

            contract = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "build-stage-contract",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(contract.returncode, 0)
            contract_payload = json.loads(contract.stdout)

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "acquire-stage-run",
                    "--session-id",
                    session_id,
                    "--stage",
                    "Product",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            bundle_path = Path(temp_dir) / "product_bundle.json"
            bundle_path.write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "stage": "Product",
                        "status": "completed",
                        "artifact_name": "prd.md",
                        "artifact_content": "# PRD\n\n## Acceptance Criteria\n- Verify judge flow.\n",
                        "contract_id": contract_payload["contract_id"],
                        "evidence": [evidence("explicit_acceptance_criteria", summary="Acceptance criteria listed.")],
                    }
                )
            )

            submit = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "submit-stage-result",
                    "--session-id",
                    session_id,
                    "--bundle",
                    str(bundle_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(submit.returncode, 0)

            verify = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "verify-stage-result",
                    "--session-id",
                    session_id,
                    "--judge",
                    "openai-sandbox",
                    "--openai-api-key",
                    "sk-secret-test",
                    "--openai-base-url",
                    "https://example.test/v1",
                    "--openai-proxy-url",
                    "http://127.0.0.1:7897",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            step = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "step",
                    "--session-id",
                    session_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(verify.returncode, 0)
        self.assertTrue(
            "openai-agents[docker]" in verify.stderr or "Docker is not available" in verify.stderr,
            msg=verify.stderr,
        )
        self.assertNotIn("sk-secret-test", verify.stdout)
        self.assertNotIn("sk-secret-test", verify.stderr)
        self.assertIn("next_action: verify-stage-result", step.stdout)


if __name__ == "__main__":
    unittest.main()
