# AI_Team CLI Runtime

`AI_Team` 是一个通过 CLI 暴露、对 AI 友好的工程化团队编排运行时。

它的目标不是做一组 prompt，也不是做一个只会演示流程的 skill 样例，而是做一个可以持续演进的 runtime：

- 对外是一个 CLI 产品
- 对内是一套可扩展的 orchestration framework
- 默认内置 Product / Dev / QA / Acceptance 团队
- 能把反馈、返工、证据和人工决策沉淀为可复用的运行时资产

## 项目定位

这个项目要解决的问题是：

- 让 AI 团队以工程化方式运行，而不是只靠对话里的约定运行
- 让产品、研发、测试、验收有明确边界，而不是在一个 agent 里混成一团
- 让流程推进、返工、等待人工审批、证据要求都由 runtime 控制
- 让团队行为可以被记录、被学习、被扩展、被替换

一句话定义：

`AI_Team` 是一个 CLI-first 的 AI team orchestration runtime。

## 核心目标

- 通过 `ai-team` CLI 驱动整套流程
- 内置一个可自我进化的产品-研发-测试-验收团队
- 用状态机和 artifact contract 约束流程
- 支持可扩展的角色、阶段、规则和学习回流
- 让 skill 从“流程控制器”降级为“入口与 prompt 素材”

## 当前团队模型

当前默认团队是：

- `Product`
- `Dev`
- `QA`
- `Acceptance`
- `Ops`

当前权威流程链路是：

`Product -> CEO approval -> Dev <-> QA -> Acceptance -> human Go/No-Go`

这意味着：

- Product 负责产出 PRD 和验收标准
- Dev 负责实现和自验证
- QA 必须独立验证，不能被 Dev 自测替代
- Acceptance 负责产品级验收建议
- 最终 human Go/No-Go 必须由人来决定

## 框架结构

从框架角度看，当前仓库由四层构成：

### 1. CLI Runtime

CLI 是用户和上层 AI 的统一入口。

当前主入口是：

```bash
ai-team
```

已经落地的主要命令：

- `ai-team start-session`
- `ai-team current-stage`
- `ai-team resume`
- `ai-team build-stage-contract`
- `ai-team submit-stage-result`
- `ai-team record-human-decision`
- `ai-team record-feedback`
- `ai-team review`

### 2. Session Runtime

运行时负责：

- 创建 session
- 持久化 session 状态
- 维护当前阶段和当前状态
- 保存 artifact、journal、findings、feedback
- 记录人工决策
- 回写学习内容

### 3. Team Contract Layer

这一层定义：

- 每个阶段的目标
- 必需产物
- 禁止动作
- 证据要求
- 当前输入资产

worker 看到的是 stage contract，不是自由发挥的任务描述。

### 4. Role Asset Layer

角色目录和 skill 文件仍然保留，但现在更偏向“角色资产”和“prompt 素材”：

- `Product/`
- `Dev/`
- `QA/`
- `Acceptance/`
- `Ops/`
- `SKILL.md`
- `codex-skill/ai-company-workflow/`

## 当前已实现的运行时能力

当前分支已经落地的能力包括：

- app-local 的 workspace 级状态目录
- 显式 stage machine
- stage contract 生成
- stage-result bundle 提交
- wait state 下的人工决策
- feedback 到 memory overlay 的学习回流
- 可安装的 `ai-team` CLI

当前默认状态目录：

```text
$CODEX_HOME/ai-team/workspaces/<workspace_fingerprint>/
```

如果没有设置 `CODEX_HOME`，则回退到：

```text
~/.codex/ai-team/workspaces/<workspace_fingerprint>/
```

## 当前未完成的部分

当前这套 runtime 还不是最终形态，未完成部分主要包括：

- 自动 worker dispatch
- 更完整的 supervisor loop
- 原生 Codex 插件体验
- 更完整的扩展注册机制
- 可视化审批和 timeline

所以当前最准确的理解是：

它已经能稳定地“控流程”，但还没有完全自动地“跑流程”。

## 安装与使用

推荐通过 GitHub Releases 安装正式版本。

安装前提：

- Python 3.13+
- `curl`
- `shasum` 或 `sha256sum`

安装最新版本：

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/AI_Team/releases/latest/download/install.sh | sh
```

安装固定版本：

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/AI_Team/releases/download/v0.1.0/install.sh | sh
```

安装完成后，稳定命令入口是：

```bash
~/.local/bin/ai-team
```

如果你需要安装随包分发的 Codex skill：

```bash
ai-team install-codex-skill
```

当前版本发布资产包括 `wheel`、源码包、`install.sh`、`SHA256SUMS` 和版本级 `CHANGELOG.md`。

如果你是在仓库里做开发，再使用本地 editable 安装：

```bash
pip install -e .
```

启动一个 session：

```bash
ai-team start-session --message "执行这个需求：<你的需求>"
```

查看当前阶段：

```bash
ai-team current-stage --session-id <session_id>
```

生成阶段 contract：

```bash
ai-team build-stage-contract --session-id <session_id> --stage Product
```

提交阶段结果：

```bash
ai-team submit-stage-result --session-id <session_id> --bundle /path/to/bundle.json
```

记录人工决策：

```bash
ai-team record-human-decision --session-id <session_id> --decision go
```

在 `Codex App` 里运行时，推荐把这套系统理解成：

- `ai-team` 负责控流程、发 contract、收 bundle、记状态
- Codex 负责按当前 stage contract 执行真实工作并提交结果
- 当前能稳定支持“最小 harness 循环”，还不是一条命令全自动跑完所有角色

## 仓库结构

核心目录：

- `ai_company/`
  - 当前 runtime 核心实现
- `Product/`, `Dev/`, `QA/`, `Acceptance/`, `Ops/`
  - 角色资产
- `scripts/`
  - 项目级 helper
- `codex-skill/`
  - 可安装 skill 包装层
- `docs/workflow-specs/`
  - 运行时设计、流程和使用文档
- `tests/`
  - 运行时、文档和打包测试

虽然当前内部包名还是 `ai_company`，但对外产品定义已经切到 `AI_Team CLI Runtime`。后续如果继续推进，会再单独做一次运行时包名迁移。

## 核心文档

- [运行时设计](docs/workflow-specs/2026-04-11-ai-team-cli-runtime-design.md)
- [当前流程说明](docs/workflow-specs/2026-04-11-ai-team-cli-runtime-flow.md)
- [CLI 使用说明](docs/workflow-specs/2026-04-11-ai-team-cli-runtime-usage.md)
- [变更记录](CHANGELOG.md)
- [Codex 运行 Help](docs/workflow-specs/2026-04-11-ai-team-codex-cli-help.md)
- [Codex Harness 方案](docs/workflow-specs/2026-04-11-ai-team-codex-harness-solution.md)
- [Skill 接入说明](docs/workflow-specs/2026-04-11-ai-team-skill-integration.md)

## 当前原则

- CLI 是用户主入口
- runtime 是流程事实来源
- skill 不是流程控制器
- evidence 不完整就不能算通过
- Acceptance 只能建议，不能代替人工决策
- 学习回流必须落到工程化状态，而不是只留在对话记忆里

## 一句话总结

`AI_Team` 现在应该被理解成一个面向 AI 的 CLI 编排运行时，而不是一个“会写代码的 prompt 套装”。
