# Agent Team Codex Harness 方案

日期：2026-04-11

## 目标

这份方案只关注 `Codex`。

不考虑 `Claude Code`、不考虑跨平台 hooks、也不考虑把 runtime 先抽象成一个面向所有宿主的通用插件系统。

当前目标是：

- 让 `Agent Team` 在 `Codex App` 中可稳定运行
- 让 `agent-team` 成为真正的 harness control plane
- 让 Codex 成为当前 stage 的执行器
- 让最小团队循环可以持续运行并可自我迭代

一句话定义：

`Agent Team` 采用 `Codex-only`、`runtime-first` 的 harness 方案。

## 为什么是 Codex-only

当前阶段不需要同时兼容多个宿主。

如果现在就为了适配多个平台而引入大量抽象，会让实现面变重，反而拖慢真正的运行时建设。

所以当前取舍是：

- 只适配 Codex 的能力模型
- 只使用 Codex 当前可依赖的入口层能力
- 把流程事实来源放到 `agent-team` CLI，而不是放到宿主特性里

## 核心判断

对 Codex 来说，最稳的 harness 不是 hook-first，而是 runtime-first。

也就是：

- `AGENTS.md` 负责全局约束
- skill 负责触发入口
- `agent-team` 负责流程控制
- Codex 负责真实执行

## 分层架构

### 1. Codex 原生层

这一层只使用 Codex 已经具备的能力：

- `AGENTS.md`
- skills
- worktrees
- background tasks
- 多 agent 执行能力

这一层的职责不是控流程，而是提供：

- 入口
- 角色解释
- 执行环境
- 并行能力

### 2. Agent Team Runtime 层

这一层是 harness 的事实来源。

核心职责：

- session 生命周期
- stage machine
- stage contract
- artifact bundle
- human decision
- feedback learning

当前 CLI 面：

- `agent-team start-session`
- `agent-team current-stage`
- `agent-team resume`
- `agent-team build-stage-contract`
- `agent-team submit-stage-result`
- `agent-team record-human-decision`
- `agent-team record-feedback`
- `agent-team review`

### 3. 角色资产层

这一层提供：

- `Product/`
- `Dev/`
- `QA/`
- `Acceptance/`
- `Ops/`

每个角色继续维护：

- context
- memory
- skill

但角色资产不再负责决定流程顺序。

### 4. 仓库适配层

这一层是具体项目里的接入面：

- `AGENTS.md`
- root `SKILL.md`
- installable skill
- `scripts/`

这层负责把 Codex 的自然语言入口接到 `agent-team` runtime。

## 控制面与执行面

### 控制面

控制面只属于 `agent-team`。

控制面负责回答：

- 现在在哪个 session
- 当前 stage 是什么
- 下一步该谁执行
- 当前是否是等待人工决策
- 当前 contract 是什么
- 这次反馈应该如何回流

### 执行面

执行面属于 Codex。

Codex 负责：

- 读取当前 contract
- 在真实仓库里执行当前 stage
- 生成 stage-result bundle
- 把结果提交回 runtime

所以架构关系应当是：

```text
Codex = executor
agent-team = controller
```

## Codex 接入原则

### 原则 1：不要把 skill 当成流程控制器

skill 的职责是：

- 识别 Agent Team workflow 触发意图
- 告诉 Codex 应该使用 `agent-team`
- 解释当前最小循环和边界

skill 不应该：

- 自己推进 stage
- 自己跳过 QA
- 自己决定最终 Go / No-Go

### 原则 2：不要假设 Codex 侧有强 hooks

当前方案不建立在 hooks 自动注入上。

即使将来 Codex 提供更强的生命周期钩子，当前阶段也不依赖它们。

### 原则 3：contract 比 prompt 更重要

Codex 真正执行当前阶段时，优先级最高的输入应该是 stage contract，而不是对话里零散的文字提醒。

### 原则 4：反馈必须回到 runtime

任何 QA、Acceptance、human feedback，都应该进入：

- findings
- `record-feedback`
- memory overlay

而不是只留在会话上下文里。

## 当前最小运行链路

当前推荐的最小运行链路是：

```text
start-session
-> current-stage
-> build-stage-contract
-> Codex execute current stage
-> submit-stage-result
-> wait or next stage
```

完整最小团队链路：

```text
Product -> CEO approval -> Dev -> QA -> Acceptance -> human Go/No-Go
```

## Codex 下的文件职责

### `AGENTS.md`

这里放全局规则，不放流程状态。

推荐承载：

- 任何 Agent Team 需求先走 `agent-team start-session`
- 任何 stage 执行前优先看 `build-stage-contract`
- 不允许跳过 QA
- Acceptance 不能代替最终 human decision
- 反馈必须通过 runtime 回流

### Skill

这里放入口说明，不放运行状态。

推荐承载：

- 触发词
- 使用范围
- runtime 与 skill 的边界
- Codex 当前最小 harness 循环

### Runtime State

这里承载真实状态：

- session
- workflow summary
- stage artifacts
- findings
- feedback
- memory overlays

## 推荐新增的 CLI 能力

为了让 Codex 更容易接入，下一步推荐补下面这些命令。

### `agent-team step`

这是最优先的命令。

它应该输出机器可读的下一步信息，例如：

```json
{
  "session_id": "<session_id>",
  "current_state": "Dev",
  "stage": "Dev",
  "action": "execute_stage",
  "requires_human_decision": false,
  "contract_path": "/path/to/contract.json",
  "required_outputs": ["implementation.md"]
}
```

它的作用是让 Codex 不必自己拼当前阶段逻辑。

### `agent-team explain-next`

这是给人和 Codex 都能读的解释层。

应该回答：

- 当前为什么停在这里
- 下一步是谁执行
- 是不是等待人工决策
- 如果不是等待态，应该先做什么

### `agent-team make-bundle-template`

为当前 stage 生成最小 bundle 模板，降低 Codex 产出 JSON 的摩擦。

### `agent-team doctor`

检查当前 session 是否缺失：

- summary
- contract
- artifact
- required evidence

### `agent-team step --format json`

如果 `step` 默认输出人类可读文本，那么建议同时支持 JSON 输出，方便 Codex 直接消费。

## M0 / M1 / M2 路线

### M0

目标：最小 harness 循环可运行。

范围：

- `start-session`
- `build-stage-contract`
- `submit-stage-result`
- `record-human-decision`
- `record-feedback`
- Codex help + skill integration

完成标准：

- Codex 能按 contract 执行 Product / Dev / QA / Acceptance
- 遇到等待态会停
- 反馈能进入下一轮 contract

### M1

目标：让 Codex 接入成本显著下降。

范围：

- `agent-team step`
- `agent-team explain-next`
- `agent-team make-bundle-template`
- `agent-team doctor`
- 更清晰的 session/operator UX

完成标准：

- Codex 不需要自己推断当前 stage
- Codex 不需要手写最小 bundle 结构
- 人类可以快速看懂当前 session 卡在哪里

### M2

目标：让 Codex 能更像一个连续运行的 team executor。

范围：

- 可选的 stage runner
- 更好的并行 worker dispatch
- 更好的 review / evidence gate
- 更强的扩展注册机制

完成标准：

- 多个 stage worker 可以更顺畅地衔接
- QA / Acceptance 的证据门控更自动化
- 新角色 / 新阶段的接入成本可控

## 当前不做的事情

当前阶段明确不做：

- Claude Code hooks 适配
- 多宿主统一抽象层
- plugin-first 形态
- 为了未来跨平台而提前设计复杂中间层

这些都可以等 Codex-only 路线稳定后再考虑。

## 最终建议

对当前项目来说，最重要的不是继续扩写 skill，而是继续强化 `agent-team` 这个 CLI harness。

所以后续主线建议明确成：

```text
先把 Codex-only 的 runtime 跑顺
再逐步降低 Codex 接入成本
最后再考虑更强的自动化与扩展能力
```

## 结论

`Agent Team` 在 Codex 下的正确实现方式，不是让 skill 接管流程，而是让 `agent-team` 接管流程，让 Codex 专注执行。

这就是当前阶段最适合的 Codex Harness 方案。
