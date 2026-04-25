import json
import sys
import types
import unittest


class OpenAISandboxJudgeTests(unittest.TestCase):
    def test_unavailable_runtime_without_injected_runner_reports_clear_hint(self) -> None:
        from ai_company.gate_evaluator import JudgeResult
        from ai_company.openai_sandbox_judge import OpenAISandboxJudge, OpenAISandboxJudgeUnavailable

        class EmptyContext:
            def to_dict(self):
                return {"stage": "Acceptance", "required_output_schema": "JudgeResult"}

        judge = OpenAISandboxJudge(model="test-model")

        with self.assertRaises(OpenAISandboxJudgeUnavailable) as raised:
            result = judge.judge(EmptyContext())
            self.assertIsInstance(result, JudgeResult)

        message = str(raised.exception)
        self.assertTrue(
            "openai-agents[docker]" in message or "Docker is not available" in message,
            msg=message,
        )

    def test_injected_runner_receives_read_only_prompt_and_parses_dict_result(self) -> None:
        from ai_company.openai_sandbox_judge import OpenAISandboxJudge

        calls = []

        def fake_runner(
            *,
            prompt,
            model,
            sandbox_backend,
            docker_image,
            api_key,
            base_url,
            proxy_url,
            user_agent,
            oa_header,
        ):
            calls.append(
                {
                    "prompt": prompt,
                    "model": model,
                    "sandbox_backend": sandbox_backend,
                    "docker_image": docker_image,
                    "api_key": api_key,
                    "base_url": base_url,
                    "proxy_url": proxy_url,
                    "user_agent": user_agent,
                    "oa_header": oa_header,
                }
            )
            return {
                "verdict": "rework",
                "target_stage": "Dev",
                "confidence": 0.87,
                "reasons": ["Missing visual diff evidence."],
                "missing_evidence": ["visual_diff_summary"],
                "trace_id": "trace-1",
            }

        class Context:
            def to_dict(self):
                return {
                    "stage": "Acceptance",
                    "required_output_schema": "JudgeResult",
                    "hard_gate_result": {"status": "PASSED"},
                }

        result = OpenAISandboxJudge(
            model="gpt-test",
            runner=fake_runner,
            docker_image="python:3.13-slim",
            api_key="sk-test",
            base_url="https://example.test/v1",
            proxy_url="http://127.0.0.1:7897",
            oa_header="oa-test",
        ).judge(Context())

        self.assertEqual(result.verdict, "rework")
        self.assertEqual(result.target_stage, "Dev")
        self.assertEqual(result.confidence, 0.87)
        self.assertEqual(result.missing_evidence, ["visual_diff_summary"])
        self.assertEqual(calls[0]["model"], "gpt-test")
        self.assertEqual(calls[0]["sandbox_backend"], "docker")
        self.assertEqual(calls[0]["docker_image"], "python:3.13-slim")
        self.assertEqual(calls[0]["api_key"], "sk-test")
        self.assertEqual(calls[0]["base_url"], "https://example.test/v1")
        self.assertEqual(calls[0]["proxy_url"], "http://127.0.0.1:7897")
        self.assertEqual(calls[0]["user_agent"], "AI-Team-Runtime/0.1")
        self.assertEqual(calls[0]["oa_header"], "oa-test")
        self.assertIn("read-only", calls[0]["prompt"])
        self.assertIn("JudgeResult", calls[0]["prompt"])
        self.assertIn('"hard_gate_result"', calls[0]["prompt"])

    def test_injected_runner_can_return_json_string(self) -> None:
        from ai_company.openai_sandbox_judge import OpenAISandboxJudge

        class Context:
            def to_dict(self):
                return {"stage": "QA", "required_output_schema": "JudgeResult"}

        def fake_runner(
            *,
            prompt,
            model,
            sandbox_backend,
            docker_image,
            api_key,
            base_url,
            proxy_url,
            user_agent,
            oa_header,
        ):
            return json.dumps({"verdict": "pass", "confidence": 1.0, "reasons": ["All criteria met."]})

        result = OpenAISandboxJudge(model="gpt-test", runner=fake_runner).judge(Context())

        self.assertEqual(result.verdict, "pass")
        self.assertEqual(result.reasons, ["All criteria met."])

    def test_parser_converts_finding_payloads(self) -> None:
        from ai_company.openai_sandbox_judge import parse_judge_result

        result = parse_judge_result(
            {
                "verdict": "rework",
                "confidence": 0.7,
                "reasons": ["Visual mismatch."],
                "findings": [
                    {
                        "source_stage": "Acceptance",
                        "target_stage": "Dev",
                        "issue": "CTA button is misaligned.",
                        "severity": "high",
                    }
                ],
            }
        )

        self.assertEqual(result.findings[0].source_stage, "Acceptance")
        self.assertEqual(result.findings[0].target_stage, "Dev")
        self.assertEqual(result.findings[0].issue, "CTA button is misaligned.")

    def test_invalid_verdict_is_rejected(self) -> None:
        from ai_company.openai_sandbox_judge import OpenAISandboxJudge

        class Context:
            def to_dict(self):
                return {"stage": "QA", "required_output_schema": "JudgeResult"}

        def fake_runner(
            *,
            prompt,
            model,
            sandbox_backend,
            docker_image,
            api_key,
            base_url,
            proxy_url,
            user_agent,
            oa_header,
        ):
            return {"verdict": "merge", "confidence": 1.0}

        with self.assertRaises(ValueError) as raised:
            OpenAISandboxJudge(model="gpt-test", runner=fake_runner).judge(Context())

        self.assertIn("Unsupported judge verdict", str(raised.exception))

    def test_sdk_runner_uses_official_docker_sandbox_run_config_shape(self) -> None:
        from ai_company.openai_sandbox_judge import _run_with_openai_agents_sdk

        calls = {}
        original_modules = dict(sys.modules)

        try:
            agents_module = types.ModuleType("agents")
            run_module = types.ModuleType("agents.run")
            sandbox_module = types.ModuleType("agents.sandbox")
            docker_module = types.ModuleType("agents.sandbox.sandboxes.docker")
            docker_pkg = types.ModuleType("docker")
            openai_module = types.ModuleType("openai")
            httpx_module = types.ModuleType("httpx")

            class Result:
                final_output = '{"verdict": "pass", "confidence": 1.0, "reasons": ["ok"]}'

            class Runner:
                @staticmethod
                def run_sync(agent, prompt, *, run_config):
                    calls["agent"] = agent
                    calls["prompt"] = prompt
                    calls["run_config"] = run_config
                    return Result()

            class RunConfig:
                def __init__(self, *, sandbox, model_provider=None, tracing_disabled=False):
                    self.sandbox = sandbox
                    self.model_provider = model_provider
                    self.tracing_disabled = tracing_disabled

            class SandboxAgent:
                def __init__(self, *, name, instructions, model):
                    self.name = name
                    self.instructions = instructions
                    self.model = model

            class SandboxRunConfig:
                def __init__(self, *, client, options):
                    self.client = client
                    self.options = options

            class DockerSandboxClient:
                def __init__(self, docker_client):
                    self.docker_client = docker_client

            class DockerSandboxClientOptions:
                def __init__(self, *, image):
                    self.image = image

            class OpenAIProvider:
                def __init__(self, *, api_key=None, base_url=None, openai_client=None):
                    self.api_key = api_key
                    self.base_url = base_url
                    self.openai_client = openai_client

            class AsyncOpenAI:
                def __init__(self, *, api_key=None, base_url=None, default_headers=None, http_client=None):
                    self.api_key = api_key
                    self.base_url = base_url
                    self.default_headers = default_headers or {}
                    self.http_client = http_client

            class AsyncClient:
                def __init__(self, *, headers=None, proxy=None, trust_env=True):
                    self.headers = headers or {}
                    self.proxy = proxy
                    self.trust_env = trust_env

            def docker_from_env():
                return "docker-client"

            agents_module.Runner = Runner
            agents_module.OpenAIProvider = OpenAIProvider
            run_module.RunConfig = RunConfig
            sandbox_module.SandboxAgent = SandboxAgent
            sandbox_module.SandboxRunConfig = SandboxRunConfig
            docker_module.DockerSandboxClient = DockerSandboxClient
            docker_module.DockerSandboxClientOptions = DockerSandboxClientOptions
            docker_pkg.from_env = docker_from_env
            openai_module.AsyncOpenAI = AsyncOpenAI
            httpx_module.AsyncClient = AsyncClient

            sys.modules["agents"] = agents_module
            sys.modules["agents.run"] = run_module
            sys.modules["agents.sandbox"] = sandbox_module
            sys.modules["agents.sandbox.sandboxes.docker"] = docker_module
            sys.modules["docker"] = docker_pkg
            sys.modules["openai"] = openai_module
            sys.modules["httpx"] = httpx_module

            output = _run_with_openai_agents_sdk(
                prompt="judge prompt",
                model="gpt-test",
                sandbox_backend="docker",
                docker_image="python:3.13-slim",
                api_key="sk-test",
                base_url="https://example.test/v1",
                proxy_url="http://127.0.0.1:7897",
                user_agent="AI-Team-Runtime/0.1",
                oa_header="oa-test",
            )

            self.assertEqual(output, Result.final_output)
            self.assertEqual(calls["agent"].model, "gpt-test")
            self.assertEqual(calls["run_config"].sandbox.client.docker_client, "docker-client")
            self.assertEqual(calls["run_config"].sandbox.options.image, "python:3.13-slim")
            self.assertEqual(calls["run_config"].model_provider.openai_client.api_key, "sk-test")
            self.assertEqual(calls["run_config"].model_provider.openai_client.base_url, "https://example.test/v1")
            self.assertEqual(
                calls["run_config"].model_provider.openai_client.default_headers["User-Agent"],
                "AI-Team-Runtime/0.1",
            )
            self.assertEqual(
                calls["run_config"].model_provider.openai_client.default_headers["oa"],
                "oa-test",
            )
            self.assertEqual(
                calls["run_config"].model_provider.openai_client.http_client.proxy,
                "http://127.0.0.1:7897",
            )
            self.assertTrue(calls["run_config"].model_provider.openai_client.http_client.trust_env)
            self.assertTrue(calls["run_config"].tracing_disabled)
        finally:
            sys.modules.clear()
            sys.modules.update(original_modules)


if __name__ == "__main__":
    unittest.main()
