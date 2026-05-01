# Agent Team CLI Runtime

`Agent Team CLI Runtime` 是一个 CLI-first、可自我进化的 AI agent team orchestration runtime（编排运行时）。它不是一个 prompt 集合，不是流程演示 skill，而是一个可以持续演进的**运行时引擎**：

- 对外是 CLI 产品（`agent-team` 命令）
- 对内是可扩展的 orchestration framework
- 内置 Product / Dev / QA / Acceptance 角色
- 用状态机 + artifact contract 约束流程
- 反馈、返工、证据和人工决策沉淀为可复用资产

`agent-team` 是可选的多角色协议层，不替代仓库原有的 AI 问答式开发。团队里有人使用 `agent-team` 跑需求、会话和验收链路时，其他人仍然可以按普通 AI 辅助开发方式直接读代码、改代码、跑测试；只有明确进入 `agent-team` session 的工作才受状态机和 artifact contract 约束。

## 一句话定义

**一个把"多人 AI agent 协作"装进状态机的 CLI 运行时。**

---

## 架构总览

```
┌─────────────────────────────────────────────────┐
│                  交互层                          │
│  ┌──────────────────┐  ┌──────────────────────┐ │
│  │  人类模式         │  │  AI/Agent 模式       │ │
│  │  agent-team dev      │  │  acquire→submit→     │ │
│  │  需求→技术→执行    │  │  verify（不改状态机） │ │
│  └────────┬─────────┘  └──────────┬───────────┘ │
│           │                       │              │
│           └───────────┬───────────┘              │
│                       │                          │
├───────────────────────┼──────────────────────────┤
│                  状态机层                         │
│  Intake → Product → CEO → Dev ⇄ QA → Acceptance │
│                       │     → WaitForHuman       │
│                       │                          │
├───────────────────────┼──────────────────────────┤
│                  执行层                           │
│  ┌────────────────────────────────────────────┐  │
│  │  StageExecutor (Protocol)                  │  │
│  │  ├── CodexExecutor    (codex exec)         │  │
│  │  ├── ClaudeCodeExecutor (claude --print)   │  │
│  │  └── (future) ...                          │  │
│  └────────────────────────────────────────────┘  │
│                       │                          │
├───────────────────────┼──────────────────────────┤
│                  提示词层                         │
│  Layer 1: 通用保护 (SCOPE+SECURITY+INTEGRITY)   │
│  Layer 2: 角色指令 (Dev/QA/Acceptance 分支)      │
│  Layer 3: 阶段上下文 (alignment+artifacts...)    │
│  Layer N: (future) 合规/调试/行业特化            │
│                       │                          │
├───────────────────────┼──────────────────────────┤
│                 Gate 验证层                       │
│  GateEvaluator → hard gates + optional AI judge  │
│  → PASS 推进状态机 / FAIL 回退 / BLOCKED 停住    │
└─────────────────────────────────────────────────┘
```

---

## 两种交互模式

### 人类模式 —— `agent-team dev`

一条命令走完：需求对齐 → 技术方案讨论 → Agent 链执行。

```bash
agent-team dev
# Phase 1: 需求对齐——你说要做什么，AI 帮你结构化验收标准，你确认
# Phase 2: 技术方案——AI 分析代码库，提方案，你确认
# 决策点：是否委托 Agent 执行？
#   [y] 启动 Dev → QA → Acceptance Agent 链
#   [m] 手动执行（保留 session，自己提交）
# Phase 3: Agent 链自动执行
#   Product Agent → Dev Agent → QA Agent(空沙箱) → Acceptance Agent
#   停在 WaitForHumanDecision，等你最终确认

# 快捷入口
agent-team dev --message "实现一个 OAuth 登录页面"

# 指定执行器
agent-team dev --executor claude-code
```

### AI/Agent 模式 —— 细粒度 CLI 调用

AI（Codex、Claude Code）可以作为 worker 调用 runtime，但不能控制状态机。

```bash
# Agent 创建 session
agent-team start-session --initiator agent --message "..."

# Agent 领取任务
agent-team acquire-stage-run --session-id xxx --stage Dev --worker codex

# Agent 完成工作后提交
agent-team submit-stage-result --session-id xxx --bundle result.json

# Runtime 验证并推进状态机
agent-team verify-stage-result --session-id xxx

# Agent 不能做这些：
# ✗ record-human-decision   ← 只有人类 initiator 可以
# ✗ 直接修改 session 状态   ← Runtime 管
# ✗ 跳过 QA 或 Acceptance   ← 状态机强制
```

---

### 普通 AI 问答式开发

不需要多角色会话、QA 独立验收或人工 Go/No-Go 的改动，可以继续使用原始 AI 问答式开发。此时不需要创建 `.agent-team/` session，也不需要生成 `.codex/agents/` 或 `.agents/skills/`；按仓库已有说明、代码结构和测试命令完成即可。

如果同一个需求已经进入 `agent-team` session，则该需求的 PRD、实现、QA 和验收证据应回写到对应 session artifact，避免普通问答记录和 Agent Team 状态机同时声明同一变更的完成状态。

---

## 执行器抽象

Executor 是"把提示词交给 AI CLI 执行"的薄封装层。不是业务抽象，只是子进程调用的统一接口。

```python
class StageExecutor(Protocol):
    def execute(self, *, prompt: str, output_dir: Path, stage: str) -> ExecutorResult:
        ...
```

| 实现 | CLI | 特点 |
|---|---|---|
| `CodexExecutor` | `codex exec --json` | 内置沙箱、workspace-write 模式 |
| `ClaudeCodeExecutor` | `claude --print` | 非交互式、可指定工具集 |
| *(future)* | Gemini CLI、本地模型等 | 实现 Protocol 即插即用 |

**为什么不更抽象：** 只抽象到"执行 prompt、返回 JSON"这一层。不做 prompt 生成、不做状态管理、不做编排。这些是上层的事。

---

## Agent 链：Dev → QA → Acceptance

```
  Dev Agent                     QA Agent                      Acceptance Agent
  ─────────                     ────────                      ─────────────────
  沙箱: workspace-write         沙箱: CLEAN (独立)             沙箱: CLEAN (独立)
  输入: alignment + tech_plan   输入: 只有 Dev 的产出文件       输入: 全量 paper trail
       + PRD                          + alignment + PRD             alignment → PRD
  任务: 实现功能                 任务: 从零重建 + 独立验证         → Dev → QA
  产出: implementation.md       产出: qa_report.md             任务: 最终 go/no-go 建议
                                      (passed|failed|blocked)  产出: acceptance_report.md
```

关键约束：
- **QA 不能信任 Dev 的自评**——必须在空沙箱从零重建、独立运行测试
- **QA 不通过 → 自动回 Dev**——状态机把 QA 反馈路由回 Dev
- **Acceptance 只建议不决策**——最终 Go/No-Go 由人决定

---

## Agent 提示词保护层

每个 stage agent 的提示词按三层组装，借鉴 Claude Code 的分段设计：

| 层 | 内容 | 适用范围 | 修改成本 |
|---|---|---|---|
| **Layer 1: 通用保护** | SCOPE（不越界）、SECURITY（OWASP）、INTEGRITY（不伪造结果）、BOUNDARY（不改状态机） | 所有 agent 相同 | 改一个函数 |
| **Layer 2: 角色指令** | Dev 怎么做自验证、QA 怎么独立验证、Acceptance 怎么 cross-reference | 按 stage 分支 | 改对应分支函数 |
| **Layer 3: 阶段上下文** | alignment、tech plan、PRD、前面 stage 的 artifact | 纯数据注入 | 加新字段即可 |
| *(future)* | 合规层、调试层、行业特化层 | 按需插入 | 加一个函数调用 |

---

## 状态机

```
Intake → ProductDraft → WaitForCEOApproval → Dev ⇄ QA → Acceptance → WaitForHumanDecision → Done
                            │                                │
                         [go/rework/no-go]              [go/rework/no-go]
```

Product -> CEO approval -> Dev <-> QA -> Acceptance -> human Go/No-Go

- **Gate verify 通过** → 自动推进
- **Wait 状态** → 必须人工决策
- **QA failed** → 自动回 Dev（带 QA 反馈）
- **Blocked** → 停住等人工介入

---

## 安装与使用

```bash
# 安装最新版本
curl -fsSL https://github.com/ZHOUKAILIAN/agent-team-runtime/releases/latest/download/install.sh | sh

# 固定版本安装
curl -fsSL https://github.com/ZHOUKAILIAN/agent-team-runtime/releases/download/v0.1.0/install.sh | sh

# 安装后命令
~/.local/bin/agent-team

# Python 3.13+

# 开发安装
pip install -e .
```

---

## CLI 命令

### 人类交互

| 命令 | 说明 |
|---|---|
| `agent-team dev` | 交互式开发：需求对齐 → 技术方案 → Agent 链执行 |
| `agent-team dev --message "..."` | 跳过需求输入，直接进入对齐 |
| `agent-team dev --executor claude-code` | 指定执行器 |

### Session 管理

| 命令 | 说明 |
|---|---|
| `agent-team start-session --message "..."` | 创建 session |
| `agent-team start-session --initiator human\|agent` | 指定发起者类型 |
| `agent-team status --session-id <id>` | 项目/角色/状态摘要 |
| `agent-team current-stage --session-id <id>` | 当前阶段和状态 |
| `agent-team step --session-id <id>` | 打印下一步动作 |
| `agent-team resume --session-id <id>` | 恢复查看 |

### Stage 执行（AI worker 用）

| 命令 | 说明 |
|---|---|
| `agent-team acquire-stage-run --session-id <id> --stage <name>` | 认领 stage |
| `agent-team submit-stage-result --session-id <id> --bundle <path>` | 提交候选结果 |
| `agent-team verify-stage-result --session-id <id>` | 验证并推进状态机 |
| `agent-team build-stage-contract --session-id <id> --stage <name>` | 生成 stage contract |

### 人类决策（仅人类 initiator 可用）

| 命令 | 说明 |
|---|---|
| `agent-team record-human-decision --session-id <id> --decision go\|no-go\|rework` | 人工决策 |
| `agent-team record-feedback --session-id <id> ...` | 反馈 + 学习回流 |

### 可观测性

| 命令 | 说明 |
|---|---|
| `agent-team panel --session-id <id> --port 8765` | 本地 Web panel |
| `agent-team panel-snapshot --session-id <id>` | JSON snapshot |
| `agent-team board-snapshot --all-workspaces` | 多工作区看板 |
| `agent-team serve-board --all-workspaces` | Board HTTP server |
| `agent-team review --session-id <id>` | Session review |

`agent-team panel` 和 `agent-team serve-board` 启动同一个 React Runtime Console：第一层是项目地图，进入项目后是阶段看板式项目工作台，再进入单个会话查看需求流程、证据、产物和事件流。前端位于 `apps/web`，使用 React + Vite + Tailwind；Python 侧提供 REST snapshot、WebSocket 实时连接和静态资源托管。开发时可运行 `npm run dev:web`，发布前运行 `npm run build` 将前端产物复制到 Python 包资源目录。

### 项目初始化

| 命令 | 说明 |
|---|---|
| `agent-team codex-init` | 生成项目级 Codex agent 配置 |

---

## 设计原则

- **状态机是唯一权威** —— 流程推进只有 gate verify 和 human decision 两个入口
- **AI 是 worker，不是 controller** —— AI 执行工作、提交结果，但无权改状态机
- **Evidence 不完整 = 不通过** —— QA 必须有独立命令和输出作为证据
- **Acceptance 只建议不决策** —— 最终 Go/No-Go 由人决定
- **Agent 提示词自包含** —— 每个 agent 的 prompt 包含完成任务所需的全部信息
- **保护层永远最先加载** —— 在 agent 知道自己是"Dev"还是"QA"之前，先戴上紧箍咒
- **学习回流落到文件** —— 反馈和学习记录持久化到 .agent-team/memory/，不依赖对话记忆

---

## 当前状态

**已实现：**
- 完整状态机 + artifact contract
- CLI 全命令体系
- Gate evaluator + 可选 AI judge
- Web panel / board 可观测性
- Codex skill 安装和项目脚手架
- 角色 skill 文件（Product/Dev/QA/Acceptance/Ops）
- 测试套件（27 个测试文件）

**设计中（v2 计划）：**
- `agent-team dev` 人类交互命令
- Session initiator 权限边界
- 执行器抽象（Codex + Claude Code）
- Agent 提示词分层架构 + 保护层
- Dev/QA/Acceptance 专用提示词（含空沙箱验证）

---

## 仓库结构

```
agent-team-runtime/
├── agent_team/            ← runtime 核心（Python）
│   ├── cli.py             ← CLI 入口
│   ├── stage_machine.py   ← 状态机
│   ├── state.py           ← 状态持久化
│   ├── stage_contracts.py ← stage contract 生成
│   ├── gate_evaluator.py  ← 验证评估
│   ├── orchestrator.py    ← 编排器
│   └── assets/            ← 打包资源
├── Product|Dev|QA|Acceptance|Ops/  ← 角色资产
├── docs/superpowers/      ← 设计文档和计划
├── tests/                 ← 测试套件
├── scripts/               ← Helper 脚本
└── README.md
```

> Python 包名为 `agent_team`，CLI 入口为 `agent-team`。对外命名统一使用 `agent-team`。

---

## 文档

- [v2 实现计划](docs/superpowers/plans/2026-04-29-agent-team-run-interactive-v2.md)
- [v1 实现计划](docs/superpowers/plans/2026-04-29-agent-team-run-interactive.md)
- [run-interactive 设计](docs/superpowers/specs/2026-04-29-agent-team-run-interactive-design.md)
- [CLI 运行时设计](docs/workflow-specs/2026-04-11-agent-team-cli-runtime-design.md)
- [Codex 运行 Help](docs/workflow-specs/2026-04-11-agent-team-codex-cli-help.md)
- [Skill 接入说明](docs/workflow-specs/2026-04-11-agent-team-skill-integration.md)
- [Codex Harness 方案](docs/workflow-specs/2026-04-11-agent-team-codex-harness-solution.md)
- [CHANGELOG.md](CHANGELOG.md)
