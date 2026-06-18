# Agent Team Runtime

`agent-team-runtime` 是一个 JS/TypeScript 的 agent workflow runtime。它的目标是把“小需求快速跑、复杂需求可追踪”做成同一套本地工具，而不是每次再启动一组黑盒的 `codex --yolo` 进程。

新的入口是 `agt` CLI。runtime 自己负责 session、两层 workflow、agent run、tool call 和迁移记录；模型执行通过 OpenAI Agents SDK 的 `SandboxAgent` 完成。没有 OpenAI 环境变量时会自动使用 deterministic local fallback，方便测试和离线验证。

## 当前能力

- `quick` profile：面向小需求，按 `planner -> repo_scout -> writer -> verifier -> summarizer` 快速跑完。
- `investigate` profile：面向只查问题不改代码，按 `planner -> repo_scout -> test_scout -> summarizer` 收敛证据。
- `full` profile：面向大需求，保留五层九阶段：`route -> product_definition -> project_runtime -> technical_design -> implementation -> verification -> governance_review -> acceptance -> session_handoff`。
- 每个 session 都写入结构化状态：`session.json`、`delivery-workflow.json`、`execution-workflow.json`、`events.jsonl`、`tool-calls.jsonl`、`agents/*.json`。
- 旧 Python/Codex CLI runtime 的 session 可以迁移到新 `.agt/sessions/` schema，迁移不会修改旧目录。
- 内置 Fastify API 和 web 静态资源服务，供控制台读取项目、session、事件和工具调用。

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

常用参数：

```bash
agt run "..." --repo-root /path/to/repo --state-root /path/to/repo/.agt
agt run --from docs/requirement.md --repo-root /path/to/repo
agt run --from-dir docs/requirement-folder --repo-root /path/to/repo
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

默认模型和每个 profile 的最大 turns 可以写在 `.agt/config.json`：

```json
{
  "schema_version": 1,
  "default_profile": "full",
  "default_model": "gpt-5.4-mini",
  "state_root": ".agt",
  "max_turns": {
    "quick": 4,
    "investigate": 5,
    "full": 8
  }
}
```

如果没有 OpenAI 环境变量，runtime 会走 `local_fallback`，只执行确定性的本地检查并写入同样的状态文件。这样 `npm test`、CLI smoke 和迁移验证不依赖外部模型。

## 状态目录

默认状态目录是 `<repo>/.agt`：

```text
.agt/
  sessions/
    <session_id>/
      session.json
      delivery-workflow.json
      execution-workflow.json
      events.jsonl
      tool-calls.jsonl
      agents/
        <agent_run_id>.json
      artifacts/
        index.jsonl
        <role-output>.md
  local/
    worktree-policy.json
  prompt_traces/
    index.jsonl
    <prompt_id>/
      meta.json
      prompt.md
  session-index.json
```

这些文件是 runtime 的事实来源。控制台和 CLI 都从这里读取，不再从模型摘要反推状态。
`agt init` 也会写入 `.agt/local/worktree-policy.json`，用于记录 task worktree 的默认策略。

`delivery-workflow.json` 是外层业务交付状态，面向用户和 CLI 默认展示：`requirement -> development -> verification -> handoff`。它记录每个 phase 的状态、blockers 和 evidence_refs。

`execution-workflow.json` 是 AGT 内部执行状态，面向调试和追踪：不同 profile 会展开成 `quick`、`investigate` 或 `full` 的执行 steps。execution 的变化会通过 runtime projector 更新 delivery；delivery 不会反向改 execution。

如果不需要保留旧 session、prompt trace、tool-call 记录和历史控制台数据，可以直接删除旧 `.agt` 后重新初始化：

```bash
rm -rf .agt
agt init
agt run "你的第一个需求"
```

这条路径最适合从旧 Python/Codex CLI runtime 切到 JS runtime 的全新开始。删除 `.agt` 会永久丢弃旧运行历史；如果需要保留旧记录，先使用 `agt migrate --dry-run` 和 `agt migrate --apply`。

每个 execution workflow step 会记录：

- `prompt_trace_id`：这一阶段实际发送给 runner 的 prompt。
- `agent_run_id`：这一阶段的 executor run 记录。
- `artifact_path`：这一阶段输出 artifact。
- `files_changed` / `commands_run`：runtime 能观察到的变更和命令证据。

人工决策使用：

```bash
agt decision <session_id> --decision go
agt decision <session_id> --decision no-go
agt decision <session_id> --decision rework --target-role implementation
```

`rework` 会从目标阶段开始清空下游 step 的 `agent_run_id`、`prompt_trace_id`、`artifact_path`、`files_changed`、`commands_run` 和摘要，避免控制台继续展示旧 trace。

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
node packages/cli/dist/index.js migrate --from . --state-root /tmp/agt-js-migrate-state --dry-run
node packages/cli/dist/index.js server --state-root /tmp/agt-js-smoke-state --host 127.0.0.1 --port 8765
```

## 技术方案

本次 JS rewrite 的详细方案在 [docs/workflow-specs/2026-06-06-js-runtime-rewrite.md](docs/workflow-specs/2026-06-06-js-runtime-rewrite.md)。
两层 workflow 状态模型在 [docs/workflow-specs/2026-06-18-delivery-execution-workflow.md](docs/workflow-specs/2026-06-18-delivery-execution-workflow.md)。
