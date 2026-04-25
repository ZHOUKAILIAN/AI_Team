from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .gate_evaluator import JudgeResult
from .models import Finding

SUPPORTED_VERDICTS = {"pass", "rework", "blocked", "needs_human"}
DEFAULT_OPENAI_USER_AGENT = "AI-Team-Runtime/0.1"


class OpenAISandboxJudgeUnavailable(RuntimeError):
    pass


class JudgeContextLike(Protocol):
    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError


SandboxRunner = Callable[..., dict[str, Any] | str | JudgeResult]


@dataclass(slots=True)
class OpenAISandboxJudge:
    model: str
    runner: SandboxRunner | None = None
    sandbox_backend: str = "docker"
    docker_image: str = "python:3.13-slim"
    api_key: str | None = None
    base_url: str | None = None
    proxy_url: str | None = None
    user_agent: str = DEFAULT_OPENAI_USER_AGENT
    oa_header: str | None = None
    instructions: str = (
        "You are an independent AI_Team judge. Review the compact context in a read-only way. "
        "Do not write files, do not change workflow state, do not run git commands, and do not "
        "claim completion outside the required JudgeResult schema."
    )

    def judge(self, context: JudgeContextLike) -> JudgeResult:
        prompt = build_judge_prompt(context=context, instructions=self.instructions)
        raw_result = self._run(prompt)
        return parse_judge_result(raw_result)

    def _run(self, prompt: str) -> dict[str, Any] | str | JudgeResult:
        if self.runner is not None:
            return self.runner(
                prompt=prompt,
                model=self.model,
                sandbox_backend=self.sandbox_backend,
                docker_image=self.docker_image,
                api_key=self.api_key,
                base_url=self.base_url,
                proxy_url=self.proxy_url,
                user_agent=self.user_agent,
                oa_header=self.oa_header,
            )
        return _run_with_openai_agents_sdk(
            prompt=prompt,
            model=self.model,
            sandbox_backend=self.sandbox_backend,
            docker_image=self.docker_image,
            api_key=self.api_key,
            base_url=self.base_url,
            proxy_url=self.proxy_url,
            user_agent=self.user_agent,
            oa_header=self.oa_header,
        )


def build_judge_prompt(*, context: JudgeContextLike, instructions: str) -> str:
    context_json = json.dumps(context.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
    schema_json = json.dumps(_judge_schema(), indent=2, sort_keys=True)
    return (
        f"{instructions}\n\n"
        "Return only valid JSON matching this JudgeResult schema. "
        "Allowed verdict values are pass, rework, blocked, needs_human.\n\n"
        "JudgeResult schema:\n"
        f"{schema_json}\n\n"
        "JudgeContextCompact:\n"
        f"{context_json}\n"
    )


def parse_judge_result(raw_result: dict[str, Any] | str | JudgeResult) -> JudgeResult:
    if isinstance(raw_result, JudgeResult):
        payload = {
            "verdict": raw_result.verdict,
            "target_stage": raw_result.target_stage,
            "confidence": raw_result.confidence,
            "reasons": raw_result.reasons,
            "missing_evidence": raw_result.missing_evidence,
            "findings": raw_result.findings,
            "trace_id": raw_result.trace_id,
        }
    elif isinstance(raw_result, str):
        payload = json.loads(_strip_json_fence(raw_result))
    else:
        payload = dict(raw_result)

    verdict = str(payload.get("verdict", "")).strip().lower()
    if verdict not in SUPPORTED_VERDICTS:
        raise ValueError(f"Unsupported judge verdict: {payload.get('verdict')}")

    return JudgeResult(
        verdict=verdict,
        target_stage=payload.get("target_stage") or None,
        confidence=float(payload.get("confidence", 0.0)),
        reasons=[str(item) for item in payload.get("reasons", [])],
        missing_evidence=[str(item) for item in payload.get("missing_evidence", [])],
        findings=[Finding.from_dict(item) for item in payload.get("findings", [])],
        trace_id=str(payload.get("trace_id", "")),
    )


def _strip_json_fence(value: str) -> str:
    stripped = value.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _judge_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["verdict", "confidence", "reasons"],
        "properties": {
            "verdict": {"enum": sorted(SUPPORTED_VERDICTS)},
            "target_stage": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "reasons": {"type": "array", "items": {"type": "string"}},
            "missing_evidence": {"type": "array", "items": {"type": "string"}},
            "findings": {"type": "array", "items": {"type": "object"}},
            "trace_id": {"type": "string"},
        },
    }


def _run_with_openai_agents_sdk(
    *,
    prompt: str,
    model: str,
    sandbox_backend: str,
    docker_image: str,
    api_key: str | None = None,
    base_url: str | None = None,
    proxy_url: str | None = None,
    user_agent: str = DEFAULT_OPENAI_USER_AGENT,
    oa_header: str | None = None,
) -> str:
    try:
        from agents import OpenAIProvider, Runner
        from agents.run import RunConfig
        from agents.sandbox import SandboxAgent, SandboxRunConfig
        from openai import AsyncOpenAI
        import httpx
    except ModuleNotFoundError as exc:
        raise OpenAISandboxJudgeUnavailable(
            "OpenAI Agents SDK sandbox support is not installed. "
            "Install with `pip install 'openai-agents[docker]'` for DockerSandboxClient support."
        ) from exc

    sandbox_run_config = None
    if sandbox_backend == "docker":
        try:
            from docker import from_env as docker_from_env
            from agents.sandbox.sandboxes.docker import DockerSandboxClient, DockerSandboxClientOptions
        except ModuleNotFoundError as exc:
            raise OpenAISandboxJudgeUnavailable(
                "Docker sandbox support is not installed. "
                "Install with `pip install 'openai-agents[docker]'`."
            ) from exc
        try:
            sandbox_run_config = SandboxRunConfig(
                client=DockerSandboxClient(docker_from_env()),
                options=DockerSandboxClientOptions(image=docker_image),
            )
        except Exception as exc:
            raise OpenAISandboxJudgeUnavailable(
                "Docker is not available for OpenAI sandbox judging. "
                "Start Docker Desktop or use a different sandbox backend."
            ) from exc
    elif sandbox_backend != "none":
        raise ValueError(f"Unsupported sandbox backend: {sandbox_backend}")

    agent = SandboxAgent(
        name="AI_Team Independent Judge",
        instructions="Return only a structured JudgeResult JSON object.",
        model=model,
    )
    client_headers = {"User-Agent": user_agent}
    if oa_header:
        client_headers["oa"] = oa_header
    openai_client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers=client_headers,
        http_client=httpx.AsyncClient(
            proxy=proxy_url,
            trust_env=True,
        ),
    )
    result = Runner.run_sync(
        agent,
        prompt,
        run_config=RunConfig(
            sandbox=sandbox_run_config,
            model_provider=OpenAIProvider(openai_client=openai_client),
            tracing_disabled=True,
        ),
    )
    return getattr(result, "final_output", result)
