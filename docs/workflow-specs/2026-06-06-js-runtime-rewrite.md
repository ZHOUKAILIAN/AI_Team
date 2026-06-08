# JS Runtime Rewrite Technical Plan

## 背景

旧 runtime 的核心问题不是“能不能调用模型”，而是每次任务都像重新开一组 Codex 进程：

- 小需求启动和规划成本偏高。
- 大需求的阶段执行容易变成黑盒，用户只能看到最终摘要。
- 任务执行依赖 Codex CLI，runtime 本身不能直接控制 agent、tool call、sandbox 和状态落盘。
- 旧状态目录分散在 `.agt/_runtime`、`.agent-team/_runtime` 等目录里，迁移和控制台读取都不稳定。

这次重写的目标是把执行权收回到 runtime：用 JS/TypeScript 和 OpenAI Agents SDK 直接创建 subagent，并由 runtime 统一记录状态、事件、工具调用和迁移结果。

## 目标

1. 去掉对 Codex CLI 执行链路的硬依赖，默认由 OpenAI Agents SDK runner 执行。
2. 提供 `quick`、`investigate`、`full` 三种 profile，降低小需求成本，同时保留大需求治理链路。
3. 每个 agent run 都有结构化记录，能回答“模型拿到了什么输入、跑到了哪个阶段、输出了什么、记录了哪些工具调用”。
4. 旧 session 可以迁移到新 schema，迁移不修改旧运行态。
5. 控制台通过 API 读取 `.agt/sessions`，不再依赖旧 Python runtime 的 summary shape。

## 架构

```text
agt CLI
  -> packages/runtime
       -> RuntimeStore
       -> OpenAISandboxRunner | LocalFallbackRunner
       -> profiles quick/investigate/full
  -> packages/migrator
  -> packages/server
       -> Fastify API
       -> apps/web/dist static UI
```

### CLI

`packages/cli` 提供统一入口：

- `agt run [message...]`
- `agt status [session-id]`
- `agt inspect <session-id>`
- `agt migrate --from <path> --dry-run|--apply`
- `agt server`

CLI 不保存业务状态，只负责解析参数、调用 runtime、打印可读结果。

### Runtime

`packages/runtime` 是事实来源：

- `schema.ts`：用 zod 定义 session、workflow、event、agent run、tool call。
- `store.ts`：负责 `.agt/sessions/<session-id>/` 的读写。
- `profiles.ts`：定义 profile 和阶段序列。
- `runner.ts`：封装 OpenAI SDK runner 和 local fallback runner。

### Runner

`OpenAISandboxRunner` 在有 `OPENAI_API_KEY` 或 `OPENAI_BASE_URL` 时启用：

- 创建 `SandboxAgent`。
- 将 repo 挂载到 `/workspace`。
- 读阶段使用 read-only，写阶段使用 read-write。
- 写入 `agents/<agent_run_id>.json`、`events.jsonl` 和 `tool-calls.jsonl`。
- 从 `.agt/config.json` 读取 `default_model` 和每个 profile 的 `max_turns`。
- 把 SDK 返回的 shell/apply_patch/function/tool-like run items 归一化写入 `tool-calls.jsonl`。
- 把 SDK 原始响应摘要写成 `<agent_run_id>-sdk-trace.json` artifact，保留 raw response count、new item count、last response id 和 run item 摘要。

`LocalFallbackRunner` 用于没有 OpenAI 环境变量的场景：

- 执行 `git status --short`。
- 写入同样 schema 的 agent run 和 tool call。
- 保证本地测试、CI、CLI smoke 不需要真实模型。

### Profiles

`quick` 用于小需求：

```text
planner -> repo_scout -> writer -> verifier -> summarizer
```

`investigate` 用于只调查不写代码：

```text
planner -> repo_scout -> test_scout -> summarizer
```

`full` 用于大需求：

```text
route -> product_definition -> project_runtime -> technical_design -> implementation -> verification -> governance_review -> acceptance -> session_handoff
```

阶段不是靠 prompt 记忆控制，而是由 runtime 的 profile 数组和 workflow state 控制。

## 状态 Schema

新状态目录：

```text
.agt/
  sessions/
    <session_id>/
      session.json
      workflow.json
      events.jsonl
      tool-calls.jsonl
      agents/
      artifacts/
        index.jsonl
  prompt_traces/
    index.jsonl
    <prompt_id>/
      meta.json
      prompt.md
  session-index.json
```

关键原则：

- `session.json` 记录请求、profile、repo root、state root、当前状态。
- `workflow.json` 记录阶段列表、当前阶段、状态、文件变更和命令证据。
- `events.jsonl` 记录生命周期事件。
- `tool-calls.jsonl` 记录 runtime 能观察到的工具调用。
- `agents/*.json` 记录每次 subagent 的输入、输出、runner、错误和 metadata。
- `prompt_traces/*/prompt.md` 记录每个阶段实际发送给 runner 的 prompt。
- `artifacts/index.jsonl` 记录阶段输出、SDK trace 和迁移证据。

每个 workflow step 通过 `prompt_trace_id`、`agent_run_id` 和 `artifact_path` 串起输入、执行和输出。人工 `rework` 会从目标阶段开始清空下游 step 的 trace 指针、文件变更、命令记录和摘要，避免旧证据被误当成新执行结果。

## 配置

`.agt/config.json` 使用 runtime schema 校验：

```json
{
  "schema_version": 1,
  "default_profile": "quick",
  "default_model": "gpt-5.4-mini",
  "state_root": ".agt",
  "max_turns": {
    "quick": 4,
    "investigate": 5,
    "full": 8
  },
  "task_worktree": {
    "enabled": false,
    "base_ref_candidates": ["origin/test", "origin/main", "test", "main"],
    "branch_prefix": "feature/",
    "worktree_root": ".worktrees",
    "slug_max_length": 40
  },
  "human_gates": false
}
```

`agt init` 可以创建默认配置；`AGT_OPENAI_MODEL` 或 `OPENAI_MODEL` 可以覆盖 `default_model`。

## Worktree Continuation

task worktree 模式下，新 session 的真实 `state_root` 在 worktree 内，但主项目 `.agt/session-index.json` 会镜像 session 索引。以下命令都先读主索引，再跳转到目标 `state_root`：

- `agt run --continue`
- `agt status [session-id]`
- `agt inspect <session-id>`
- `agt decision <session-id>`

这样用户不需要进入每个 worktree 才能看状态或继续任务。

## 迁移策略

migrator 扫描旧目录：

- `<source>/_runtime/sessions`
- `<source>/.agt/_runtime/sessions`
- `<source>/.agent-team/_runtime/sessions`

迁移规则：

- 新 session id 使用 `migrated-<legacy-session-id>`。
- 能读到 `session.json` 和 `workflow_summary.json` 时标记 `complete`。
- 缺少其中一个但仍能恢复核心信息时标记 `partial`。
- 完全没有可识别文件时 `skipped`。
- 旧文件复制到新 session 的 `artifacts/`，不修改旧目录。
- 迁移 artifacts 通过 `RuntimeStore.writeArtifact()` 写入，因此 legacy evidence 会进入 `artifacts/index.jsonl` 并产生 `artifact_written` 事件。

## 控制台 API

`packages/server` 提供 Fastify 服务：

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

这些接口直接读 `RuntimeStore`，因此控制台展示和 CLI inspect 使用同一份事实来源。

控制台 session detail 页以 trace ledger 展示：

- workflow steps
- prompt traces
- agent runs
- tool calls
- artifacts
- events

prompt 和 artifact 内容通过 API 弹窗预览，不再只展示路径。

## 验证标准

本分支完成后必须通过：

```bash
npm run typecheck
npm run build
npm test
node packages/cli/dist/index.js run "smoke quick js runtime" --repo-root . --state-root /tmp/agt-js-smoke-state
node packages/cli/dist/index.js migrate --from . --state-root /tmp/agt-js-migrate-state --dry-run
```

服务 smoke 需要验证：

```bash
node packages/cli/dist/index.js server --state-root /tmp/agt-js-smoke-state --host 127.0.0.1 --port 8765
curl http://127.0.0.1:8765/api/console/snapshot
curl http://127.0.0.1:8765/api/sessions
```
