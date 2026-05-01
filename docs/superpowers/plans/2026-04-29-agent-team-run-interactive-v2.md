# Agent Team Run Interactive — 更新版实现计划 (v2)

> 基于 `2026-04-29-agent-team-run-interactive.md` 叠加两种交互模式、Phase 1/2 拆分、子Agent 决策点、沙箱提示词、claude-code 提示词模式。

**核心理念变更：**

| v1 (原0429计划) | v2 (本计划) |
|---|---|
| 单一 `run-interactive` 命令 | 人类 `dev` 命令 + AI `acquire→submit→verify` 路径 |
| 一个 alignment 步骤 | Phase 1 需求对齐 + Phase 2 技术方案 |
| 无权限区分 | `initiator: human|agent` + 权限检查 |
| 通用 stage 提示词 | Dev/QA/Acceptance 各自专用提示词 + 空沙箱 |
| 无子Agent 决策 | Phase 2 后的 y/m/q 决策点 |

---

## 两种交互模式

```
                    ┌─ AI/Agent 模式 ─────────────────────┐
                    │  AI 调用 acquire/submit/verify       │
                    │  AI 不能调用 record-human-decision   │
                    │  AI 不能直接改状态机                  │
                    │                                       │
  agent-team ──────────┤                                       ├── 状态机（唯一权威）
                    │                                       │
                    └─ 人类交互模式 ───────────────────────┘
                       agent-team dev
                       Phase 1 需求对齐 → Phase 2 技术方案
                       → 决策点 → Agent 链执行
```

### AI/Agent 模式 — 现有流程保持不变

```bash
agent-team start-session --initiator agent --message "..."
agent-team acquire-stage-run --session-id xxx --stage Dev --worker codex
# AI 执行工作...
agent-team submit-stage-result --session-id xxx --bundle result.json
agent-team verify-stage-result --session-id xxx
# 碰到 WaitForCEOApproval 或 WaitForHumanDecision 就停住
# AI 不能自己 go——需要人类介入 record-human-decision
```

### 人类交互模式 — 新命令 `agent-team dev`

```text
$ agent-team dev

Phase 1: 需求对齐
├─ "你想做什么？"
├─ codex exec → 需求理解 + scope + 验收标准
├─ 展示 → [y]确认 [e]修改 [q]退出
└─ → confirmed_alignment.json

Phase 2: 技术方案
├─ codex exec → 分析代码库 → 技术方案
├─ 展示技术选型、影响范围、实现步骤、风险
├─ [y]确认 [e]修改 [q]退出
└─ → technical_plan.json

决策点
├─ "是否委托 Agent 执行？"
├─ [y] 启动 Dev/QA/Acceptance Agent 链
├─ [m] 手动执行（跳过 agent，人类提交结果）
└─ [q] 退出，保留 session

Phase 3: Agent 链执行 (选 y 时)
├─ start-session --initiator human
├─ Product Agent → prd.md
├─ auto go (CEO approval——人类已在 Phase 1+2 确认)
├─ Dev Agent (workspace sandbox) → 写代码
├─ QA Agent (clean sandbox) → 独立验证
│   └─ 不通过 → rework 回 Dev
├─ Acceptance Agent (clean sandbox) → 最终裁决
└─ 停在 WaitForHumanDecision → "Go / No-Go / Rework?"
```

---

## 权限边界

### session.json 结构

```json
{
  "session_id": "...",
  "initiator": "human",
  ...
}
```

### start-session 增加 --initiator

```python
start_session_parser.add_argument(
    "--initiator", choices=["human", "agent"], default="agent",
    help="Who initiated this session."
)
```

### record-human-decision 拦截

```python
def _handle_record_human_decision(args):
    store = StateStore(args.state_root)
    session = store.load_session(args.session_id)
    if session.initiator == "agent":
        raise SystemExit(
            "Human decisions are reserved for human-initiated sessions. "
            "Agent sessions must wait for a human operator to intervene."
        )
    # ... 原有逻辑
```

### AI 模式 session 的 Wait 状态处理

AI 发起的 session 走到 `WaitForCEOApproval` 或 `WaitForHumanDecision` 时：
- `step` 命令输出 `next_action: wait-for-human`
- `panel` 面板显示 `status: blocked, reason: "Waiting for human decision"`
- 人类用 `agent-team record-human-decision --session-id xxx --decision go` 介入

---

## 文件结构 (相比 v1 的增量)

```
agent_team/
  alignment.py        ← v1 保留，Phase 1 用
  tech_plan.py         ← 新增，Phase 2 用
  codex_exec.py       ← v1 保留
  stage_harness.py    ← v1 保留，增加按 stage 分支的沙箱提示词
  interactive.py      ← v1 改造，三阶段流程 + 决策点
  cli.py              ← 新增 dev 命令 + initiator 参数

tests/
  test_alignment.py   ← v1 保留
  test_tech_plan.py    ← 新增
  test_codex_exec.py  ← v1 保留
  test_stage_harness.py ← v1 保留，增加 QA/Acceptance 提示词测试
  test_dev_command.py  ← 新增，端到端集成测试
```

---

## Task 0：Session initiator 字段

**文件：** `agent_team/models.py`, `agent_team/state.py`, `agent_team/cli.py`

- [ ] `Session` dataclass 加 `initiator: str = "agent"`
- [ ] `StateStore.create_session()` 接受 `initiator` 参数
- [ ] `start-session` CLI 加 `--initiator` 参数
- [ ] `record-human-decision` handler 加 agent session 拦截
- [ ] 测试：agent session 的 human decision 被拒绝

---

## Task 1：Alignment 模型和解析器 (v1 保留，微调)

**文件：** `agent_team/alignment.py`, `tests/test_alignment.py`

与 v1 Task 1 基本一致。微调：`alignment_prompt()` 中移除 scope 相关字段（scope 讨论移到 Phase 2），聚焦于需求理解和验收标准。

```python
@dataclass(slots=True)
class AlignmentDraft:
    requirement_understanding: list[str]
    acceptance_criteria: list[AlignmentCriterion]
    clarifying_questions: list[str]
    # scope 移到 TechPlanDraft
```

---

## Task 2：执行器抽象 (StageExecutor 协议 + Codex/Claude Code 实现)

**文件：** `agent_team/executor.py`, `tests/test_executor.py`

### 设计原则

- 协议只定义一个方法：`execute(prompt, output_dir, stage) → ExecutorResult`
- 每个实现只负责"把 prompt 交给对应 CLI，拿回 JSON 结果"
- 不关心 prompt 内容、不关心状态机、不关心 stage 语义
- 未来加新后端（Gemini CLI、本地模型等）只需加一个类，不碰其他文件

```
StageExecutor (Protocol)
  ├── CodexExecutor       codex exec --json --output-last-message ...
  ├── ClaudeCodeExecutor  claude --print --output-format json ...
  └── (future) GeminiExecutor, LocalModelExecutor, ...
```

### 数据模型

```python
# agent_team/executor.py

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class ExecutorResult:
    returncode: int
    stdout: str
    stderr: str
    last_message: str  # parsed JSON output from the model

    @property
    def success(self) -> bool:
        return self.returncode == 0


@runtime_checkable
class StageExecutor(Protocol):
    """Execute a stage prompt via an external AI CLI.

    Implementations are stateless: they receive a prompt, call a CLI,
    and return the model's structured JSON output.
    """

    def execute(
        self,
        *,
        prompt: str,
        output_dir: Path,
        stage: str,
    ) -> ExecutorResult:
        """Run the prompt and return the model's last-message JSON."""
        ...


def _ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
```

### CodexExecutor

```python
@dataclass(slots=True)
class CodexExecutor:
    """Execute prompts via `codex exec`."""

    codex_bin: str = "codex"
    model: str = ""
    sandbox: str = "workspace-write"
    approval: str = "never"
    profile: str = ""

    def execute(
        self,
        *,
        prompt: str,
        output_dir: Path,
        stage: str,
    ) -> ExecutorResult:
        _ensure_output_dir(output_dir)
        output_path = output_dir / f"{stage.lower()}_last_message.json"
        prompt_path = output_dir / f"{stage.lower()}_prompt.md"
        prompt_path.write_text(prompt)

        command = [
            self.codex_bin, "exec",
            "--json",
            "--output-last-message", str(output_path),
        ]
        if self.model:
            command.extend(["--model", self.model])
        if self.sandbox:
            command.extend(["--sandbox", self.sandbox])
        if self.approval:
            command.extend(["--ask-for-approval", self.approval])
        if self.profile:
            command.extend(["--profile", self.profile])
        command.append(prompt)

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        last_message = output_path.read_text() if output_path.exists() else ""
        return ExecutorResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            last_message=last_message,
        )
```

### ClaudeCodeExecutor

```python
@dataclass(slots=True)
class ClaudeCodeExecutor:
    """Execute prompts via Claude Code CLI.

    Uses `claude --print` for non-interactive execution.
    The --output-format json flag requests structured output.
    """

    claude_bin: str = "claude"
    model: str = ""
    allowed_tools: list[str] = field(default_factory=lambda: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"])

    def execute(
        self,
        *,
        prompt: str,
        output_dir: Path,
        stage: str,
    ) -> ExecutorResult:
        _ensure_output_dir(output_dir)
        output_path = output_dir / f"{stage.lower()}_last_message.txt"
        prompt_path = output_dir / f"{stage.lower()}_prompt.md"
        prompt_path.write_text(prompt)

        command = [
            self.claude_bin,
            "--print",
            "--output-format", "json",
            "--allowedTools", ",".join(self.allowed_tools),
        ]
        if self.model:
            command.extend(["--model", self.model])
        command.append(prompt)

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        # Claude Code outputs JSON to stdout, extract last message
        last_message = _extract_last_message(result.stdout)
        output_path.write_text(last_message or result.stdout)
        return ExecutorResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            last_message=last_message or "",
        )


def _extract_last_message(stdout: str) -> str:
    """Extract the final model response from Claude Code's JSON output."""
    try:
        messages = json.loads(stdout)
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                # Try common Claude Code output shapes
                for key in ("content", "text", "message"):
                    if key in last:
                        return str(last[key])
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    return stdout.strip()
```

### StageHarness 注入 Executor

```python
# agent_team/stage_harness.py

@dataclass(slots=True)
class StageHarness:
    repo_root: Path
    state_store: StateStore
    executor: StageExecutor  # ← 注入，不再硬编码 Codex

    def run_stage(self, session_id: str, stage: str) -> StageRunRecord:
        # ... acquire run, build context, build prompt ...
        result = self.executor.execute(
            prompt=prompt,
            output_dir=codex_dir,  # rename to exec_dir later
            stage=stage,
        )
        # ... parse bundle, submit, verify ...
```

### CLI 执行器选择

```bash
# 默认 Codex
agent-team dev

# 使用 Claude Code
agent-team dev --executor claude-code

# 按 stage 指定（高级用法）
agent-team dev --dev-executor codex --qa-executor claude-code
```

```python
# agent_team/cli.py

dev_parser.add_argument(
    "--executor", choices=["codex", "claude-code"], default="codex",
    help="AI executor for all stages.",
)
dev_parser.add_argument("--codex-bin", default="codex")
dev_parser.add_argument("--claude-bin", default="claude")

def _resolve_executor(args, stage: str) -> StageExecutor:
    """Resolve executor for a given stage, with per-stage override support."""
    executor_name = getattr(args, f"{stage.lower()}_executor", None) or args.executor
    if executor_name == "claude-code":
        return ClaudeCodeExecutor(claude_bin=args.claude_bin)
    return CodexExecutor(
        codex_bin=args.codex_bin,
        model=args.model,
        sandbox=args.sandbox,
        profile=args.profile,
    )
```

### 测试

```python
# tests/test_executor.py

class FakeExecutor:
    """Executor that returns pre-configured responses for testing."""
    def __init__(self, responses: dict[str, str]):
        self._responses = responses
        self.calls: list[tuple[str, str]] = []  # (stage, prompt)

    def execute(self, *, prompt, output_dir, stage) -> ExecutorResult:
        self.calls.append((stage, prompt))
        return ExecutorResult(0, "", "", self._responses.get(stage, "{}"))

    def satisfies(self, protocol: type) -> bool:
        return True  # duck-type compatible with StageExecutor


class ExecutorTests(unittest.TestCase):
    def test_codex_executor_builds_correct_command(self) -> None:
        executor = CodexExecutor(codex_bin="/usr/local/bin/codex", model="opus")
        # verify command structure without actually running
        ...

    def test_claude_code_executor_builds_correct_command(self) -> None:
        executor = ClaudeCodeExecutor(claude_bin="/opt/claude")
        ...

    def test_stage_harness_uses_injected_executor(self) -> None:
        fake = FakeExecutor({"Dev": '{"status": "passed", ...}'})
        harness = StageHarness(..., executor=fake)
        harness.run_stage("s1", "Dev")
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0][0], "Dev")

    def test_cli_resolves_executor_per_stage(self) -> None:
        ...
```

---

## Task 3：Tech Plan 模型和解析器 (新增)

**文件：** `agent_team/tech_plan.py`, `tests/test_tech_plan.py`

### 数据模型

```python
@dataclass(slots=True)
class TechPlanDraft:
    approach_summary: str
    affected_modules: list[str]
    dependencies: list[str]
    implementation_steps: list[str]
    risks: list[str]
    testing_strategy: str
    clarifying_questions: list[str]
```

### 技术方案 Prompt

```python
def tech_plan_prompt(
    *,
    repo_root: Path,
    confirmed_alignment: AlignmentDraft,
    repo_structure: str,
    previous_plan: str = "",
    user_revision: str = "",
) -> str:
    return "\n".join([
        "You are the Tech Lead role for Agent Team.",
        "Analyze the codebase and produce a concrete technical implementation plan.",
        "Return strict JSON only. Do not wrap it in markdown.",
        "",
        "Required JSON shape:",
        "{",
        '  "approach_summary": "Brief overview of the technical approach",',
        '  "affected_modules": ["src/auth/login.ts", "src/components/Profile.tsx"],',
        '  "dependencies": ["react@18", "zustand"],',
        '  "implementation_steps": ["1. Add auth hook", "2. Create login form component", ...],',
        '  "risks": ["Database migration may affect existing users"],',
        '  "testing_strategy": "Unit tests for auth hook, E2E for login flow",',
        '  "clarifying_questions": ["Should we support third-party OAuth?"]',
        "}",
        "",
        "Confirmed requirement:",
        json.dumps(confirmed_alignment.to_dict(), ensure_ascii=False, indent=2),
        "",
        "Repository structure:",
        repo_structure,
        "",
        "Constraints:",
        "- Prefer minimal changes over large refactors.",
        "- Consider existing patterns in the codebase.",
        "- Flag risks even if you think they are unlikely.",
        # claude-code 模式：包含自包含提示词的原则
        "",
        "---",
        "Your analysis will be reviewed by a human before any code is written.",
        "Be thorough and specific — vague plans lead to bad implementations.",
    ] + ([
        "", "Previous plan (for revision):", previous_plan,
    ] if previous_plan else []) + ([
        "", "User revision request:", user_revision,
    ] if user_revision else []))
```

---

## Task 4：Stage Harness (v1 改造——按 stage 分支的沙箱提示词)

**文件：** `agent_team/stage_harness.py`, `tests/test_stage_harness.py`

v1 的 `stage_prompt()` 是通用的。v2 改为按 stage 构建专用提示词，借鉴 claude-code 的 worker/verifier 提示词模式。

### Dev Agent 提示词

```
You are the Dev stage agent for Agent Team.
Given the task specification, implement the feature completely.
Don't gold-plate, but don't leave it half-done.

Sandbox: workspace-write — you have full access to the repository.

Input:
- Confirmed alignment: {alignment_json}
- Technical plan: {tech_plan_json}
- PRD: {prd_content}
- Stage contract: {contract_json}

== SCOPE ==
- Implement ONLY what the technical plan and acceptance criteria define.
  Do NOT add features, refactor unrelated code, or make "improvements"
  beyond what was asked.
- Do NOT add error handling, fallbacks, or validation for scenarios that
  can't happen. Trust internal code and framework guarantees.
- Do NOT create helpers, utilities, or abstractions for one-time operations.
  Three similar lines is better than a premature abstraction.
- Do NOT create documentation files beyond what the stage contract requires.

== SECURITY ==
- Prioritize writing safe, secure, and correct code.
- Be careful not to introduce security vulnerabilities such as command
  injection, XSS, SQL injection, and other OWASP top 10 vulnerabilities.
  If you notice that you wrote insecure code, immediately fix it.

== SELF-VERIFICATION ==
- Run tests and typecheck before reporting done.
- If tests fail, report the failure with output — do NOT suppress or
  simplify failures to make the result look clean.
- If you did not run a verification step, say so rather than implying
  it succeeded.
- Never claim "all tests pass" when output shows failures.
- Never characterize incomplete or broken work as done.

== OUTPUT ==
- Write implementation.md describing:
  - What was changed and why
  - Files modified (absolute paths)
  - Commands run and their actual output
  - Any limitations or known issues
- Report back with specific, actionable results — include file paths,
  commit hashes, and test run summaries.

== BOUNDARY ==
- You are a STAGE AGENT. You only have authority over the Dev stage.
- Do NOT attempt to advance the workflow state machine.
- Do NOT call record-human-decision or modify session state.
- Submit your stage result and stop. The runtime handles what comes next.
- Do NOT run destructive git operations (force push, hard reset,
  branch delete) unless explicitly instructed by the stage contract.

Output: StageResultEnvelope JSON with artifact_name "implementation.md".
```

### QA Agent 提示词 (空沙箱——核心变更)

```
You are the QA stage agent for Agent Team.

== CRITICAL: CLEAN SANDBOX ==
You are in a CLEAN sandbox. The Dev agent worked in a DIFFERENT sandbox
that you cannot access. You CANNOT see Dev's environment, Dev's node_modules,
or Dev's build artifacts. You only have the artifact files listed below.

Your job is to INDEPENDENTLY VERIFY the implementation.
Prove the code works — don't just confirm it exists.

Input:
- Confirmed alignment: {alignment_json}
- Technical plan: {tech_plan_json}
- PRD: {prd_content}
- Dev's implementation.md: {dev_implementation_md}
- Dev's changed files (full content): {dev_changed_files}
- Stage contract: {contract_json}

== VERIFICATION PROTOCOL ==
1. Reconstruct the implementation from scratch in this clean sandbox:
   - Apply Dev's changed files to a clean copy of the codebase
   - Install dependencies from scratch
   - Build from source
2. Run ALL tests independently:
   - Unit tests, integration tests, type checking, linting
   - Report the actual command and its output — not a summary
3. Verify EACH acceptance criterion:
   - Test the behavior, not just read the code
   - Try edge cases and error paths — don't just re-run the happy path
   - Do NOT assume Dev's self-assessment is correct
4. Security audit:
   - Check for command injection, XSS, SQL injection, path traversal
   - Check for hardcoded secrets, unsafe deserialization
   - Check for missing input validation at system boundaries
   - Flag any security concern even if you're not 100% sure
5. Regression check:
   - Verify nothing obvious is broken outside the changed area
   - Review common bug patterns (null checks, error handling, race conditions)

== INTEGRITY RULES ==
- Be skeptical — if something looks off, dig in.
- Investigate failures — don't dismiss any error as "unrelated" without
  concrete evidence proving it is unrelated.
- If you cannot reproduce Dev's results from scratch, mark it FAILED.
  Do not pass something just because Dev says it works.
- Never claim tests pass when output shows failures.
- Never suppress or simplify failing checks to manufacture a green result.
- Your qa_report.md MUST include the COMMANDS you ran and their OUTPUT.
  "Tests passed" without evidence is not acceptable.

== SCOPE ==
- Verify ONLY what the acceptance criteria define — don't audit for
  unrelated issues, but DO flag security problems you notice.
- Don't gold-plate the verification. Be thorough, not exhaustive.

== BOUNDARY ==
- You are a STAGE AGENT. You only have authority over the QA stage.
- Do NOT attempt to advance the workflow state machine.
- Do NOT call record-human-decision or modify session state.
- Submit your stage result and stop. The runtime handles what comes next.
- Do NOT modify the codebase — you verify, you don't fix.

Output: StageResultEnvelope JSON with artifact_name "qa_report.md"
and status "passed", "failed", or "blocked".
```

### Acceptance Agent 提示词 (空沙箱 + 全量纸面证据)

```
You are the Acceptance stage agent for Agent Team.

You are in a CLEAN sandbox. You cannot run the implementation.
You have the full paper trail: requirement → PRD → Dev → QA.
Your job is to make a FINAL recommendation: go or no-go.

Input:
- Original requirement: {raw_request}
- Confirmed alignment: {alignment_json}
- Technical plan: {tech_plan_json}
- PRD: {prd_content}
- Dev's implementation.md: {dev_implementation_md}
- QA's qa_report.md: {qa_report_content}
- Stage contract: {contract_json}

== ASSESSMENT DIMENSIONS ==
1. Requirement coverage:
   - Does the implementation satisfy every acceptance criterion?
   - Cross-reference PRD → Dev → QA for gaps.
2. Quality assessment:
   - Did QA find issues? What severity?
   - Are there unresolved concerns?
   - Did QA actually exercise edge cases or just rubber-stamp?
     If QA's report lacks concrete command output, flag it.
3. Security assessment:
   - Did QA flag any security issues? Were they addressed?
   - Review the paper trail for signs of unsafe patterns
     (command injection, XSS, missing input validation).
4. Risk assessment:
   - Signs of incomplete work, tech debt, or fragility
   - Areas that might break in production
   - What was explicitly marked as "out of scope"

== INTEGRITY RULES ==
- Don't rubber-stamp weak work just to finish the pipeline.
- If QA's evidence is thin, say so — do not fill the gap with assumptions.
- Cross-reference Dev's claims against QA's findings — flag discrepancies.
- Never claim "all criteria met" when some lack evidence.
- If you're uncertain, say so and explain why — don't fabricate confidence.

== OUTPUT ==
Produce acceptance_report.md with:
- Summary of what was built
- Per-criterion pass/fail/blocked table with evidence citations
- Security concerns (even if not blocking)
- Risk assessment with specific, named risks
- Recommendation: recommended_go | recommended_no_go | blocked
- Rationale — explain your reasoning so the human can trust or challenge it.
  Your rationale must reference specific evidence from the paper trail,
  not just general impressions.

== BOUNDARY ==
- You are a STAGE AGENT. You only have authority over the Acceptance stage.
- Do NOT attempt to advance the workflow state machine.
- Do NOT call record-human-decision or modify session state.
- You recommend go/no-go to the human — the human decides.
- Submit your stage result and stop. The runtime handles what comes next.

Output: StageResultEnvelope JSON with artifact_name "acceptance_report.md"
and acceptance_status set to your recommendation.
```

### 提示词分层架构

借鉴 claude-code 的分层设计（`getSimpleDoingTasksSection()` → `getActionsSection()` → … → `dynamicSections`），
agent 提示词按三层组装，每层是一个独立函数。层之间职责不重叠，修改时只改一层。

```
┌──────────────────────────────────────────────┐
│  Layer 1: 通用保护层 (universal_protection)  │  ← 所有 agent 相同，永不按 stage 变化
│  SCOPE + SECURITY + INTEGRITY + BOUNDARY     │
├──────────────────────────────────────────────┤
│  Layer 2: 角色指令层 (role_instruction)      │  ← 按 stage 分支，定义做什么、怎么做
│  Dev: implement + self-verify                │
│  QA:  reconstruct + verify + security audit  │
│  Acceptance: assess + cross-ref + recommend  │
├──────────────────────────────────────────────┤
│  Layer 3: 阶段上下文层 (stage_context)       │  ← 纯数据注入，无行为指令
│  alignment + tech_plan + PRD + artifacts...  │
│  StageResultEnvelope JSON schema             │
└──────────────────────────────────────────────┘
```

**设计原则**（参考 claude-code `prompts.ts` 的分段模式）：
- 每层是纯函数，返回字符串，不依赖全局状态
- Layer 1 永远不变且永远最先——确保 agent 在被指派具体任务前先戴上"紧箍咒"
- Layer 2 控制行为差异——通过 `if stage ==` 路由，不通过参数配置（避免分支蔓延）
- Layer 3 只注入数据——不包含 `Do NOT` 等行为约束
- 加新层时只在 `build_agent_prompt()` 的返回列表里加一行，不影响现有层

```python
# agent_team/stage_harness.py

def build_agent_prompt(
    *,
    stage: str,
    alignment: dict[str, Any],
    tech_plan: dict[str, Any],
    prd_content: str,
    dev_artifacts: DevArtifacts,
    qa_report: str,
    raw_request: str,
) -> str:
    """Assemble a stage agent prompt from configured layers.

    Layer order is load-bearing:
    - Universal protection MUST come first (sets constraints before role context)
    - Role instruction MUST come before stage context (agent needs to know HOW
      to use the data before seeing it)
    - Stage context is pure data and MUST come last (no behavioral rules)
    """
    layers = [
        _universal_protection_layer(),                    # Layer 1
        _role_instruction_layer(stage),                   # Layer 2
        _stage_context_layer(                             # Layer 3
            stage=stage,
            alignment=alignment,
            tech_plan=tech_plan,
            prd_content=prd_content,
            dev_artifacts=dev_artifacts,
            qa_report=qa_report,
            raw_request=raw_request,
        ),
    ]
    return "\n\n".join(layers)


# ── Layer 1: Universal Protection ──────────────────────────────

def _universal_protection_layer() -> str:
    """Protections applied to EVERY stage agent.

    This layer MUST NOT reference any specific stage, artifact, or task.
    It sets the outermost guardrails before any role context is loaded.

    When to edit this layer:
    - Adding a new universal constraint (e.g., "never access network")
    - Tightening integrity rules that apply to all agents
    - Adding compliance requirements (e.g., "never log PII")

    When NOT to edit this layer:
    - Role-specific behavior → edit _role_instruction_layer()
    - Input data format → edit _stage_context_layer()
    """
    return """== UNIVERSAL PROTECTION ==

You are a STAGE AGENT in the Agent Team workflow. These rules apply regardless
of which stage you are executing.

=== SCOPE ===
- Do ONLY what your stage defines. Do NOT add features, refactor unrelated
  code, or make "improvements" beyond what was asked.
- Do NOT add error handling, fallbacks, or validation for scenarios that
  can't happen. Trust internal code and framework guarantees.
- Do NOT create helpers, utilities, or abstractions for one-time operations.
  Three similar lines is better than a premature abstraction.
- Do NOT create documentation files beyond what the stage contract requires.

=== SECURITY ===
- Prioritize writing safe, secure, and correct code.
- Be careful not to introduce security vulnerabilities such as command
  injection, XSS, SQL injection, path traversal, hardcoded secrets,
  unsafe deserialization, and other OWASP top 10 vulnerabilities.
  If you notice that you wrote insecure code, immediately fix it.
- Check for missing input validation at system boundaries.

=== INTEGRITY ===
- Report outcomes faithfully. If tests fail, say so with the relevant output.
- If you did not run a verification step, say that rather than implying
  it succeeded.
- Never claim "all tests pass" when output shows failures.
- Never suppress or simplify failing checks to manufacture a green result.
- Never characterize incomplete or broken work as done.

=== BOUNDARY ===
- You are a STAGE AGENT. You only have authority over your assigned stage.
- Do NOT attempt to advance the workflow state machine.
- Do NOT call record-human-decision or modify session state.
- Submit your stage result and stop. The runtime handles what comes next.
- Do NOT run destructive git operations (force push, hard reset,
  branch delete) unless explicitly required by the stage contract.

=== OUTPUT FORMAT ===
- Report back with specific, actionable results.
- Include file paths (absolute), commands run, and their actual output.
- Use the StageResultEnvelope JSON format defined in your stage context."""


# ── Layer 2: Role Instruction ──────────────────────────────────

def _role_instruction_layer(stage: str) -> str:
    """Stage-specific behavioral instructions.

    This is where each stage's unique workflow lives: what to do, in what
    order, how to verify, what "done" means for this specific role.

    Layer 1 (universal protection) is already applied before this.
    Layer 3 (context data) comes after this.
    """
    if stage == "Dev":
        return _dev_instruction()
    elif stage == "QA":
        return _qa_instruction()
    elif stage == "Acceptance":
        return _acceptance_instruction()
    raise ValueError(f"Unknown stage: {stage}")


def _dev_instruction() -> str:
    return """== DEV ROLE ==

You are the Dev stage agent. Implement the feature according to the
technical plan and acceptance criteria in your stage context.

Sandbox: workspace-write — you have full access to the repository.

=== SELF-VERIFICATION ===
Before reporting done, run tests and typecheck. Report the actual
command output — not a summary.

=== OUTPUT ===
Write implementation.md describing:
- What was changed and why
- Files modified (absolute paths)
- Commands run and their output
- Any limitations or known issues"""


def _qa_instruction() -> str:
    return """== QA ROLE ==

CRITICAL: You are in a CLEAN sandbox. The Dev agent worked in a DIFFERENT
sandbox that you cannot access. You only have the artifact files in your
stage context. Your job is to INDEPENDENTLY VERIFY — prove the code works,
don't just confirm it exists.

=== VERIFICATION PROTOCOL ===
1. Reconstruct from scratch: apply Dev's changed files, install deps, build
2. Run ALL tests independently — report command + output
3. Verify EACH acceptance criterion — test behavior, try edge cases and
   error paths, do NOT assume Dev's self-assessment is correct
4. Security audit: command injection, XSS, SQL injection, path traversal,
   hardcoded secrets, unsafe deserialization, missing input validation.
   Flag any concern even if you're not 100% sure.
5. Regression check: verify nothing is broken outside the changed area

=== VERIFICATION INTEGRITY ===
- Be skeptical — if something looks off, dig in.
- Investigate failures — don't dismiss as "unrelated" without concrete proof.
- If you cannot reproduce Dev's results from scratch, mark it FAILED.
- Your qa_report.md MUST include COMMANDS you ran and their OUTPUT.
  "Tests passed" without evidence is not acceptable.
- Do NOT modify the codebase — you verify, you don't fix.

=== OUTPUT ===
Write qa_report.md with:
- Per-criterion: passed / failed / blocked, with concrete evidence
- Test run results (command + output)
- Security findings (even if non-blocking)
- Final verdict: passed | failed | blocked"""


def _acceptance_instruction() -> str:
    return """== ACCEPTANCE ROLE ==

You are in a CLEAN sandbox. You cannot run the implementation. You have
the full paper trail: requirement → PRD → Dev → QA. Your job is to make
a FINAL recommendation: go or no-go.

=== ASSESSMENT ===
1. Requirement coverage — does the implementation satisfy every criterion?
   Cross-reference PRD → Dev → QA for gaps.
2. Quality — did QA find issues? Did QA actually exercise edge cases or
   just rubber-stamp? If QA's report lacks concrete command output, flag it.
3. Security — did QA flag security issues? Were they addressed? Review the
   paper trail for unsafe patterns.
4. Risk — signs of incomplete work, tech debt, fragility. What would go
   wrong in production? What was explicitly out of scope?

=== RECOMMENDATION INTEGRITY ===
- Don't rubber-stamp weak work just to finish the pipeline.
- If QA's evidence is thin, say so — don't fill the gap with assumptions.
- Cross-reference Dev's claims against QA's findings — flag discrepancies.
- Never claim "all criteria met" when some lack evidence.
- If you're uncertain, say so and explain why — don't fabricate confidence.

=== OUTPUT ===
Write acceptance_report.md with:
- Summary of what was built
- Per-criterion pass/fail/blocked table with evidence citations
- Security concerns (even if not blocking)
- Risk assessment with specific, named risks
- Recommendation: recommended_go | recommended_no_go | blocked
- Rationale referencing specific evidence, not general impressions
- Remember: you recommend — the human decides."""


# ── Layer 3: Stage Context ─────────────────────────────────────

def _stage_context_layer(
    *,
    stage: str,
    alignment: dict[str, Any],
    tech_plan: dict[str, Any],
    prd_content: str,
    dev_artifacts: DevArtifacts,
    qa_report: str,
    raw_request: str,
) -> str:
    """Pure data injection. No behavioral rules — those belong in Layers 1-2.

    This layer provides the task-specific information the agent needs to
    do its job: requirements, plans, artifacts from prior stages, and the
    expected output format.

    When to add new data fields:
    - New artifact type from a prior stage (e.g., "design_review.md")
    - New input source (e.g., "performance_baseline.json")
    """
    parts = [
        "== STAGE CONTEXT ==",
        f"Stage: {stage}",
        "",
        "=== StageResultEnvelope JSON Schema ===",
        "{",
        '  "session_id": "<provided>",',
        '  "stage": "<provided>",',
        '  "contract_id": "<provided>",',
        '  "status": "passed|failed|blocked",',
        '  "summary": "<one-paragraph summary>",',
        '  "artifact_name": "<e.g. implementation.md>",',
        '  "artifact_content": "<full artifact text>",',
        '  "journal": "<Markdown journal of decisions and observations>",',
        '  "evidence": [{"name": "...", "kind": "report|log|screenshot", "summary": "..."}],',
        '  "findings": []',
        "}",
        "",
        "Return strict JSON only. Do NOT wrap in markdown.",
    ]
    if alignment:
        parts += [
            "",
            "=== Confirmed Alignment ===",
            json.dumps(alignment, ensure_ascii=False, indent=2),
        ]
    if tech_plan:
        parts += [
            "",
            "=== Technical Plan ===",
            json.dumps(tech_plan, ensure_ascii=False, indent=2),
        ]
    if raw_request:
        parts += [
            "",
            "=== Original Request ===",
            raw_request,
        ]
    if prd_content:
        parts += [
            "",
            "=== PRD ===",
            prd_content,
        ]
    if stage in ("QA", "Acceptance"):
        parts += [
            "",
            "=== Dev Implementation Report ===",
            dev_artifacts.implementation_md,
            "",
            "=== Dev Changed Files ===",
            dev_artifacts.changed_files,
        ]
    if stage == "Acceptance" and qa_report:
        parts += [
            "",
            "=== QA Report ===",
            qa_report,
        ]
    return "\n".join(parts)
```

### 分层对比：claude-code vs agent-team-runtime

```
claude-code prompts.ts                    agent-team-runtime stage_harness.py
──────────────────────────               ──────────────────────────────
getSimpleIntroSection()          ─┐
getSimpleSystemSection()          │
getSimpleDoingTasksSection()      ├─ Layer 1: _universal_protection_layer()
getActionsSection()               │   (SCOPE + SECURITY + INTEGRITY + BOUNDARY)
getUsingYourToolsSection()        │
getSimpleToneAndStyleSection()   ─┘
getOutputEfficiencySection()     ─── Layer 2: _role_instruction_layer()
                                      (Dev / QA / Acceptance 分支)
dynamicSections                  ─── Layer 3: _stage_context_layer()
  (env info, MCP, scratchpad...)      (alignment + tech_plan + artifacts...)
```

### 未来扩展口

当需要加新层时，只需在 `build_agent_prompt()` 的返回列表里加一行：

```python
# 未来示例：合规层（医疗/金融行业）
def _compliance_layer(industry: str) -> str:
    if industry == "healthcare":
        return "=== HIPAA COMPLIANCE ===\nNever log PHI. ..."
    return ""

# 未来示例：调试层（开发环境专用）
def _debug_layer(*, debug: bool) -> str:
    if not debug:
        return ""
    return "=== DEBUG MODE ===\nLog all tool calls to stderr. ..."
```

不需要改任何现有函数，不需要改 Layer 1/2/3。

---

## Task 4.5：技能系统 (Skill Registry + 偏好池 + 交互式选择)

**文件：** `agent_team/skill_registry.py`, `tests/test_skill_registry.py`

### 设计原则

```
初始状态：空，默认不使用任何 skill
首次使用：每个 stage 执行前，多选询问使用哪些 skill
偏好池：  记录上次选择，下次自动预选
日常使用：一行提示，不增加交互操作
修改入口：按 s 即时调整 / CLI --with-skills / 偏好池管理命令
```

参考 openclaw 的 `WizardPrompter` 交互模式（`multiselect`、`confirm`、`note`），目标是"第一次友好引导，之后不打搅"。

### 技能来源和发现

```
优先级从高到低：
1. 项目内建: <project>/<Stage>/skills/<skill-name>/SKILL.md
2. 个人技能库: $AGENT_TEAM_SKILL_PATH/<skill-name>/SKILL.md
3. 内建默认: agent_team/assets/skills/<skill-name>/SKILL.md

同名 skill 取高优先级的版本。
```

### 首次使用流程

Phase 2 技术方案确认后，进入技能选择：

```text
技术方案已确认:
- 涉及模块: 3 (src/auth, src/api, src/db)
- 风险: 低
- 预估实现: 中等

── 本次使用的技能 ──

  Dev 阶段可用的技能:
  [ ] plan                     (内置) 拆分实现步骤，输出实施计划
  [ ] refactor-checklist       (内置) 重构检查项
  [ ] ai-doc-driven-dev        (个人库) 文档驱动开发

  QA 阶段可用的技能:
  [ ] security-audit           (内置) 安全审计：OWASP、注入、密钥泄露
  [ ] cst                      (个人库) 客诉排查工作流

  Acceptance 阶段可用的技能:
  [ ] e2e-coverage-guard       (个人库) E2E 覆盖检查

  空格切换选择，回车确认。全空 = 裸跑，不选任何技能。
>
```

设计要点：
- 全空默认 —— 用户直接回车就是裸跑
- 来源标记清晰 —— `(内置)` / `(个人库)` 让用户知道信任边界
- 描述简短 —— 一行，不超过 60 字，足够决策

### 后续使用流程

有了偏好池后，skill 一行展示，不增加交互：

```text
技术方案已确认:
- 涉及模块: 3
- 风险: 低

技能: plan (Dev) · security-audit (QA) · e2e-coverage-guard (Acceptance)
按 [s] 修改  按 [Enter] 继续
>
```

"技能"行是只读展示——看完就知道挂载了哪些 skill，不需要每次重新选择。只有按 `s` 才进多选调整。

### 偏好池

```yaml
# .agent-team/skill-preferences.yaml
# 自动维护，用户也可以直接编辑

dev:
  last: [plan]                    # 上次选的，下次默认预选
  frequent:                       # 展示顺序：按次数降序
    plan: 7
    refactor-checklist: 2

qa:
  last: [security-audit]
  frequent:
    security-audit: 6

acceptance:
  last: [e2e-coverage-guard]
  frequent:
    e2e-coverage-guard: 5
```

- `last` 决定预选哪些。每次用户修改选择后更新
- `frequent` 决定多选列表里展示顺序——常用的排前面
- 纯自动维护，不需要管理命令。用户也可以直接编辑文件

### 多选时的展示排序

按 `frequent` 降序，同频次按来源（内置 → 个人库），同来源按字母序。常用 skill 自然浮到顶部。

### 技能注入到提示词

#### Prompt 注入（默认，80% 的 skill）

`skill_registry.py` 在 `build_agent_prompt()` 的 L2 和 L3 之间插入 L2.5：

```python
def build_agent_prompt(*, stage, skills, ...):
    layers = [
        _universal_protection_layer(),          # L1
        _role_instruction_layer(stage),          # L2
        _skill_injection_layer(skills),          # L2.5 ← 注入这里
        _stage_context_layer(...),               # L3
    ]
    return "\n\n".join(layers)

def _skill_injection_layer(skills: list[Skill]) -> str:
    """将选中的技能注入为提示词片段。只注入方法论内容，不注入脚本路径。"""
    if not skills:
        return ""
    parts = ["== ENABLED SKILLS =="]
    for skill in skills:
        parts.append(f"### {skill.name}")
        parts.append(skill.content)  # SKILL.md 正文（去掉 frontmatter）
        parts.append("")
    return "\n".join(parts)
```

#### Sandbox 安装（少数需要脚本/外部工具的 skill）

skill 的 frontmatter 声明 `delivery: sandbox`：

```markdown
---
name: cst
delivery: sandbox
sandbox_files:
  - assets/templates/
  - scripts/query-logs.sh
env_vars:
  - CST_LOG_ACCESS_METHOD
---

# Customer Service Troubleshooting
...
```

处理流程：

```
Phase 3 执行 stage
  → skill_registry 检测 delivery: sandbox
  → 复制 skill 目录到沙箱 .agent-team/skills/<name>/
  → 注入 env_vars 到沙箱环境
  → L2.5 注入激活指令（简短，不膨胀 prompt）：
    "cst skill 已安装到沙箱 .agent-team/skills/cst/
     环境变量 CST_LOG_ACCESS_METHOD 已配置"
  → executor 执行
```

多选时标记 `[需沙箱]` 或 `[需数据库连接]`，从 skill 的 `env_vars` 推断。

### CLI 直达

```bash
# 加 skill
agent-team dev --with-skills dev:plan,refactor-checklist --with-skills qa:cst

# 跳 skill
agent-team dev --skip-skills qa:security-audit

# 裸跑（全部空）
agent-team dev --skills-empty
```

这些都只影响当次执行，不修改偏好池。

### 管理命令

```bash
agent-team skill list                       # 列出所有可用技能
agent-team skill list --stage QA            # 按 stage 过滤
agent-team skill list --source personal     # 按来源过滤
agent-team skill show security-audit        # 预览 SKILL.md 内容

agent-team skill preferences                # 查看偏好池
agent-team skill preferences --reset        # 清空偏好池，回到全空

agent-team skill default dev plan           # 锁定 Dev 默认（不跟随 last 变化）
agent-team skill default dev --reset        # 解锁，恢复跟随 last
```

### 一次典型的使用旅程

```
第 1 次: agent-team dev --message "...需求..."
  Phase 2 确认 → 技能多选（全空）→ 选了 plan + security-audit
  → 偏好池写入 last: [plan], [security-audit]
  → 执行

第 2 次: agent-team dev --message "...另一个需求..."
  Phase 2 确认 → 技能: plan (Dev) · security-audit (QA) [Enter 继续]
  → 什么都没改，偏好池不变
  → 执行（frequent +1）

第 3 次: 觉得 QA 不需要 security-audit 了
  按 s → 把 QA 的 [x] security-audit 切掉 → 回车
  → 偏好池 last 更新
  → 执行

第 5 次: 稳定下来 → agent-team skill default dev plan
  → Dev 永远用 plan，不再跟随 last

某天: agent-team skill preferences --reset
  → 清空，下回重新问
```

---

## Task 5：Interactive Flow Controller (v1 改造——三阶段 + 决策点)

**文件：** `agent_team/interactive.py`, `tests/test_dev_command.py`

### 流程伪代码

```python
class DevController:
    def run(self) -> str:
        # Phase 1: 需求对齐
        raw_request = self._collect_requirement()
        alignment = self._confirm_phase(
            phase="requirement",
            runner=self.alignment_runner,
            raw_input=raw_request,
        )
        # alignment 确认后保存

        # Phase 2: 技术方案
        repo_structure = self._capture_repo_structure()
        tech_plan = self._confirm_phase(
            phase="tech_plan",
            runner=self.tech_plan_runner,
            raw_input=alignment,
            extra_context={"repo_structure": repo_structure},
        )
        # tech_plan 确认后保存

        # 技能选择（首次多选，后续偏好预选）
        skills = self._select_skills(tech_plan)

        # 决策点: 是否委托 Agent
        choice = self._ask_agent_decision()
        if choice == "q":
            raise SystemExit("Session saved. Resume with --session-id.")
        if choice == "m":
            self._print_manual_instructions()
            return session_id

        # Phase 3: Agent 链执行
        session = self._start_session(initiator="human", ...)
        self._run_stage("Product")
        self._auto_approve_product()
        self._run_stage("Dev")
        self._run_stage("QA")  # 可能 rework 回 Dev
        self._run_stage("Acceptance")
        self._print_final_decision_prompt()
        return session.session_id

    def _select_skills(self, tech_plan: TechPlanDraft) -> dict[str, list[str]]:
        """技能选择：首次多选，后续偏好预选。

        参考 openclaw 的 WizardPrompter.multiselect 交互模式。
        """
        prefs = self.skill_registry.load_preferences()
        for stage in ["Dev", "QA", "Acceptance"]:
            available = self.skill_registry.list_skills(stage)
            if prefs.is_first_time:
                # 首次：交互式多选
                chosen = self.prompter.multiselect(
                    message=f"{stage} 阶段可用的技能",
                    options=[
                        {"label": f"{s.name:.<30} ({s.source}) {s.description}"}
                        for s in available
                    ],
                    initial_values=[],  # 全空默认
                )
            else:
                # 后续：展示偏好预选，一行提示
                self.prompter.show(
                    f"技能 [{stage}]: {prefs.format_last(stage)}  "
                    f"按 [s] 修改  按 [Enter] 继续"
                )
                if self.prompter.wait_key() == "s":
                    chosen = self.prompter.multiselect(
                        message=f"{stage} 阶段可用的技能",
                        options=[...],
                        initial_values=prefs.last[stage],
                    )
                else:
                    chosen = prefs.last[stage]
            self.skill_registry.record(stage, chosen)
        return self.skill_registry.get_enabled()

    def _ask_agent_decision(self) -> str:
        """决策点：y=启动Agent链, m=手动, q=退出"""
        self.show("\n技术方案已确认。")
        self.show(f"涉及 {len(self.tech_plan.affected_modules)} 个模块")
        self.show(f"实现步骤: {len(self.tech_plan.implementation_steps)} 步")
        return self.ask(
            "\n是否委托 Agent 执行？\n"
            "[y] 启动 Dev/QA/Acceptance Agent 链\n"
            "[m] 手动执行（保留 session，自行提交结果）\n"
            "[q] 退出\n> "
        )
```

### 决策点 UI

```text
技术方案已确认:
- 涉及模块: 2 (src/auth/login.ts, src/components/Profile.tsx)
- 实现步骤: 4 步
- 风险: 低

是否委托 Agent 执行？
[y] 启动 Dev/QA/Acceptance Agent 链
[m] 手动执行（保留 session，自行提交结果）
[q] 退出
>
```

---

## Task 6：CLI 命令注册

**文件：** `agent_team/cli.py`, `tests/test_cli.py`

### 新增命令

```python
dev_parser = subparsers.add_parser(
    "dev",
    help="Interactive development workflow: clarify requirements, "
         "discuss technical approach, then execute via AI agents.",
)
dev_parser.add_argument("--message", help="Initial requirement. Prompt if omitted.")
dev_parser.add_argument("--session-id", help="Existing session to resume.")
dev_parser.add_argument("--codex-bin", default="codex", help="Path to codex executable.")
dev_parser.add_argument("--model", default="", help="Optional model override.")
dev_parser.add_argument("--sandbox", default="workspace-write", help="Codex sandbox mode.")
dev_parser.add_argument("--profile", default="", help="Optional Codex config profile.")
dev_parser.add_argument("--dry-run", action="store_true", help="Print plan without executing.")
dev_parser.set_defaults(handler=_handle_dev)
```

### start-session 新增 --initiator

```python
start_session_parser.add_argument(
    "--initiator", choices=["human", "agent"], default="agent",
)
```

---

## Task 7：文档和技能包更新

**文件：** `agent_team/project_scaffold.py`, skill 文件, README

- `agent-team-run` 技能推荐 `agent-team dev` 作为终端使用方式
- `codex-init` 生成的 agent 配置更新文档引用
- README 添加 `agent-team dev` 使用示例

---

## Task 8：全量验证

- [ ] 单元测试：alignment + tech_plan + codex_exec + stage_harness（三个 agent 提示词）
- [ ] 集成测试：fake codex 端到端 `agent-team dev --message "..." --codex-bin ./fake_codex`
- [ ] 权限测试：agent session 的 human decision 被拒绝
- [ ] 决策点测试：y/m/q 三路分支
- [ ] QA rework 测试：QA 失败 → 自动回 Dev
- [ ] 全量测试套件

---

## 总结：v2 相比 v1 的差异

| 维度 | v1 | v2 |
|---|---|---|
| 命令名 | `run-interactive` | `dev` |
| 用户交互 | 一个 alignment 确认 | Phase 1(需求) + Phase 2(技术) 两个独立确认 |
| 子Agent 决策 | 无 | y/m/q 决策点 |
| AI 调用路径 | 隐含 | 明确 `initiator: agent` + 权限拦截 |
| Dev 提示词 | 通用 stage prompt | 专用：自验证、不gold-plate、report specifics |
| QA 提示词 | 通用 | 专用：空沙箱、skeptical、prove not confirm |
| Acceptance 提示词 | 通用 | 专用：纸面证据、cross-reference、final verdict |
| 沙箱策略 | 未明确 | Dev=workspace, QA/Acceptance=clean |
| 提示词模式 | 基础 | 借鉴 claude-code：自包含、done定义、specifics、evidence |

---

## Agent 提示词保护层清单

每个 stage agent 的提示词都包含五层保护，按阶段特点调整：

| 保护层 | Dev | QA | Acceptance | 来源 |
|---|---|---|---|---|
| **SCOPE** | 不越界改代码、不 premature abstraction | 不越界审计、验证但不修复 | 不越界裁决 | claude-code doing tasks |
| **SECURITY** | OWASP top 10、命令注入 | OWASP、硬编码密钥、不安全反序列化 | 审查 QA 发现的安全问题 | claude-code security |
| **INTEGRITY** | 不伪造"测试通过"、不隐瞒未验证步骤 | 不压制失败、不 dismiss 错误、"tests passed" 需附命令+输出 | 不 rubber-stamp、不确定就说、不制造信心 | claude-code Capybara false-claims mitigation |
| **BOUNDARY** | 不改状态机、不改 session、不调 human-decision、不做破坏性 git 操作 | 不改状态机、不改 session、不改代码 | 不改状态机、只建议不决定 | agent-team-runtime 特有 |
| **OUTPUT** | 绝对路径、commit hash、命令+输出 | 命令+输出、每项 AC 附证据、passed/failed/blocked 附理由 | 每项 AC 附证据引用、命名风险、解释理由 | claude-code specificity |

### 保护层的设计原则

1. **不是"建议"，是"规则"**：用 `Do NOT` 开头而不是 `You should avoid`。claude-code 提示词全部用大写 `IMPORTANT`、`CRITICAL`、`Do NOT` 开头，agent 对这些指令的遵从度更高。

2. **具体到错误类型**：不说"注意安全"，说"检查命令注入、XSS、SQL 注入、硬编码密钥"。

3. **告诉 agent 为什么不能做**："你是 STAGE AGENT，只对当前阶段负责。runtime 处理后续流程。" 而不是只说 "不要改状态机"。

4. **每个约束有对称的正面指示**：
   - 不压制失败 → 如实报告
   - 不越界改代码 → 只改 tech plan 范围内的
   - 不 rubber-stamp → cross-reference + 证据引用

5. **QA 和 Acceptance 的保护比 Dev 更严**：
   - QA 额外有 `Do NOT modify the codebase — you verify, you don't fix`
   - Acceptance 额外有 `You recommend go/no-go to the human — the human decides`
