import unittest
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class RuntimeDriverSchemaTests(unittest.TestCase):
    def test_stage_result_schema_is_strict_for_codex_structured_output(self) -> None:
        from ai_company.runtime_driver import _stage_result_schema

        def assert_strict_objects(schema: dict[str, object], path: str) -> None:
            if schema.get("type") == "object":
                properties = schema.get("properties", {})
                required = schema.get("required", [])
                self.assertEqual(schema.get("additionalProperties"), False, path)
                self.assertEqual(set(required), set(properties), path)
                for name, child in properties.items():
                    if isinstance(child, dict):
                        assert_strict_objects(child, f"{path}.{name}")
            if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
                assert_strict_objects(schema["items"], f"{path}[]")

        assert_strict_objects(_stage_result_schema(), "$")


class RuntimeDriverTraceTests(unittest.TestCase):
    def test_dry_run_records_non_skippable_stage_trace(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ai_company",
                    "--repo-root",
                    str(repo_root),
                    "--state-root",
                    temp_dir,
                    "run-requirement",
                    "--message",
                    "执行这个需求：验证 runtime trace 不允许跳过链路步骤",
                    "--executor",
                    "dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            session_id = dict(
                line.split(": ", 1) for line in result.stdout.splitlines() if ": " in line
            )["session_id"]
            trace_path = Path(temp_dir) / session_id / "stage_runs" / "product-run-1_trace.json"
            trace = json.loads(trace_path.read_text())

        self.assertEqual(
            [step["step"] for step in trace["steps"]],
            [
                "contract_built",
                "execution_context_built",
                "stage_run_acquired",
                "executor_started",
                "executor_completed",
                "result_submitted",
                "gate_evaluated",
                "state_advanced",
            ],
        )
        self.assertTrue(all(step["status"] == "ok" for step in trace["steps"]))

    def test_runtime_trace_validator_blocks_missing_required_steps(self) -> None:
        from ai_company.runtime_driver import REQUIRED_PASS_TRACE_STEPS, _validate_runtime_trace

        trace = [{"step": step, "status": "ok"} for step in REQUIRED_PASS_TRACE_STEPS[:-1]]
        result = _validate_runtime_trace(trace, required_steps=REQUIRED_PASS_TRACE_STEPS)

        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("state_advanced", result.reason)


if __name__ == "__main__":
    unittest.main()
