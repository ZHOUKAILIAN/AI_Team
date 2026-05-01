# Agent Team Skill 接入说明

日期：2026-04-11

## 目标

这份文档说明如何把 `Agent Team CLI Runtime` 以 skill 的方式接入到 `Codex App`，同时保持 skill 与 runtime 的边界清晰。

核心原则是：

- skill 是入口，不是流程控制器
- runtime 才是 stage order 和 workflow state 的事实来源
- skill 负责触发、约束和说明
- `agent-team` 负责 bootstrap、状态推进、人工决策记录和学习回流

## Skill Standard 对这件事的要求

根据 `Skill Standard`，这类 skill 需要满足下面几个条件：

- `Goal` 清晰，说明 skill 要达成什么
- `When To Use` 清晰，说明什么时候触发
- `Available assets` 清晰，说明有哪些脚本、CLI、目录或生成物
- `Completion Signals` 清晰，说明什么才算真的完成
- 用相对路径描述资产，不硬编码绝对路径
- 不把 SKILL.md 写成一串必须照抄的命令
- 不让 skill 越权接管 runtime 的阶段推进

## 当前推荐的 skill 结构

当前这类 skill 推荐至少包含下面这些段落：

- `Goal`
- `When To Use`
- `Workflow Isolation Contract`
- `Available assets`
- `Artifact Contract`
- `Stage Outcomes`
- `Evidence Rules`
- `Completion Signals`

这是因为 `Agent Team` 不是一个单步工具，而是一套多角色、多阶段、有审批边界的运行时。

## Skill 应该表达什么

### Goal

告诉 Codex：

- 这个 skill 的目标是把用户需求送入 Agent Team workflow
- 不要把整个需求塌缩成一个 Dev-only 执行路径
- 不要让 skill 自己决定是否跳过 QA、Acceptance 或人工审批

### When To Use

告诉 Codex：

- 哪些自然语言触发词应该使用这个 skill
- 哪些场景不应该使用这个 skill
- 如果当前 workspace 没有 runtime，应该明确报 blocked，而不是假装流程已接入

### Available assets

告诉 Codex 资产在哪里、用途是什么，但不要把 SKILL.md 写成脚本教程。

例如可以表达为：

- `scripts/` 里有 skill 自带的 bootstrap helper
- 项目根目录的 `scripts/` 里可能有 runtime helper
- `agent-team` 是对外 CLI 入口
- session artifact 和 review 会落到 runtime state 目录

不推荐在 SKILL.md 里写死一长串必须执行的命令流程。

命令级细节更适合放在操作文档里，例如：

- `Codex 运行 Help`
- `CLI 使用说明`

## Skill 不应该做什么

- 不应该自己维护 stage 状态
- 不应该自己决定跳过 `QA`
- 不应该自己宣布最终 Go / No-Go
- 不应该把 Dev 自测当作 QA 独立验证
- 不应该把 deterministic metadata 当作真实验收证据
- 不应该依赖绝对路径或用户机器专属路径

## Root Skill 与 Installable Skill 的区别

当前仓库里有两类 skill：

### 1. 仓库内 Root Skill

适合在 runtime 仓库本身里使用。

它可以描述：

- 仓库内的角色资产
- 项目级 helper
- 生成出来的本地 agent / local run skill

### 2. Installable Skill

适合复制到 `Codex` 的 skill 目录后使用。

它应该优先描述：

- 自身 `scripts/` 目录里的 bootstrap helper
- vendored runtime 或当前 workspace runtime 的发现逻辑
- 如果 runtime 缺失，明确报 blocked

Installable Skill 要特别避免写成依赖仓库内部固定目录的说明。

## 当前接入建议

如果目标是在 `Codex App` 里接入这套 harness，推荐做法是：

1. 保持 `agent-team` 为唯一对外 CLI 入口
2. skill 只负责识别触发意图和说明边界
3. 真实流程推进全部通过 `agent-team` 完成
4. 角色 overlay 学习继续通过 `record-feedback` 回流
5. 让 Codex 在同一个 session 里读取 contract、执行阶段、提交 bundle

## Completion Signals

这类 skill 接入完成的信号应该是：

- Codex 能从 skill 正确识别何时使用 `Agent Team` workflow
- Codex 知道 `agent-team` 而不是 skill 本身负责流程推进
- Codex 知道等待态必须停下并等待人工决策
- Codex 知道 `record-feedback` 会把问题回流到后续 contract
- SKILL.md 仍然保持 goal-oriented，而不是退化成命令抄写板
