from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from .codex_isolation import isolated_codex_env


RunCallable = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(slots=True)
class ExecutorResult:
    returncode: int
    stdout: str
    stderr: str
    last_message: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


@runtime_checkable
class StageExecutor(Protocol):
    def execute(
        self,
        *,
        prompt: str,
        output_dir: Path,
        stage: str,
    ) -> ExecutorResult:
        """Run a stage prompt and return the model's structured JSON output."""
        ...


def _ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class CodexExecutor:
    repo_root: Path
    codex_bin: str = "codex"
    model: str = ""
    sandbox: str = "workspace-write"
    approval: str = "never"
    profile: str = ""
    isolate_home: bool = True
    ignore_rules: bool = True
    disable_plugins: bool = True
    ephemeral: bool = True
    run: RunCallable = subprocess.run

    def build_command(self, *, prompt: str, output_path: Path) -> list[str]:
        command = [
            self.codex_bin,
            "exec",
            "--cd",
            str(self.repo_root),
            "--json",
            "--output-last-message",
            str(output_path),
        ]
        if self.ignore_rules:
            command.append("--ignore-rules")
        if self.disable_plugins:
            command.extend(["--disable", "plugins"])
        if self.ephemeral:
            command.append("--ephemeral")
        if self.model:
            command.extend(["--model", self.model])
        if self.sandbox:
            command.extend(["--sandbox", self.sandbox])
        if self.approval:
            command.extend(["-c", f'approval_policy="{self.approval}"'])
        if self.profile:
            command.extend(["--profile", self.profile])
        command.append(prompt)
        return command

    def execute(self, *, prompt: str, output_dir: Path, stage: str) -> ExecutorResult:
        _ensure_output_dir(output_dir)
        output_path = output_dir / f"{stage.lower()}_last_message.json"
        (output_dir / f"{stage.lower()}_prompt.md").write_text(prompt)
        command = self.build_command(prompt=prompt, output_path=output_path)
        if self.isolate_home:
            with isolated_codex_env() as env:
                result = self.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    env=env,
                    stdin=subprocess.DEVNULL,
                )
        else:
            result = self.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        last_message = output_path.read_text() if output_path.exists() else ""
        return ExecutorResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            last_message=last_message,
        )


@dataclass(slots=True)
class ClaudeCodeExecutor:
    claude_bin: str = "claude"
    model: str = ""
    allowed_tools: list[str] = field(default_factory=lambda: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"])
    run: RunCallable = subprocess.run

    def build_command(self, *, prompt: str) -> list[str]:
        command = [
            self.claude_bin,
            "--print",
            "--output-format",
            "json",
            "--allowedTools",
            ",".join(self.allowed_tools),
        ]
        if self.model:
            command.extend(["--model", self.model])
        command.append(prompt)
        return command

    def execute(self, *, prompt: str, output_dir: Path, stage: str) -> ExecutorResult:
        _ensure_output_dir(output_dir)
        output_path = output_dir / f"{stage.lower()}_last_message.txt"
        (output_dir / f"{stage.lower()}_prompt.md").write_text(prompt)
        result = self.run(
            self.build_command(prompt=prompt),
            capture_output=True,
            text=True,
            check=False,
        )
        last_message = _extract_last_message(result.stdout)
        output_path.write_text(last_message or result.stdout)
        return ExecutorResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            last_message=last_message,
        )


def _extract_last_message(stdout: str) -> str:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout.strip()

    if isinstance(payload, list) and payload:
        return _message_text(payload[-1])
    if isinstance(payload, dict):
        return _message_text(payload)
    return stdout.strip()


def _message_text(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""

    for key in ("result", "content", "text", "message"):
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested = _message_text(value)
            if nested:
                return nested
        if isinstance(value, list):
            parts = [_message_text(item) for item in value]
            return "\n".join(part for part in parts if part)
    return ""
