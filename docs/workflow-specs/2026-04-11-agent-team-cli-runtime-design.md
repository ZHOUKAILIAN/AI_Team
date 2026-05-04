# Agent Team CLI Runtime 设计说明

日期：2026-04-11

## 设计目标

`Agent Team` 的新目标不是继续强化 skill 提示词，而是成为一个通过 CLI 暴露、对 AI 友好的工程化团队运行时。

它应该具备这几个属性：

- CLI-first
- runtime-controlled
- AI-friendly
- team-oriented
- extensible
- self-evolving

## 核心定义

`Agent Team` 是一个 AI team orchestration runtime。

它不是：

- 单纯的 prompt 集合
- 纯文档驱动 demo
- 只能在对话里靠人维持秩序的流程

它应该是：

- 一个可安装的 CLI
- 一个拥有状态机和契约层的 runtime
- 一个默认内置 Product / TechPlan / Dev / QA / Acceptance 团队的 framework

## 为什么不再使用 Harness-First 这个名字

`Harness-First` 更像内部演进阶段名，不适合作为项目长期对外名称。

现在更合适的名字是：

- `Agent Team CLI Runtime`

因为这个名字同时说明了三件事：

- 它是 `Agent Team`
- 它的主入口是 `CLI`
- 它的本质是 `Runtime`

## 设计原则

### 1. CLI 是主入口

用户和上层 AI 都应该优先通过：

```bash
agent-team ...
```

来驱动流程，而不是长期依赖：

```bash
python3 -m ...
```

### 2. Runtime 持有流程控制权

流程的事实来源应当是 runtime 状态，而不是当前对话里说了什么。

### 3. Team Contract 优先于自由发挥

每个阶段都应该有明确 contract：

- 输入
- 输出
- 禁止动作
- 证据要求

### 4. Learning 必须工程化

学习不能只存在对话里，必须能落盘、复用、演进。

### 5. 人工决策不可替代

Acceptance 只能建议，最终 Go / No-Go 必须由人来决定。

## 分层结构

### CLI Layer

提供统一命令入口：

- `start-session`
- `current-stage`
- `resume`
- `build-stage-contract`
- `submit-stage-result`
- `record-human-decision`
- `record-feedback`

### Runtime Layer

负责：

- session 状态
- 状态机推进
- artifact 落盘
- findings / feedback / learning

### Team Layer

负责：

- Product / TechPlan / Dev / QA / Acceptance 这些角色定义
- 阶段边界
- 角色间 handoff 规则

### Asset Layer

负责：

- 角色 skill
- 角色 context
- 角色 memory
- 生成用的 project scaffold

## 当前默认团队流程

```text
Product -> CEO approval -> Dev <-> QA -> Acceptance -> human Go/No-Go
```

这是一条默认团队流，不是最终只能有这一条流。

后续扩展方向包括：

- 新增角色
- 新增阶段
- 新增阶段 contract builder
- 新增 route / gate evaluator

## 当前运行边界

当前已经完成：

- CLI 主入口
- app-local state root
- 显式状态机
- contract 生成
- bundle 提交
- 人工决策
- learning feedback 回流

当前还没有完成：

- 自动 worker 调度
- 原生插件形态
- 更强的多团队扩展模型

## 当前结论

后续这个项目的主线应该明确成：

`Agent Team` 是一个通过 CLI 驱动的 AI team orchestration runtime。
