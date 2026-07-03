# Agent Team Runtime

`agent-team-runtime` 是一个 JS/TypeScript 的 AI 研发交付 workflow runtime。它不和 Codex `/goal`、Claude Code 或其他 coding agent 竞争单次执行速度；这些工具是执行器，AGT 是交付协议层。

AGT 的目标是把“一个需求应该如何被交付”固化为可配置、可追踪、可审计、可恢复的 workflow：需求进入后，runtime 先让模型生成初始需求摘要，再负责创建隔离执行环境、组织角色、注入 skills、生成每阶段最小上下文包、调用执行器、保存产物和验证证据，最后给出本地是否完成的交付结论。

CLI 入口按 runtime 版本分开：`agt` 保留 V1/legacy workflow，`agt2`/`agtv2` 只运行 V2 `product-dev-qa` workflow。runtime 自己负责 session、两层 workflow、agent run、tool call 和迁移记录；模型执行通过 OpenAI Agents SDK 的 `SandboxAgent` 完成。没有 OpenAI 环境变量时会自动使用 deterministic local fallback，方便测试和离线验证。

## 产品定位

AGT 是面向 AI 研发交付的可扩展 workflow runtime。

它的核心用户是需要反复把需求推进到本地可验收状态的研发负责人或独立开发者。对这类用户来说，单个 coding agent 已经可以完成很多实现工作，但交付过程仍然需要稳定处理需求边界、隔离 worktree、上下文裁剪、角色分工、独立验证、证据保存和人工判断。

AGT 的定位是把这些交付习惯变成 runtime 规则，而不是每次在聊天里重新说明。

P0 的阶段交接不传完整聊天历史：Product 完成后把需求合同和交接摘要交给 Dev；Dev 完成后把实现报告、自测证据、实现歧义和 QA 交接摘要交给 QA。

### 与 `/goal` 的关系

`/goal` 是研发执行层：给一个目标，让一个强执行器在当前上下文里尽快完成。

AGT 是 workflow 层：定义一个需求进入后应该经过哪些阶段、每个阶段使用什么角色和 skills、阶段之间传递哪些结构化产物、什么时候允许继续、什么时候必须停下来等人判断。

因此 AGT 可以把 Codex `/goal`、Claude Code、OpenAI Agent、DeepSeek agent 或其他执行器作为某个 workflow 节点使用。AGT 负责流程、状态、证据和交付结论；执行器负责具体阶段内的推理、编辑和命令执行。

### P0 完成定义

P0 只要求把一个需求推进到“本地代码改完 + 测试/验证报告完整”。

一次 AGT 需求交付完成，必须至少留下这些证据：

- 需求边界：要做什么、暂不做什么、验收标准是什么。
- 本地实现：在隔离 worktree/branch 中完成代码修改，并记录改动文件。
- 自测记录：记录运行过的测试、检查命令、结果和失败原因。
- QA 验证报告：独立复核需求是否满足，检查边界情况、兼容性、隐藏副作用、未验证项，并给出本地是否完成的结论。

P0 不负责 PR、merge、发布、线上排障或 CST 闭环。这些可以作为后续 workflow 扩展，但不属于最小产品承诺。

## Layer 1 产品定义

按五层模型，Layer 1 只定义稳定产品语义，不描述当前实现细节。

AGT 的产品定义如下：

- AGT 是一个可扩展的 AI 研发交付 workflow runtime。
- AGT 的核心对象是 `workflow`、`role`、`skill`、`context packet`、`artifact`、`executor`、`state` 和 `evidence`。
- `workflow` 定义需求交付路径，例如 `Product -> Dev -> QA`。
- `role` 是 workflow 节点的责任边界，例如产品澄清、开发实现、独立验证、交付验收。
- `skill` 是 role 可注入的可维护能力说明，不是一次性聊天提示。
- `context packet` 是 runtime 为某个 role 生成的最小输入包，用于避免把完整聊天历史传给下游阶段。
- `artifact` 是阶段产物，例如需求边界、实现报告、测试记录和 QA 报告。
- `executor` 是被 AGT 调用的具体执行工具，可以是 Codex `/goal`、Claude Code、OpenAI Agents SDK runner 或其他 agent runtime。
- `state` 是 runtime 维护的机器可读流程状态，不由模型自由生成。
- `evidence` 是支持交付结论的事实记录，包括命令、测试结果、文件变更、prompt trace、agent run 和人工决策。

AGT 的稳定边界是：它负责把需求交付过程协议化、状态化和证据化；它不承诺替代某个 coding agent 的阶段内执行能力。

## 当前能力

下面这一节描述的是当前仓库已经实现的 runtime 能力。V1 和 V2 在代码目录和 CLI 入口上都分开：`agt` 对应 V1，`agt2`/`agtv2` 对应 V2。

- `packages/runtime/src/V1/`：保留旧 runtime 能力，包括 `quick`、`investigate`、`full` profile，以及旧 delivery/execution projector。
- `packages/runtime/src/V2/`：承载新的交付 workflow，目前包含 `product-dev-qa`。
- V1 `quick` profile：面向小需求，按 `planner -> repo_scout -> writer -> verifier -> summarizer` 快速跑完。
- V1 `investigate` profile：面向只查问题不改代码，按 `planner -> repo_scout -> test_scout -> summarizer` 收敛证据。
- V1 `full` profile：面向大需求，保留五层九阶段：`route -> product_definition -> project_runtime -> technical_design -> implementation -> verification -> governance_review -> acceptance -> session_handoff`。
- V2 `product-dev-qa` workflow：面向 P0 本地交付，按 `intake_summary -> product -> product_check -> dev:technical_plan -> dev_plan_check -> dev:implementation -> qa -> done` 执行。
- 每个 session 都写入结构化状态：`session.json`、`delivery-workflow.json`、`execution-workflow.json`、`events.jsonl`、`tool-calls.jsonl`、`agents/*.json`。
- `product-dev-qa` session 额外写入外层状态 `workflow-run.json` 和每阶段审计目录 `stages/*/attempt-*`。
- 旧 runtime 的 session 可以迁移到新 `.agt/sessions/` schema，迁移不会修改旧目录。
- 内置 Fastify API 和 web 静态资源服务，供控制台读取项目、session、事件和工具调用。

源码分层也按 V1/V2 物理隔离：

```text
packages/runtime/src/
  index.ts        # 对外兼容导出，不放实现
  V1/             # 旧 quick / investigate / full runtime
  V2/             # 新 product-dev-qa 交付 workflow

packages/runtime/test/
  V1/
  V2/
```

V1 和 V2 各自保留 `schema`、`store`、`runner`、`skill-routing` 等基础文件；公共逻辑允许重复，优先保证分层边界清楚。

Runtime package 的导入边界也按版本显式区分：

- `@agent-team-runtime/runtime`：只保留 V1 兼容导出，供旧调用方继续使用。
- `@agent-team-runtime/runtime/V1`：V1 runtime 的显式入口。
- `@agent-team-runtime/runtime/V2`：V2 `product-dev-qa` workflow 的显式入口。

V2 命令链路不能从 V1 `RuntimeStore`、V1 config 或 V1 worktree helper 读取状态。CLI 的 V2 入口是 `agt2`/`agtv2`，默认状态目录是 `.agt2`；V1 入口 `agt` 默认状态目录仍然是 `.agt`。跨 worktree 的 `session-index.json` 只是同一版本 runtime 内部的索引文件，不代表 V2 依赖 V1 runtime。

## 安装

前提：

- Node.js 22+
- npm

开发安装：

```bash
npm install
npm run build
```

本地使用 CLI：

```bash
node packages/cli/dist/index.js --help
node packages/cli/dist/V2/index.js --help
node packages/cli/dist/index.js run "整理这个仓库的测试入口"
```

如果通过 npm link 安装，本地命令是：

```bash
npm link
agt --help
```

## 运行任务

快速需求：

```bash
agt run "修一个小问题" --profile quick
```

调查型需求：

```bash
agt run "查一下这个接口为什么慢，不要改代码" --profile investigate
```

完整流程：

```bash
agt run "做一个跨模块需求"
```

`full` 是默认 profile；只有明确要快速小改或只调查时，才显式传 `--profile quick` 或 `--profile investigate`。

P0 本地交付 workflow：

```bash
agt2 deliver "实现一个需求，完成本地验证报告"
agt2 approve
agt2 approve
```

第一次 `go` 通过 Product 需求合同检查，第二次 `go` 通过 Dev 技术方案检查。Dev 实现完成后会自动进入 QA；QA 失败会直接回到 `dev:implementation` 生成新 attempt。AGT 不会自动 commit、push、merge 或发 PR。

`agt2 deliver` 是 V2 `product-dev-qa` 的简化入口，默认会为需求创建隔离 worktree。`agt2 run` 是 `deliver` 的别名，但遵守 `run` 的 worktree 语义：只有显式传 `--task-worktree` 或 V2 项目配置启用 task worktree 时才创建 worktree。`agt2 approve` 等价于对当前最新 V2 session 执行 `go` 决策。

常用参数：

```bash
agt run "..." --repo-root /path/to/repo --state-root /path/to/repo/.agt
agt run --from docs/requirement.md --repo-root /path/to/repo
agt run --from-dir docs/requirement-folder --repo-root /path/to/repo
agt2 deliver --from docs/requirement.md
agt2 deliver "..." --no-task-worktree
agt2 status
agt2 inspect <session_id>
agt status
agt status <session_id>
agt inspect <session_id>
```

如果启用 task worktree，`agt run --continue`、`agt status`、`agt inspect` 和 `agt decision` 会先读主状态目录的 `session-index.json`，再跳到对应 worktree 的 `state_root` 读取真实 session。因此从主项目目录也能继续或检查 worktree 里的任务。

## OpenAI SDK 执行

当存在 `OPENAI_API_KEY` 或 `OPENAI_BASE_URL` 时，runtime 会使用 OpenAI Agents SDK：

```bash
export OPENAI_API_KEY=...
export AGT_OPENAI_MODEL=gpt-5.4-mini
agt run "实现一个小功能" --profile quick
```

SDK runner 会创建 `SandboxAgent`，把当前仓库挂载到 sandbox 的 `/workspace`：

- 只读阶段使用 read-only mount。
- 写入阶段使用 read-write mount。
- 每个 agent run 会记录输入、输出、runner、状态和 tool call 摘要。
- SDK 返回的 tool-like run item 会落到 `tool-calls.jsonl`。
- 每次 SDK run 会额外写一个 `<agent_run_id>-sdk-trace.json` artifact，记录 raw response 数量、new item 数量、last response id 和压缩后的 run item 摘要。

V1 的默认模型和每个 profile 的最大 turns 可以写在 `.agt/config.json`。V2 不再使用 profile，`.agt2/config.json` 只保留模型、executor 默认参数和 task worktree 策略。下面是 V2 示例：

```json
{
  "schema_version": 1,
  "default_model": "gpt-5.4-mini",
  "state_root": ".agt2",
  "executor": {
    "default_max_turns": 8
  }
}
```

V2 executor 优先读取 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`AGT_OPENAI_MODEL` / `OPENAI_MODEL`。如果这些环境变量没有设置，会尝试读取 `~/.codex/config.toml` 的 `model` / `model_provider` / provider `base_url`，以及 `~/.codex/auth.json` 的 `OPENAI_API_KEY`。环境变量和 Codex 配置都不可用时，runtime 才会走 `local_fallback`，只执行确定性的本地检查并写入同样的状态文件。这样 `npm test`、CLI smoke 和迁移验证不依赖外部模型。

V2 也可以显式使用 Codex CLI 作为阶段 executor：`AGT_EXECUTOR=codex_exec agt2 deliver --from docs/requirement.md`。`codex_exec` runner 调用 `codex exec --json`，由 AGT 为每次 agent run 准备隔离的 `CODEX_HOME`，只把当前 stage 选中的 skills 物化到 `codex-home/skills/<skill>/SKILL.md`，并剥离继承自用户全局配置的 `[[skills.config]]`。Prompt 只携带 skill 名称、来源和 hash；skill 正文通过隔离 home 供 Codex 原生发现。默认从当前 `CODEX_HOME` 或 `~/.codex` 复制认证和配置，也可用 `AGT_CODEX_SHARED_HOME` 指定来源。每次 Codex run 会记录 `<agent_run_id>-codex-exec-prompt.md`、`<agent_run_id>-codex-exec-events.jsonl`、`runs/<agent_run_id>/skill-manifest.json`、agent run metadata、tool call 摘要、commands、changed files 和 token usage。

## 状态目录

V1 默认状态目录是 `<repo>/.agt`，V2 默认状态目录是 `<repo>/.agt2`。V1 目录结构示例：

```text
.agt/
  sessions/
    <session_id>/
      session.json
      workflow-run.json        # product-dev-qa workflow only
      delivery-workflow.json
      execution-workflow.json
      events.jsonl
      tool-calls.jsonl
      agents/
        <agent_run_id>.json
      artifacts/
        index.jsonl
        <role-output>.md
      stages/                  # product-dev-qa workflow only
        <stage>/attempt-001/
          context-packet.json
          pre-state.json
          prompt.md
          prompt.meta.json
          candidate.json
          verdict.json
          executor-run.json
          post-state.json
  local/
    worktree-policy.json
  prompt_traces/
    index.jsonl
    <prompt_id>/
      meta.json
      prompt.md
  session-index.json
```

这些文件是 runtime 的事实来源。控制台和 CLI 都从这里读取，不再从模型摘要反推状态。V2 使用同样结构，但根目录是 `.agt2/`。
`agt init` 会写入 `.agt/local/worktree-policy.json`，`agt2 init` 会写入 `.agt2/local/worktree-policy.json`，用于记录 task worktree 的默认策略。

`delivery-workflow.json` 是外层业务交付状态，面向用户和 CLI 默认展示：`requirement -> development -> verification -> handoff`。它记录每个 phase 的状态、blockers 和 evidence_refs。

`execution-workflow.json` 是 AGT 内部执行状态，面向调试和追踪。V1 会按 profile 展开 steps；V2 `product-dev-qa` 固定展开为 `intake_summary -> product -> dev.technical_plan -> dev.implementation -> qa`。execution 的变化会通过 runtime projector 更新 delivery；delivery 不会反向改 execution。

`product-dev-qa` workflow 的外层循环以 `workflow-run.json` 为准。人主要看这个文件里的 `status`、`current_role`、`current_step` 和 `waiting_on`；`stages/*/attempt-*` 用于审计和调试阶段输入、prompt、候选输出、verdict 与 executor run。

如果不需要保留旧 session、prompt trace、tool-call 记录和历史控制台数据，可以直接删除旧 `.agt` 后重新初始化：

```bash
rm -rf .agt
agt init
agt run "你的第一个需求"
```

这条路径最适合从旧 runtime 切到当前 JS runtime 的全新开始。删除 `.agt` 会永久丢弃旧运行历史；如果需要保留旧记录，先使用 `agt migrate --dry-run` 和 `agt migrate --apply`。

每个 execution workflow step 会记录：

- `prompt_trace_id`：这一阶段实际发送给 runner 的 prompt。
- `agent_run_id`：这一阶段的 executor run 记录。
- `artifact_path`：这一阶段输出 artifact。
- `files_changed` / `commands_run`：runtime 能观察到的变更和命令证据。

人工决策使用：

```bash
agt decision <session_id> --decision go
agt decision <session_id> --decision no-go
```

## 迁移旧状态

先 dry-run：

```bash
agt migrate --from /path/to/legacy/repo --state-root /path/to/repo/.agt --dry-run
```

确认后写入：

```bash
agt migrate --from /path/to/legacy/repo --state-root /path/to/repo/.agt --apply
```

migrator 会扫描：

- `<source>/_runtime/sessions`
- `<source>/.agt/_runtime/sessions`
- `<source>/.agent-team/_runtime/sessions`

迁移结果会写入新 session 的 `migration.json`，并把旧 `session.json`、`workflow_summary.json` 复制到 `artifacts/` 作为 legacy evidence。

## 控制台服务

启动 API 和前端静态资源：

```bash
agt server --state-root /path/to/repo/.agt --host 127.0.0.1 --port 8765
agt2 server --state-root /path/to/repo/.agt2 --host 127.0.0.1 --port 8766
```

主要接口：

- `GET /api/console/snapshot`
- `GET /api/projects`
- `GET /api/sessions`
- `GET /api/sessions/:sessionId`
- `GET /api/sessions/:sessionId/events`
- `GET /api/sessions/:sessionId/tool-calls`
- `GET /api/sessions/:sessionId/prompts`
- `GET /api/sessions/:sessionId/prompts/:promptId`
- `GET /api/sessions/:sessionId/artifacts`
- `GET /api/sessions/:sessionId/artifacts/:artifactName`
- `GET /api/sessions/:sessionId/agent-runs`
- `GET /api/session`
- `GET /ws/runtime`

控制台的 session detail 页会展示 workflow steps、prompt traces、agent runs、tool calls、artifacts 和 events，并能直接预览 prompt/artifact 内容。

## 开发验证

```bash
npm run typecheck
npm run build
npm test
```

CLI smoke：

```bash
node packages/cli/dist/index.js run "smoke quick js runtime" --repo-root . --state-root /tmp/agt-js-smoke-state
node packages/cli/dist/V2/index.js deliver "smoke product dev qa runtime" --repo-root . --state-root /tmp/agt2-js-smoke-state --no-task-worktree
node packages/cli/dist/index.js migrate --from . --state-root /tmp/agt-js-migrate-state --dry-run
node packages/cli/dist/index.js server --state-root /tmp/agt-js-smoke-state --host 127.0.0.1 --port 8765
```

## 技术方案

本次 JS rewrite 的详细方案在 [docs/workflow-specs/2026-06-06-js-runtime-rewrite.md](docs/workflow-specs/2026-06-06-js-runtime-rewrite.md)。
两层 workflow 状态模型在 [docs/workflow-specs/2026-06-18-delivery-execution-workflow.md](docs/workflow-specs/2026-06-18-delivery-execution-workflow.md)。
新的 `Product -> Dev -> QA` P0 workflow 方案在 [docs/workflow-specs/2026-06-21-product-dev-qa-workflow-runtime.md](docs/workflow-specs/2026-06-21-product-dev-qa-workflow-runtime.md)。
