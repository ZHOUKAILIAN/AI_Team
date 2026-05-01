# Agent Team Orchestration Control Options

日期：2026-04-22

## 问题定义

你现在在比较的，不是“哪个 agent 框架更强”，而是：

- 流程控制权继续放在 prompt 里，靠模型“遵守流程”
- 还是把阶段推进、证据门禁、人工审批、恢复重试交给代码/runtime

对 Agent Team 这类固定阶段工作流，核心判断是：

> 阶段顺序、必需产物、证据门禁、人工审批，不应该主要靠模型自觉，应该由代码控制。

模型更适合负责语义工作：

- 写 PRD、实现说明、QA 报告、Acceptance 报告
- 从反馈里抽 Finding
- 生成修复建议和验证建议

## 先给结论

如果目标是把 Agent Team 变成一个稳定、可追责、可恢复的工程系统，我的建议顺序是：

| 方案 | 结论 |
| --- | --- |
| 继续主要靠 prompt 约束 AI | 不建议。演示可以，生产流程不稳。 |
| 纯 LangChain 作为主控层 | 不建议作为主控层。更适合 agent 组件和工具封装。 |
| LangGraph 作为 workflow runtime | 可行，而且比“靠 prompt”可靠得多。 |
| OpenAI Agents SDK 作为 agent runtime | 可行，尤其在你标准化 OpenAI、想要 handoff / guardrails / observability 时。 |
| 自研状态机 / runtime | 对 Agent Team 这类固定阶段流程，通常是最稳的主控方案。 |

我的偏向：

> Agent Team 最适合“自研状态机作为 control plane，OpenAI Agents SDK 作为默认 agent execution layer”。

也就是说：状态、阶段、门禁、审批、返工流转由你自己的 runtime 控制；AI 的执行、工具调用、handoff、guardrails、tracing 交给 OpenAI Agents SDK。

## 对比表

| 方案 | 核心定位 | 对固定阶段流程的控制力 | 人工审批 / 暂停恢复 | 多 agent / specialist | 工具与观测 | 代价 | 对 Agent Team 的适配判断 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Prompt-only | 把流程写进 system prompt / role prompt | 弱。模型会漂移，边界靠约定 | 弱。要自己补状态落盘和恢复 | 可做，但容易失控 | 取决于你自己补多少 | 初始最省事，长期返工最大 | 不建议继续作为主方案 |
| LangChain | 高层 agent 组件和中间件层 | 中。适合 agent 能力，不适合单独做强 stage gate | 中。要配合下层 runtime | 强，但更多偏 agent loop | 工具生态成熟 | 抽象多，容易“看起来方便、实则难控” | 适合做 agent 层，不适合做主控层 |
| LangGraph | 面向 workflow/agent 的图运行时 | 强。适合显式节点、状态和路由 | 强。内建 persistence / durable execution / interrupt | 强。orchestrator-worker 很自然 | 调试、流式、部署能力完整 | 学习成本中等 | 适合作为 runtime，但你仍要定义业务 gate |
| OpenAI Agents SDK | OpenAI 的 code-first agent runtime | 中到强。适合 tool/state/approval/handoff，但业务 stage 仍建议你自己定义 | 强。官方就把 approvals、results/state、continuation 当一等能力 | 强。适合 specialist ownership / handoff | OpenAI tracing/observability 路线更顺 | 有 OpenAI 生态绑定 | 适合你如果想统一到 OpenAI 能力栈 |
| 自研状态机 / runtime | 你自己定义 stage/state/contract/evidence | 最强。每个 gate 都可精确编码 | 最强，前提是你自己实现 | 中。需要你自己设计 worker/handoff 机制 | 观测也要自己做 | 前期工程量最大 | 最适合 Agent Team 的主控层 |

## 关键判断点

### 1. 如果你的流程是预定义的，先选 workflow，不要先选 agent

LangGraph 官方明确区分：

- workflow 是“预定代码路径”
- agent 是“动态决定过程和工具使用”

这和 Agent Team 非常贴近。你的主链路是固定的：

`Intake -> Product(PRD + AcceptanceCriteria) -> WaitForRequirementsApproval -> Dev -> QA -> Acceptance -> Done/Rework`

这不是典型的“让 agent 自己决定下一步”的问题，而是典型的“业务状态机 + 局部 agent 能力”的问题。

### 2. LangChain 本身不是这个问题的主答案

LangChain 官方现在也写得很直接：`create_agent` 底层本来就是建立在 LangGraph 之上的 graph runtime。

所以如果你的问题是：

> 我想把流程控制得更死、更稳定

那答案更接近：

- 要么直接上 LangGraph
- 要么自己写状态机

而不是“把控制权交给 LangChain 高层 agent 抽象”

### 3. OpenAI Agents SDK 更适合做 agent runtime，不天然等于业务工作流引擎

OpenAI 官方文档对适用边界也写得很清楚：

- 当你的应用自己拥有 orchestration、tool execution、approvals、state 时，用 Agents SDK
- 当你需要 multi-agent specialist ownership、guardrails、results/state、integrations/observability 时，继续往 SDK 这些章节走

这说明 Agents SDK 很适合作为：

- tool-calling runtime
- specialist/handoff runtime
- OpenAI 生态内的执行层

但 Agent Team 的“Product 之后必须等人批准 PRD 和验收标准、QA findings 必须回 Dev、Acceptance 只能按已批准标准裁决”这种业务规则，最好还是你自己硬编码。

## 分场景建议

### 方案 A：继续现在的路线，但把 runtime 做硬

适合你当前 Agent Team。

建议分层：

1. `workflow runtime`
   - stage machine
   - contract generation
   - evidence gate
   - requirements approval gate
   - persistence / replay / audit
2. `agent execution layer`
   - Product / Dev / QA / Acceptance 这些角色 agent
   - 可以用 Responses API、Agents SDK，或者 LangGraph 子图
3. `tool / surface layer`
   - git
   - figma
   - test runner
   - browser / miniprogram / runtime screenshot

这个方案的优点：

- 你的业务规则不会被 agent 抢控制权
- 后续换模型、换 provider、换 agent 框架的成本低
- 更容易做审计和回放

### 方案 B：用 LangGraph 替代你现在的一部分 runtime

适合你如果想减少自研恢复/interrupt/worker routing 这部分胶水。

比较适合迁进去的点：

- QA / Acceptance 的暂停恢复
- orchestrator-worker 型任务拆解
- 长流程 checkpoint
- 人工 review interrupt

不建议直接让 LangGraph 取代的点：

- 业务 stage 语义本身
- 证据契约
- 审批边界
- 你的 artifact contract

更好的做法是：

> 让 LangGraph 成为“执行引擎”，而不是“业务规则唯一来源”。

### 方案 C：用 OpenAI Agents SDK 统一 agent 执行层

适合你如果接下来打算：

- 主要标准化在 OpenAI 栈
- 要更多 specialist handoff
- 要 guardrails / human review / tracing
- 要把 agent runtime 和 OpenAI 工具能力更顺地接起来

这个方案不差，但有两个现实点：

- 你会更依赖 OpenAI 生态语义
- 你仍然应该保留自己的 stage machine

也就是说，最合理的姿势通常不是：

> “让 Agents SDK 直接代表业务流程”

而是：

> “你的业务 runtime 决定该执行哪个阶段；阶段内部再调用 Agents SDK 跑具体 agent”

## 如果只让我选一个主控方向

### 我对 Agent Team 的推荐

| 层 | 推荐 |
| --- | --- |
| 主控层 | 自研 workflow runtime / state machine |
| agent 执行层 | OpenAI Agents SDK 作为默认实现；保留抽象接口，避免锁死 |
| 文档与证据层 | 继续保留 artifact contract，不要并进 agent prompt 里 |

更具体一点：

| 如果你最在意 | 更推荐 |
| --- | --- |
| 业务规则严密、阶段固定、审计优先 | 自研状态机 |
| 长流程恢复、interrupt、worker fan-out | LangGraph |
| OpenAI 专用能力、handoff、guardrails、observability | OpenAI Agents SDK |
| 快速把 agent 跑起来 | LangChain，但别让它当主控层 |

## 我会怎么落地

如果我是你，我会这么做：

1. 保留 Agent Team 现在的 stage machine 作为唯一流程真相
2. 把“当前 stage 可做什么、必须提交什么、缺什么证据才能过”全部放在 runtime
3. 角色 agent 只接收当前 stage contract，不直接决定流程跳转
4. 为 agent execution 层留一个统一接口：
   - `run_stage_with_openai_agents(...)`
   - `run_stage_with_langgraph(...)`
   - `run_stage_with_prompt_only(...)`
5. 先把 `run_stage_with_openai_agents(...)` 做成默认实现
6. 先不要重构整套系统到某个框架
7. 先挑一个最痛点的阶段试点：
   - 比如 Acceptance 的 interrupt/resume
   - 或者 Dev / QA 的 orchestrator-worker fan-out

这样你不会一次性把“流程语义”和“agent 框架”绑死。

### 推荐目标架构

```text
Agent Team Runtime
  - owns session state
  - owns stage transition
  - owns evidence gate
  - owns approval / rework decision
  - owns audit log and resume

OpenAI Agents SDK
  - runs ProductAgent / DevAgent / QAAgent / AcceptanceAgent
  - calls tools
  - handles specialist handoff inside a stage
  - applies model-side guardrails
  - emits traces for debugging and review
```

这条边界很关键：OpenAI Agents SDK 可以决定“这个阶段内哪个 specialist 继续干、调用什么工具”；但不能决定“PRD/验收标准是否已获人批准、QA 是否通过、Acceptance finding 是否必须回 Dev”。

## StagePolicy 结构建议

你前面那句“评判标准这些都需要我来确定”是对的。对 Agent Team 来说，真正要被代码掌握的不是 prompt，而是每个 stage 的裁判标准。

结合现有实现，更合适的结构不是让 `StageMachine` 直接吃 agent 自报状态，而是走这条链：

```text
StagePolicy
  -> build StageContract
  -> agent executes via OpenAI Agents SDK
  -> produce StageResultEnvelope
  -> runtime runs deterministic gate checks
  -> independent judge model reviews compressed context
  -> runtime emits GateDecision
  -> StageMachine applies GateDecision
```

### 现有代码里的落点

当前仓库里已经有这些基础件：

- `StageContract`
- `EvidenceRequirement`
- `AcceptanceContract`
- `StageResultEnvelope`
- `GateResult`

所以更合理的演进方向不是重写一套，而是补一个“标准源头”：

```python
@dataclass(slots=True)
class StagePolicy:
    stage: str
    goal: str
    required_outputs: list[str]
    evidence_specs: list[EvidenceRequirement]
    required_checks: list[str]
    allowed_agent_statuses: list[str]
    pass_rule: str
    failback_targets: list[str]
    approval_rule: str | None = None
    acceptance_contract: AcceptanceContract | None = None
    allow_findings: bool = True
    blocking_conditions: list[str] = field(default_factory=list)
```

这个对象的作用很单纯：

- 定义这个 stage 想要什么
- 定义拿到什么证据才算完成
- 定义什么情况通过、什么情况回流、什么情况必须人工决定

### 建议再补两个运行时结果对象

```python
@dataclass(slots=True)
class GateDecision:
    outcome: Literal["pass", "rework", "blocked", "await_human"]
    target_stage: str | None = None
    reason: str = ""
    missing_outputs: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    judge_verdict: str = ""
    judge_confidence: float | None = None
    judge_trace_id: str = ""
    derived_status: str = ""


@dataclass(slots=True)
class StageEvaluation:
    policy: StagePolicy
    result: StageResultEnvelope
    judge_result: JudgeResult | None
    decision: GateDecision
```

这样 `StageMachine` 不再直接相信执行 agent 回的 `status` 或 `acceptance_status`，也不直接相信 judge 的建议，而是只消费 runtime 自己算出来的 `GateDecision`。

### 运行时职责边界

推荐拆成 3 个明确部件：

1. `PolicyRegistry`
   - 按 stage 提供 `StagePolicy`
   - `Product / Dev / QA / Acceptance` 的标准都在这里集中维护
2. `ContractBuilder`
   - 从 `StagePolicy` 编译出 `StageContract`
   - 给 OpenAI Agents SDK 只发当前阶段允许看到的 contract
3. `GateEvaluator`
   - 用 `StagePolicy + StageResultEnvelope` 算 `GateDecision`
   - 先跑确定性规则，再调用独立 judge 做语义复核
   - 判断通过、回流、阻塞、待人工审批

## 独立 Judge 模型

你提到的“每次执行完成之后，判断能不能流转，也要调用新的大模型”，我认为应该作为 `GateEvaluator` 的一部分，而且必须和执行 agent 隔离。

推荐边界：

```text
Execution Agent
  - 负责做事
  - 产出 artifact / evidence / findings / suggested_actions
  - 不能决定是否流转

Independent Judge
  - 负责复核
  - 读取压缩后的原始需求、StagePolicy、StageContract、上下文、产物和证据
  - 输出结构化 judge verdict
  - 不能写文件、不能改状态、不能直接流转

Runtime
  - 负责最终裁决
  - 合并 hard gate + judge verdict
  - 生成 GateDecision
  - 调用 StageMachine 做状态迁移
```

### 为什么不能用原来的执行模型自判

执行 agent 有几个天然问题：

- 它已经投入了当前解法，容易自证完成
- 它的上下文可能被执行过程污染
- 它倾向于把“我做了”解释成“可以过”
- 它可能忽略原始需求里没有显式重复的约束

所以 judge 应该是一次新的、隔离的模型调用。可以用同一个底层模型，也可以用更强模型；关键是不能复用执行 agent 的主观上下文。

### Judge 输入包

judge 不应该拿完整无限上下文，而应该拿 runtime 压缩后的 `JudgeInput`：

```python
@dataclass(slots=True)
class JudgeInput:
    session_id: str
    stage: str
    original_request_summary: str
    product_requirements_summary: str
    stage_policy: StagePolicy
    stage_contract: StageContract
    stage_result: StageResultEnvelope
    relevant_artifacts: dict[str, str]
    evidence_summary: list[EvidenceItem]
    previous_findings: list[Finding]
    hard_gate_result: GateResult
```

这里的压缩应该由 runtime 做，而不是由执行 agent 自己总结。压缩目标是让 judge 明确看到：

- 原始需求是什么
- 当前阶段应该交付什么
- 执行 agent 实际交了什么
- 哪些证据是可验证的
- 之前 QA / Acceptance / Human 提过什么问题
- hard gate 已经发现哪些缺口

### Judge Context Compact

参考 Claude Code 的 compact / memory 设计，给 judge 的上下文不应该是“完整聊天记录压缩版”，而应该是一次可重建裁判语义的 `JudgeContextCompact`。

核心原则：

- 稳定规则和临时执行上下文分开
- 入口短小，正文用引用寻址
- compact 的目标是保住工作语义，不是回忆完整过程
- 为 judge 输出和失败恢复预留 token 预算
- 压缩后要重新注入裁判必需附件，而不是只给一段 summary

建议结构：

```python
@dataclass(slots=True)
class JudgeContextCompact:
    header: JudgeHeader
    stable_rules: JudgeStableRules
    current_state: JudgeCurrentState
    task_specification: JudgeTaskSpecification
    acceptance_matrix: list[AcceptanceCriterion]
    artifact_index: list[ArtifactRef]
    evidence_index: list[EvidenceRef]
    execution_summary: StageExecutionSummary
    hard_gate_result: GateResult
    prior_findings: list[Finding]
    errors_and_corrections: list[CorrectionRef]
    budget: JudgeContextBudget
```

`JudgeContextCompact` 里应该优先放“可裁判的信息”，而不是“执行 agent 说了什么”。例如：

| 区块 | 内容 | 是否放全文 |
| --- | --- | --- |
| `stable_rules` | 已批准 PRD 摘要、验收标准、StagePolicy、不可违背规则 | 只放摘要和关键表 |
| `acceptance_matrix` | AC ID、场景、标准、必需证据、失败回流 | 放结构化表 |
| `artifact_index` | 产物路径、hash、摘要、关键片段 | 默认不放全文 |
| `evidence_index` | 命令、exit code、截图/视频/日志引用、visual diff 摘要 | 默认不放大附件 |
| `execution_summary` | agent 实际做了什么、改了什么、声称完成什么 | 放压缩摘要 |
| `hard_gate_result` | 缺哪些产物、缺哪些证据、硬规则是否通过 | 放全文结构 |
| `prior_findings` | 仍相关的历史 QA / Acceptance / Human feedback | 放相关项，不放全历史 |
| `errors_and_corrections` | 本轮踩过的坑和修正 | 放高密度摘要 |

### Judge 上下文预算

建议一开始就把预算写成代码常量，而不是等 prompt 超了再补救：

```python
MAX_JUDGE_CONTEXT_TOKENS = 24_000
MAX_JUDGE_SECTION_TOKENS = 2_000
RESERVED_JUDGE_OUTPUT_TOKENS = 4_000
MAX_ARTIFACT_SNIPPET_TOKENS = 800
MAX_PRIOR_FINDINGS = 20
MAX_COMPACT_FAILURES = 3
```

压缩优先级：

1. 保留 `approved PRD + acceptance matrix + StagePolicy`
2. 保留 `hard_gate_result`
3. 保留当前 stage 的产物摘要和证据摘要
4. 保留相关历史 findings 和 corrections
5. 裁掉冗长聊天、重复日志、可重新读取的大文件全文

如果超过预算，不应该简单截断尾部，而应该按区块降级：

| 降级顺序 | 动作 |
| --- | --- |
| 1 | artifact 全文变摘要 |
| 2 | 长日志变命令 + exit code + 关键错误片段 |
| 3 | 历史 findings 只保留未关闭和同 target stage 的 |
| 4 | 多张截图只保留索引、尺寸、diff 摘要和关键一张 |
| 5 | 仍超预算则返回 `needs_human` 或 `blocked: judge_context_too_large` |

### Judge 可读附件

compact 之后，需要重新注入 judge 必需的附件。不能只给 summary。

最少附件：

- 已批准 PRD 的 compact 摘要
- 已批准 acceptance matrix
- 当前 `StagePolicy`
- 当前 `StageContract`
- 当前 `StageResultEnvelope`
- hard gate 结果
- artifact index
- evidence index
- previous unresolved findings

对 Figma / UI 类任务，额外给：

- Figma file key / node id / frame name
- 设计尺寸和目标视口
- screenshot 引用
- visual diff 摘要
- mismatch table
- tolerance rule

### Judge 沙箱输入示例

```json
{
  "judge_task": "Decide whether the Acceptance stage can pass under the approved acceptance matrix.",
  "stage": "Acceptance",
  "decision_options": ["pass", "rework", "blocked", "needs_human"],
  "approved_acceptance_matrix": [
    {
      "id": "AC-001",
      "scenario": "Figma restoration",
      "standard": "Rendered UI must match the approved Figma frame within configured tolerance.",
      "required_evidence": ["target_screenshot", "figma_reference", "visual_diff_summary"],
      "failure_target": "Dev"
    }
  ],
  "hard_gate_result": {
    "status": "passed",
    "missing_outputs": [],
    "missing_evidence": []
  },
  "artifact_index": [
    {
      "name": "acceptance_report.md",
      "path": ".agent-team/.../acceptance_report.md",
      "sha256": "...",
      "summary": "Acceptance report claims the restored component matches the Figma frame."
    }
  ],
  "evidence_index": [
    {
      "name": "target_screenshot",
      "kind": "image",
      "path": ".agent-team/.../target.png",
      "summary": "Screenshot captured at 1440x900."
    }
  ],
  "required_output_schema": "JudgeResult"
}
```

### Judge 不能拿什么

不要默认给 judge 这些东西：

- 完整对话历史
- 执行 agent 的 chain-of-thought 或自我评价
- 无关文件全文
- 未筛选的大日志
- 可以通过 index 重新读取的大附件
- 会诱导 judge 直接改状态的工具权限

### Judge 输出结构

judge 的输出也必须结构化，不能只给自然语言评价：

```python
@dataclass(slots=True)
class JudgeResult:
    verdict: Literal["pass", "rework", "blocked", "needs_human"]
    target_stage: str | None = None
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    trace_id: str = ""
```

`JudgeResult` 仍然不是最终状态迁移。它只是 `GateEvaluator` 的一个输入。

### 最终裁决规则

推荐默认规则：

| 条件 | Runtime 裁决 |
| --- | --- |
| hard gate 缺 required output | `blocked` 或 `rework` |
| hard gate 缺 required evidence | `blocked` 或 `rework` |
| judge verdict 是 `rework` 且有有效 finding | `rework` 到 target stage |
| judge verdict 是 `blocked` | `blocked` |
| judge verdict 是 `needs_human` | `await_human` |
| hard gate 通过，judge 也通过 | 才允许进入下一状态 |
| stage 是 Acceptance，且 PRD/验收标准已批准 | 默认可直接 `Done` 或进入自动发布后续 |
| stage 是 Acceptance，但任务开启 final override 或标准不可判定 | `await_human` |

这个规则的关键是：**pass 需要双重确认，fail 可以由任一层触发。**

### Human Gate 策略

你的新边界应该更收敛：

> 人只卡控 PRD 和验收标准；PRD/验收标准批准后，常规执行、复核、回流都由模型和 runtime 完成。

这意味着 human gate 不应该散落在每个阶段，而应该集中在 `WaitForRequirementsApproval`：

```text
Product 产出 PRD + AcceptanceCriteria
  -> Human 审 PRD 是否表达对
  -> Human 审验收标准是否足够清晰、可验证、可执行
  -> approved 后锁定为后续 execution / judge 的裁判依据
```

后续阶段的默认策略：

| 阶段 | Human 是否默认介入 | 裁判方式 |
| --- | --- | --- |
| Dev | 否 | hard gate + independent judge |
| QA | 否 | hard gate + independent judge |
| Acceptance | 否 | 按已批准验收标准，hard gate + independent judge |
| 最终发布/合并 | 可选 | 默认可由 runtime 自动完成；高风险任务可开启 human override |

`needs_human` 不应该是普通失败路径。它只在这些情况下触发：

- PRD 或验收标准缺失
- PRD 和验收标准冲突
- judge 发现标准不可判定
- 当前任务被配置为必须最终人工 override
- 模型要求变更已批准的需求边界

### PRD 展示方式

PRD 不建议写成大段自然语言。它应该尽量用图和表格表达，方便人快速卡控，也方便 judge 后续压缩引用。

推荐 PRD 结构：

| 区块 | 推荐表现形式 | 目的 |
| --- | --- | --- |
| 目标与非目标 | 表格 | 快速确认做什么、不做什么 |
| 用户流程 | Mermaid flowchart / sequence diagram | 让人看到完整路径和分支 |
| 状态流转 | Mermaid state diagram 或状态表 | 明确哪些状态能进入下一步 |
| 角色职责 | RACI 表 | 明确 Human / Runtime / Agent / Judge 各自负责什么 |
| 验收标准 | Acceptance matrix | 后续 judge 的主要依据 |
| 证据要求 | Evidence matrix | 明确每条标准需要什么证据 |
| 回流规则 | Finding -> target stage 表 | 明确发现问题时退回哪里 |
| 风险与边界 | 表格 | 标注不能自动裁决的情况 |

验收标准建议用矩阵，而不是散文：

```text
| ID | 场景 | 标准 | 必需证据 | 判定方式 | 失败回流 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 用户打开页面 | 页面结构与 Figma 一致 | screenshot + visual diff | judge + threshold | Dev |
| AC-002 | 空状态 | 无数据时显示指定空状态 | screenshot | judge | Dev |
| AC-003 | 交互反馈 | 点击后状态变化正确 | video/log | judge | Dev |
```

这样人只需要 review 这张表是否正确；后面模型按表执行和裁判。

### Judge 沙箱原则

judge 最好运行在只读沙箱里：

- 只能读 runtime 提供的 `JudgeInput`
- 不能调用写文件工具
- 不能执行 git push / merge / stage transition
- 不能修改 `.agent-team` 状态
- 可以读取必要 artifact 摘要
- 如需额外证据，只能输出 `missing_evidence`

这样 judge 负责“裁判意见”，runtime 负责“制度执行”。

### OpenAI Agents SDK 沙箱选型

OpenAI Agents SDK 已经提供 beta 形态的 `SandboxAgent` 和 sandbox clients，可以作为 independent judge 的执行隔离层。

建议第一版这样选：

| 选项 | 用途 | 判断 |
| --- | --- | --- |
| `SandboxAgent` | 在沙箱中运行 agent | 适合作 independent judge 的执行容器 |
| `DockerSandboxClient` | Docker 隔离 | 推荐试点使用，比本地沙箱更接近真实隔离 |
| `UnixLocalSandboxClient` | 本地开发沙箱 | 适合调试，不适合作强隔离 |
| Hosted sandbox client | 托管隔离 | 后续生产化可评估 |
| `CodeInterpreterTool` | 代码解释器沙箱 | 可辅助分析，但不能替代完整 judge sandbox |

推荐调用形态：

```text
Runtime
  -> build JudgeContextCompact
  -> build read-only manifest
  -> run OpenAISandboxJudge
  -> OpenAISandboxJudge runs SandboxAgent with DockerSandboxClient
  -> collect structured JudgeResult
  -> validate JudgeResult schema
  -> merge hard gate + JudgeResult into GateDecision
```

第一版代码里的落点：

```text
GateEvaluator
  -> receives a Judge implementation

OpenAISandboxJudge
  -> optional adapter for OpenAI Agents SDK SandboxAgent
  -> supports fake runner injection for tests
  -> imports Agents SDK only when real sandbox execution is requested

judge-stage-result CLI
  -> loads a submitted stage result
  -> runs hard gate
  -> builds JudgeContextCompact
  -> runs noop or OpenAI sandbox judge
  -> prints GateDecision JSON without mutating workflow state

verify-stage-result CLI
  -> can run the same judge pipeline with --judge noop or --judge openai-sandbox
  -> mutates workflow state only after GateEvaluator emits a passing GateDecision
  -> fails closed and restores the run to SUBMITTED if the sandbox judge is unavailable
```

安装真实 sandbox adapter：

```bash
pip install '.[openai-sandbox]'
```

本 worktree 的试用环境已经装在 `.venv/`：

```bash
.venv/bin/agent-team --help
```

只读试用流程：

```bash
.venv/bin/agent-team --state-root /tmp/agent-team-demo start-session \
  --message "执行这个需求：做一个支持 sandbox judge 的验收流转"

.venv/bin/agent-team --state-root /tmp/agent-team-demo acquire-stage-run \
  --session-id <session_id>

.venv/bin/agent-team --state-root /tmp/agent-team-demo submit-stage-result \
  --session-id <session_id> \
  --bundle <stage_result_bundle.json>

.venv/bin/agent-team --state-root /tmp/agent-team-demo judge-stage-result \
  --session-id <session_id> \
  --run-id <run_id> \
  --judge noop \
  --print-context
```

把 judge 接入真实流转：

```bash
.venv/bin/agent-team --state-root /tmp/agent-team-demo verify-stage-result \
  --session-id <session_id> \
  --run-id <run_id> \
  --judge noop
```

真实 OpenAI sandbox judge：

```bash
OPENAI_API_KEY=... .venv/bin/agent-team --state-root /tmp/agent-team-demo judge-stage-result \
  --session-id <session_id> \
  --run-id <run_id> \
  --judge openai-sandbox \
  --model gpt-5.4 \
  --docker-image python:3.13-slim \
  --print-context
```

如果要走自定义 OpenAI-compatible 网关，可以显式传 key 和 base URL：

```bash
.venv/bin/agent-team --state-root /tmp/agent-team-demo judge-stage-result \
  --session-id <session_id> \
  --run-id <run_id> \
  --judge openai-sandbox \
  --model gpt-5.4 \
  --docker-image python:3.13-slim \
  --openai-api-key "$OPENAI_API_KEY" \
  --openai-base-url "https://api.openai.com/v1" \
  --openai-proxy-url "http://127.0.0.1:7897" \
  --print-context
```

真实 OpenAI sandbox judge 参与流转：

```bash
OPENAI_API_KEY=... .venv/bin/agent-team --state-root /tmp/agent-team-demo verify-stage-result \
  --session-id <session_id> \
  --run-id <run_id> \
  --judge openai-sandbox \
  --model gpt-5.4 \
  --docker-image python:3.13-slim
```

`--openai-api-key` 和 `--openai-base-url` 不传时，Agents SDK 继续按环境变量解析，例如
`OPENAI_API_KEY` / `OPENAI_BASE_URL`。如果网络需要本地代理，可以显式传
`--openai-proxy-url "http://127.0.0.1:7897"`。judge runtime 默认使用 `Agent-Team-Runtime/0.1`
作为 User-Agent，避免部分 OpenAI-compatible 网关对 `OpenAI/Python ...` 默认 SDK 标识做 WAF 拦截。
`oa` header 默认会继承 `--openai-user-agent`，这样像 `ai.smartingredients.my` 这类依赖自定义 header 的中转，
不需要每次手动再传一遍。如果你的中转要求一个与 User-Agent 不同的 `oa` 值，再显式传
`--openai-oa "<value>"` 覆盖默认值即可。
CLI 输出只包含 judge verdict、confidence 和 gate decision，不回显 API key。

如果 Docker 未启动，命令会 fail closed，输出：

```text
Docker is not available for OpenAI sandbox judging. Start Docker Desktop or use a different sandbox backend.
```

注意：Agents SDK 的沙箱能力不等于 workflow 安全。Agent Team 仍然需要自己控制：

- judge 可读哪些 artifact
- judge 可调用哪些工具
- judge 是否能写文件
- judge 是否能发起 git / stage transition
- judge 输出是否符合 `JudgeResult`
- judge verdict 如何合并进最终 `GateDecision`

所以沙箱层的正确边界是：

> `SandboxAgent` 负责隔离 judge 的执行环境；runtime 负责裁判权限、输入清单、输出校验和状态流转。

参考资料：

- OpenAI Agents SDK Sandbox Agents: https://openai.github.io/openai-agents-python/sandbox/guide/
- OpenAI Agents SDK Sandbox clients: https://openai.github.io/openai-agents-python/sandbox/clients/

## 每个 Stage 最少要定的标准

### Product

```text
完成标准
  产出 PRD，且 acceptance criteria 明确
  PRD 和验收标准获人批准并锁定

必需证据
  explicit_acceptance_criteria

回流标准
  Human 选择 rework

审批标准
  必须等人批准 PRD 和验收标准
```

### Dev

```text
完成标准
  产出 implementation artifact，且自验证完成

必需证据
  self_verification

回流标准
  缺 required outputs
  缺 required evidence
  执行结果 blocked

审批标准
  无；通过后自动进入 QA
```

### QA

```text
完成标准
  独立验证完成，且没有导致回流的 findings

必需证据
  independent_verification

回流标准
  有 findings
  独立验证失败
  关键证据缺失

审批标准
  无；通过后自动进入 Acceptance
```

### Acceptance

```text
完成标准
  面向用户视角验证完成，并基于已批准验收标准形成通过 / 回流 / 阻塞判断

必需证据
  product_level_validation

回流标准
  findings 指向 Product 或 Dev
  关键视觉/交互证据缺失

审批标准
  默认不需要人工逐单拍板
  仅在标准缺失、冲突、不可判定，或显式开启 human override 时回到人
```

## 我会建议你把“评判标准”分成 4 层

| 层 | 作用 | 例子 |
| --- | --- | --- |
| Artifact rule | 检查产物是否齐全 | `prd.md`、`qa_report.md` 必须存在 |
| Evidence rule | 检查证据是否足够 | 必须有命令、截图、summary、exit_code |
| Finding rule | 决定 finding 是否触发回流 | 关键问题必须回 `Dev` |
| Approval rule | 决定是否必须人来拍板 | 默认只卡 `PRD + 验收标准批准`，高风险任务可额外开启 final override |

其中最关键的是最后两层，因为这两层最不能交给 agent 自己判断。

## 更贴近当前仓库的最小落地顺序

1. 保留 `stage_contracts.py` 现有输出结构，但把硬编码常量逐步迁到 `PolicyRegistry`
2. 让 `build_stage_contract(...)` 从 `StagePolicy` 编译，而不是直接读散落常量
3. 新增 `GateEvaluator`，把现在对 `status` / `findings` / `acceptance_status` 的判断集中进去
4. 让 `StageMachine` 只处理状态迁移，不负责解释证据是否足够
5. `acceptance_policy.json` 继续保留，作为 `Acceptance` 的专用证据 profile，而不是整个 workflow 的总 policy

如果只说一句落地判断：

> 你来定义并批准 PRD/验收标准，runtime 来裁决，Agents SDK 只负责执行和提交材料。

## 最后一句判断

> 对 Agent Team 这种系统，真正该被代码控制的是 workflow；真正该交给模型的，是每个 stage 里的语义工作。

如果你要的是“更可靠”，优先把 control plane 写硬。
如果你要的是“更灵活”，再给 execution plane 换 LangGraph 或 Agents SDK。

## 参考资料

- LangGraph durable execution: https://docs.langchain.com/oss/python/langgraph/durable-execution
- LangGraph workflows vs agents: https://docs.langchain.com/oss/python/langgraph/workflows-agents
- LangChain agents: https://docs.langchain.com/oss/python/langchain/agents
- OpenAI Agents SDK: https://developers.openai.com/api/docs/guides/agents
