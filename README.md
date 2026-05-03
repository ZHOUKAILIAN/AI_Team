# Agent Team CLI Runtime

`Agent Team` 是一个通过 CLI 暴露、对 AI 友好的工程化团队编排运行时。

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

`Agent Team` 是一个 CLI-first 的 AI team orchestration runtime。

## 核心目标

- 通过 `agent-team` CLI 驱动整套流程
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
- Dev 负责实现、代码自 review 和自验证
- QA 必须独立验证，不能被 Dev 自测替代
- Acceptance 负责产品级验收建议
- 最终 human Go/No-Go 必须由人来决定

## 框架结构

从框架角度看，当前仓库由四层构成：

### 1. CLI Runtime

CLI 是用户和上层 AI 的统一入口。

当前主入口是：

```bash
agent-team
```

已经落地的主要命令：

- `agent-team dev`
- `agent-team start-session`
- `agent-team status`
- `agent-team current-stage`
- `agent-team resume`
- `agent-team step`
- `agent-team panel-snapshot`
- `agent-team panel`
- `agent-team build-stage-contract`
- `agent-team acquire-stage-run`
- `agent-team submit-stage-result`
- `agent-team verify-stage-result`
- `agent-team record-human-decision`
- `agent-team record-feedback`
- `agent-team board-snapshot`
- `agent-team serve-board`
- `agent-team review`
- `agent-team skill list`

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

角色目录和内置角色资产仍然保留，但它们只是 context / contract 素材，不再作为 workflow 控制器：

- `Product/`
- `Dev/`
- `QA/`
- `Acceptance/`
- `Ops/`
- `agent_team/assets/roles/`
- `agent_team/assets/skills/`

## 当前已实现的运行时能力

当前分支已经落地的能力包括：

- 仓库内 `.agent-team/` 单目录状态
- 显式 stage machine
- stage contract 生成
- stage-run acquire / submit / verify 强制流转
- runtime driver 逐阶段执行 `contract -> context -> acquire -> execute -> submit -> verify -> advance`，并写入 `<run_id>_trace.json`
- stage-result candidate bundle 提交
- wait state 下的人工决策
- feedback 到三层 memory 的学习回流：`raw/` 原始记录、`extracted/` 可执行规则、`graph/` 关联边
- role memory 先用 CLI 关键词检索，再把命中的 raw/extracted/graph 片段压进 stage contract；隐含关系才需要后续 AI/图分析
- 事件流驱动的 panel snapshot
- 本地只读 Web panel
- 可安装的 `agent-team` CLI

当前默认状态目录：

```text
<repo-root>/.agent-team/
```

session 文件集中在：

```text
<repo-root>/.agent-team/<session_id>/
```

长期学习内容放在 `<repo-root>/.agent-team/memory/`。每个角色下保留 memory overlay，以及三层结构：

```text
<repo-root>/.agent-team/memory/<Role>/raw/findings.jsonl
<repo-root>/.agent-team/memory/<Role>/extracted/{lessons,context_patch,skill_patch}.md
<repo-root>/.agent-team/memory/<Role>/graph/relations.jsonl
```

runtime 不再默认拆出 repo 外的 `workspaces/`、`artifacts/`、`sessions/` 多层目录。

## 当前边界

当前这套 runtime 已经能用 `run-requirement` 自动驱动 Product/Dev/QA/Acceptance，并在人工 gate 处停住。仍在演进的部分主要包括：

- 原生 Codex 插件体验
- 更完整的扩展注册机制
- 可视化审批和 timeline

所以当前最准确的理解是：

它已经用 runtime 强制“控流程”和“跑流程”；PRD 审批与最终 Go/No-Go 仍由人卡控，`--auto` 只自动穿过中间阶段。

## 安装与使用

推荐通过 GitHub Releases 安装正式版本。beta 版本会以 GitHub pre-release 发布，不会覆盖 latest。

安装前提：

- Python 3.13+
- `curl`
- `shasum` 或 `sha256sum`

安装最新版本：

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/agent-team-runtime/releases/latest/download/install.sh | sh
```

安装当前 beta 版本：

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/agent-team-runtime/releases/download/v0.2.0b4/install.sh | sh
```

安装固定版本：

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/agent-team-runtime/releases/download/v0.1.0/install.sh | sh
```

安装完成后，稳定命令入口是：

```bash
~/.local/bin/agent-team
```

当前版本发布资产包括 `wheel`、源码包、`install.sh`、`SHA256SUMS` 和版本级 `CHANGELOG.md`。

如果你是在仓库里做开发，再使用本地 editable 安装：

```bash
pip install -e .
```

### 在自己的项目里试一次

安装完成后，先确保 `agent-team` 在 PATH 里：

```bash
export PATH="$HOME/.local/bin:$PATH"
agent-team --help
```

进入一个真实项目仓库后初始化运行时目录和项目文档结构：

```bash
cd /path/to/your/project
agent-team init
```

如果本机已经安装并登录 Codex CLI，可以用默认 `codex-exec` 真实跑一条需求：

```bash
agent-team run-requirement --message "写个js文件，并打印agent-team-runtime" --auto
```

如果只想先验证安装和 workflow 文件生成，不调用 Codex：

```bash
agent-team run-requirement --message "写个js文件，并打印agent-team-runtime" --executor deterministic --auto
```

### Interactive terminal workflow

```bash
cd /path/to/project
agent-team dev
```

`agent-team dev` prompts for the requirement, confirms acceptance criteria, asks for a technical plan confirmation, and then can delegate Product / Dev / QA / Acceptance execution through `codex exec` while preserving runtime gates.

默认执行器是 Codex；也可以切到 Claude Code：

```bash
agent-team dev --executor claude-code
```

如果只想让某些阶段使用不同执行器：

```bash
agent-team dev --dev-executor codex --qa-executor claude-code
```

`agent-team dev` 支持在 Phase 2 技术方案确认后选择 stage skills。首次默认空选，后续会从 `.agent-team/skill-preferences.yaml` 读取上次偏好。

```bash
agent-team skill list
agent-team skill show security-audit
agent-team skill preferences
agent-team dev --with-skills dev:plan --with-skills qa:security-audit
agent-team dev --skills-empty
```

启动一个 session：

```bash
agent-team run-requirement --message "执行这个需求：<你的需求>"
```

默认 executor 是 `codex-exec`，runtime 会逐阶段调用 `codex exec`，并在每个阶段之后提交和验证 `StageResultEnvelope`。每个 stage-run 会生成 `<run_id>_trace.json`，记录不可跳过的 `contract_built`、`execution_context_built`、`stage_run_acquired`、`executor_started`、`executor_completed`、`result_submitted`、`gate_evaluated`、`state_advanced` 链路。Product 完成后默认停在 `WaitForCEOApproval`；如果你想在确认 PRD 后自动流转到 Acceptance 并完成交付，可以加：

```bash
agent-team run-requirement --message "执行这个需求：<你的需求>" --auto
```

测试或离线演示可以用 deterministic executor：

```bash
agent-team run-requirement --message "执行这个需求：<你的需求>" --executor dry-run
```

继续一个已经通过 PRD 审批的 session：

```bash
agent-team run-requirement --session-id <session_id> --auto
```

查看当前阶段：

```bash
agent-team current-stage --session-id <session_id>
```

查看当前下一步动作：

```bash
agent-team step --session-id <session_id>
```

`step` 会打印下一步动作以及当前 contract 的 `contract_id`、`required_outputs` 和 `required_evidence`。

查看用户友好的状态摘要：

```bash
agent-team status --session-id <session_id>
```

输出会同步展示当前项目、当前角色和当前状态；同一份内容也会写入 `.agent-team/<session_id>/status.md` 供复盘。

查看机器可读的 panel snapshot：

```bash
agent-team panel-snapshot --session-id <session_id>
```

打开本地只读 panel：

```bash
agent-team panel --session-id <session_id> --port 8765
```

生成阶段 contract：

```bash
agent-team build-stage-contract --session-id <session_id> --stage Product
```

认领当前 stage run：

```bash
agent-team acquire-stage-run --session-id <session_id> --stage Product
```

提交阶段候选结果：

```bash
agent-team submit-stage-result --session-id <session_id> --bundle /path/to/bundle.json
```

验证候选结果并决定是否推进 workflow：

```bash
agent-team verify-stage-result --session-id <session_id>
```

候选 bundle 里的 `evidence` 必须是结构化对象，runtime 会按 contract 的 `evidence_specs` 校验证据名称、类型和必填字段。

记录人工决策：

```bash
agent-team record-human-decision --session-id <session_id> --decision go
```

把人工反馈同时作为 rework 决策回流到目标阶段：

```bash
agent-team record-feedback --session-id <session_id> --source-stage Acceptance --target-stage Dev --issue "<issue>" --apply-rework
```

输出只读看板 JSON：

```bash
agent-team board-snapshot --all-workspaces
```

启动本地只读看板：

```bash
agent-team serve-board --all-workspaces --port 8765 --poll-interval 5
```

只读看板只观察 runtime state，不提供 approve、verify、submit、rework 等写操作。

在 `Codex App` 里运行时，推荐把这套系统理解成：

- `agent-team` 负责控流程、发 contract、认领 run、收 candidate bundle、做 gate 验证、记状态
- `agent-team panel` 把当前 action、阻塞原因、证据缺口和最近 timeline 可视化出来
- Codex 负责按当前 stage contract 执行真实工作并提交结果
- 当前能稳定支持“最小 harness 循环”，还不是一条命令全自动跑完所有角色

## 仓库结构

核心目录：

- `agent_team/`
  - 当前 runtime 核心实现
- `Product/`, `Dev/`, `QA/`, `Acceptance/`, `Ops/`
  - 角色资产
- `scripts/`
  - 项目级 helper
- `docs/workflow-specs/`
  - 运行时设计、流程和使用文档
- `tests/`
  - 运行时、文档和打包测试

内部 Python 包名和模块入口均为 `agent_team`，对外 CLI 入口为 `agent-team`。

## 核心文档

- [运行时设计](docs/workflow-specs/2026-04-11-agent-team-cli-runtime-design.md)
- [当前流程说明](docs/workflow-specs/2026-04-11-agent-team-cli-runtime-flow.md)
- [CLI 使用说明](docs/workflow-specs/2026-04-11-agent-team-cli-runtime-usage.md)
- [变更记录](CHANGELOG.md)
- [版本发布页](https://github.com/ZHOUKAILIAN/agent-team-runtime/releases)
- [Codex 运行 Help](docs/workflow-specs/2026-04-11-agent-team-codex-cli-help.md)
- [Codex Harness 方案](docs/workflow-specs/2026-04-11-agent-team-codex-harness-solution.md)
- [Stage 资产说明](docs/workflow-specs/2026-04-11-agent-team-skill-integration.md)

## 当前原则

- CLI 是用户主入口
- runtime 是流程事实来源
- skill 不是流程控制器
- evidence 不完整就不能算通过
- Acceptance 只能建议，不能代替人工决策
- 学习回流必须落到工程化状态，而不是只留在对话记忆里

## 一句话总结

`Agent Team` 现在应该被理解成一个面向 AI 的 CLI 编排运行时，而不是一个“会写代码的 prompt 套装”。
