# Agent Team CLI Runtime

`Agent Team` 是一个 CLI-first 的 AI team orchestration runtime。它的目标不是提供一组 prompt，而是用状态机、stage contract、证据 gate 和可回放运行态，把 AI 团队工作约束成可审计、可恢复、可自我进化的工程流程。

## 定位

- 对外主入口是 `agt` CLI，完整命令仍兼容 `agent-team`。
- 对内是可扩展的 orchestration runtime。
- 默认运行五层九阶段流程，而不是旧的 Product / Dev / QA 三角色串联。
- 反馈、返工、证据、人工决策和本地接力都会沉淀成运行时资产。

## 根目录约定

- `agt-control/`: 仓库内共享、正式、可提交的 Agent Team 控制面。
- `.agt/`: 本地隐藏的运行态、私有配置、session 状态、memory 和 runtime trace。

## 五层阶段

权威流程链路：

```text
Route -> ProductDefinition approval -> ProjectRuntime -> TechnicalDesign approval -> Implementation -> Verification -> GovernanceReview -> Acceptance -> SessionHandoff -> human Go/No-Go
```

阶段对应关系：

- `Route`: 需求路由，识别 L1/L2/L3/L4/L5 影响、红线和所需阶段。
- `ProductDefinition`: L1 产品定义 delta，只处理稳定产品语义、核心对象、运行模型和长期边界。
- `ProjectRuntime`: L3 项目落地 delta，记录本项目入口、目录、运行、打包和默认承载方式。
- `TechnicalDesign`: L2 技术设计，基于 L1/L3 和当前实现现实制定实现方案。
- `Implementation`: L2 实现现实，修改代码、测试、运行脚本并记录自检证据。
- `Verification`: 独立验证实现结果，不能被 Implementation 自测替代。
- `GovernanceReview`: L4 仓库治理审查，检查五层边界、证据、回写和 public/private 风险。
- `Acceptance`: AI 最终验收建议，不代替人的最终决策。
- `SessionHandoff`: L5 本地开发控制层，保留接力、未决项和本地现场。

下层依赖上层：低层只能报告 drift 或 delta，不能反向改写上层正式依据。

## CLI

主要命令：

```bash
agt init
agt run --message "<你的需求>"
agt status --session-id <session_id> [--verbose|--json]
agt panel --session-id <session_id> [--json]
agt verify-stage-result --session-id <session_id> [--dry-run]
agt record-human-decision --session-id <session_id> --decision go
agt record-feedback --session-id <session_id> --source-stage Verification --target-stage Implementation --issue "<issue>" --apply-rework
agt skill list|show|preferences|default
```

初始化项目：

```bash
cd /path/to/your/project
agt init
```

`init` 会创建 `agt-control/project/five-layer/` 并准备五层分类 prompt。交互终端默认会尝试调用 `codex exec`，使用 GitHub skill source：

```text
https://github.com/ZHOUKAILIAN/skills/tree/feature/five-layer-classifier-skill/five-layer-classifier
```

非交互式脚本默认跳过实际 Codex 执行，只写入：

```text
agt-control/project/five-layer/classification.md
agt-control/project/five-layer/classification-run.json
agt-control/project/five-layer/classification-prompt.md
```

强制运行或跳过：

```bash
agt init --five-layer-classification run
agt init --five-layer-classification skip
```

## 运行

真实执行默认使用 `codex-exec`：

```bash
agt run --message "写个js文件，并打印agent-team-runtime"
```

离线验证 workflow 文件和 gate：

```bash
agt run --message "写个js文件，并打印agent-team-runtime" --executor dry-run
```

`--auto` 只自动推进非人工 gate。`ProductDefinition`、`TechnicalDesign` 和最终 `SessionHandoff` 仍然需要人工决策：

```bash
agt run --session-id <session_id> --executor dry-run --auto
agt record-human-decision --session-id <session_id> --decision go
```

## Task worktrees

`agt run` 默认不会直接从当前 `HEAD` 继续做，而是先按 clean base 策略创建新的 task worktree 和最小 branch。

- 本地策略文件：`.agt/local/worktree-policy.json`
- 默认 clean base fallback：`["origin/test", "origin/main", "test", "main"]`
- 默认分支格式：`feature/<date>-<slug>`
- 默认 worktree 目录：`.worktrees/`

新 worktree 只复制 AGT 的本地支持状态，不复制历史运行现场：

- 会复制：`.agt/executor-env.json`、`.agt/skill-preferences.yaml`、`.agt/local/`、`.agt/memory/`
- 不会复制：`.agt/session-index.json`、`.agt/_runtime/`、历史 session 产物

`continue` 只会重新打开已经记录到 `.agt/session-index.json` 的 worktree，不会新建 worktree。

## 产物

人类可读 session 产物位于：

```text
<repo-root>/.agt/<session_id>/
```

典型产物：

```text
route-packet.json
product-definition-delta.md
project-landing-delta.md
technical-design.md
implementation.md
verification-report.md
governance-review.md
acceptance-report.md
session-handoff.md
```

机器运行态位于：

```text
<repo-root>/.agt/_runtime/sessions/<session_id>/
```

每个 stage-run 记录不可跳过链路：

```text
contract_built -> execution_context_built -> stage_run_acquired -> executor_started -> executor_completed -> result_submitted -> gate_evaluated -> state_advanced
```

stage 调试文件形如：

```text
_runtime/sessions/<session-id>/roles/<role>/attempt-001/stage-results/<role>-stage-result.json
_runtime/sessions/<session-id>/roles/<role>/attempt-001/execution-contexts/<role>-input-context.json
_runtime/sessions/<session-id>/roles/<role>/attempt-001/command-outputs/<role>-command-stdout.txt
```

## Skill defaults and runtime workflow

`.agt/skill-preferences.yaml` 保存每个阶段的默认 skill、上次选择和使用频率。

```bash
agt skill list
agt skill show security-audit
agt skill preferences
agt skill default Implementation plan
agt skill default Verification security-audit
agt skill default Acceptance e2e-coverage-guard
```

单次覆盖：

```bash
agt run --message "<你的需求>" --with-skills Implementation:plan --skip-skills Verification:security-audit
agt run --message "<你的需求>" --skills-empty
```

每次注入的 skill 会记录在 stage result 的 `steps[].details.skill_injection` 中，包含 skill 名称、source type、source ref、scope、delivery、installed path，以及是否进入 prompt。`codex-exec` 会记录 prompt 注入；command executor 会记录 command-only execution path；超时后恢复已写出的 result bundle 时会标记 artifact recovery 和 `result_parse_status=recovered_after_timeout`。

## 安装

前提：

- Python 3.13+
- `curl`
- `shasum` 或 `sha256sum`
- 能访问 GitHub Releases 和 PyPI

安装最新版本：

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/agent-team-runtime/releases/latest/download/install.sh | sh
```

安装固定版本：

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/agent-team-runtime/releases/download/v0.1.0/install.sh | sh
```

开发安装：

```bash
pip install -e .
```

## 核心文档

- [运行时设计](docs/workflow-specs/2026-04-11-agent-team-cli-runtime-design.md)
- [当前流程说明](docs/workflow-specs/2026-04-11-agent-team-cli-runtime-flow.md)
- [CLI 使用说明](docs/workflow-specs/2026-04-11-agent-team-cli-runtime-usage.md)
- [Codex 运行 Help](docs/workflow-specs/2026-04-11-agent-team-codex-cli-help.md)
- [Codex Harness 方案](docs/workflow-specs/2026-04-11-agent-team-codex-harness-solution.md)
- [Stage 资产说明](docs/workflow-specs/2026-04-11-agent-team-skill-integration.md)
- [变更记录](CHANGELOG.md)

## 原则

- CLI 是用户主入口。
- runtime 是流程事实来源。
- skill 是阶段能力素材，不是流程控制器。
- evidence 不完整就不能算通过。
- Acceptance 只能建议，不能代替人工决策。
- SessionHandoff 保留 L5 本地现场，但不自动升级为正式共享依据。
