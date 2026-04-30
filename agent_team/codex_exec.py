from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


RunCallable = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(slots=True)
class CodexExecConfig:
    repo_root: Path
    codex_bin: str = "codex"
    output_last_message: Path | None = None
    model: str = ""
    sandbox: str = "workspace-write"
    approval: str = "never"
    profile: str = ""

    def build_command(self, prompt: str) -> list[str]:
        command = [
            self.codex_bin,
            "exec",
            "--cd",
            str(self.repo_root),
            "--json",
        ]
        if self.output_last_message is not None:
            command.extend(["--output-last-message", str(self.output_last_message)])
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


@dataclass(slots=True)
class CodexExecResult:
    returncode: int
    stdout: str
    stderr: str
    last_message: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


class CodexExecRunner:
    def __init__(self, *, run: RunCallable | None = None) -> None:
        self._run = run or subprocess.run

    def run(self, config: CodexExecConfig, prompt: str) -> CodexExecResult:
        command = config.build_command(prompt)
        result = self._run(command, capture_output=True, text=True, check=False)
        last_message = ""
        if config.output_last_message is not None and config.output_last_message.exists():
            last_message = config.output_last_message.read_text()
        return CodexExecResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            last_message=last_message,
        )
