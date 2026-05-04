# Prompt Trace Ledger 设计说明

日期：2026-05-04

## 背景

当前 runtime 已经能把 `session.json`、`request.md`、stage artifact、stage run trace、stdout / stderr 等运行痕迹落盘，但默认 `agent-team run` 的 `codex-exec` stage prompt 只在内存里拼装后直接传给 Codex CLI。`agent-team dev` 的部分 prompt 会被写到 `_interactive` 或 `exec` 目录，但这些文件不是统一的 session 级索引，控制台也不能稳定展示。

这会导致一个核心问题：当需要复盘 Dev、QA 或其他阶段到底收到了什么输入时，现有记录不完整，无法保证每次模型调用都能追溯到完整 prompt 原文。

## 目标

Prompt Trace Ledger 的目标是让所有发给自动化执行器 / LLM 的 prompt 都可审计、可定位、可展示。

具体目标：

- 每次模型调用前，先把完整 prompt 原文落盘。
- 每条 prompt 都有稳定元数据：`prompt_id`、`kind`、`stage`、`run_id`、`executor`、`created_at`、`path`、`sha256`。
- 每条 prompt 都记录当次注入的 skill 快照，不能只依赖后续的 skill 文件内容。
- Prompt trace 能关联回 session，即使 prompt 发生在 session 创建前，例如 `agent-team dev` 的 alignment 和 technical plan。
- Web Console 的 session detail 能展示 prompt 列表，并能打开 prompt 原文。
- Prompt 记录失败时不继续调用模型，避免出现“执行了但不可回溯”的运行记录。

## 范围

记录范围是“发给自动化执行器 / LLM 的 prompt”。

必须记录：

- `agent-team dev` 的 alignment prompt。
- `agent-team dev` 的 technical plan prompt。
- `agent-team dev` 委派 Product / Dev / QA / Acceptance 时的 stage prompt。
- `agent-team run` 默认 `codex-exec` 生成的 Product / TechPlan / Dev / QA / Acceptance stage prompt。
- 未来新增 executor 只要接收 prompt 文本，也必须通过同一套 ledger 记录。

不记录：

- CLI 对人类展示的确认问题，例如 `[y] 通过`、`[e] 提修改意见`。
- `dry-run` executor，因为它没有发给模型的 prompt。
- `run --executor command` 的 shell 命令本身，因为该链路接收 contract / context / schema 路径，不在 runtime 内生成 LLM prompt。

如果 command executor 的外部命令自己调用模型并生成 prompt，那属于外部命令的审计责任；runtime 只能记录自己生成并传出的 prompt。

## 存储设计

Prompt ledger 放在 state root 下，独立于单个 session 目录：

```text
<state-root>/prompt_traces/
  index.jsonl
  <prompt_id>/
    meta.json
    prompt.md
```

这样可以支持 session 创建前的 prompt 记录，也能跨 session 做全局分析。

Session 通过 `session.json` 里的 `prompt_trace_ids` 关联 prompt：

```json
{
  "session_id": "20260504-...",
  "request": "...",
  "prompt_trace_ids": [
    "prompt-20260504T120001Z-alignment-8f2a1b",
    "prompt-20260504T120022Z-technical-plan-1d92c0",
    "prompt-20260504T120314Z-dev-run-1-91ce40"
  ]
}
```

`index.jsonl` 是全局索引，每行一条 `PromptTraceRecord`，用于分析和控制台快速列表。`meta.json` 是单条记录的权威元数据。`prompt.md` 是完整 prompt 原文。

## 数据模型

`PromptTraceRecord` 使用这些字段：

| 字段 | 含义 |
| --- | --- |
| `prompt_id` | 全局唯一 id，建议使用时间戳、kind、stage、短 hash 组成 |
| `session_id` | 已绑定 session 时填写；session 创建前可以为空 |
| `kind` | `alignment`、`technical_plan`、`stage` 等 |
| `stage` | `Product`、`TechPlan`、`Dev`、`QA`、`Acceptance`；非 stage prompt 可为空 |
| `run_id` | stage run id；非 stage prompt 可为空 |
| `round_index` | stage context round；没有 round 时为 `0` |
| `executor` | `codex`、`claude-code`、`codex-exec` 等 |
| `created_at` | UTC ISO timestamp |
| `path` | `prompt.md` 的绝对路径 |
| `metadata_path` | `meta.json` 的绝对路径 |
| `sha256` | prompt 原文的 SHA-256 |
| `bytes` | prompt 原文 UTF-8 字节数 |
| `source` | 记录点，例如 `interactive.alignment`、`runtime_driver.codex_exec` |
| `response_path` | 对应 last message 或 result bundle 路径；没有则为空 |
| `skill_manifest_path` | 当次 skill injection manifest 路径；没有则为空 |
| `skills` | 当次注入 skill 的快照数组；没有则为空 |

Prompt 原文不放进 `meta.json`，避免索引文件过大。读取原文时通过 `path` 打开 `prompt.md`。

`skills` 数组的每个元素至少包含：

| 字段 | 含义 |
| --- | --- |
| `name` | skill 名称 |
| `source` | `builtin`、`personal`、`project` |
| `scope` | `global` 或 `project` |
| `delivery` | `prompt` 或 `sandbox` |
| `path` | skill 定义文件路径 |
| `content_sha256` | skill content 的 SHA-256 |
| `included_in_prompt` | 是否注入到了 prompt 文本中 |
| `installed_path` | sandbox skill 的安装路径；非 sandbox 时为空 |
| `sandbox_files` | sandbox 资产清单 |
| `env_vars` | sandbox 需要的环境变量 |

对于 stage prompt，`skill_manifest_path` 应指向现有 stage-run 里的 `*_skill_injection.json`，同时 `skills` 数组应保存那次注入的稳定快照，避免后续 skill 文件或 preference 变化影响回溯结果。

## 写入流程

Prompt 写入必须发生在模型调用之前：

1. 构造 prompt 字符串。
2. 调用 `PromptTraceStore.record_prompt(...)`。
3. `record_prompt` 写入 `prompt.md`、`meta.json`，追加 `index.jsonl`。
4. 如果已经有 `session_id`，同步把 `prompt_id` 追加到 `session.json.prompt_trace_ids`。
5. 记录成功后才调用 Codex / Claude / 其他 executor。

如果步骤 2 或 3 失败，当前阶段直接失败或阻塞，并把错误返回给 operator。不要继续调用模型。

## Session 绑定

`agent-team run` 的 session 在 stage 执行前已经存在，因此 stage prompt 可以直接写入 `session_id` 并追加到 `session.json.prompt_trace_ids`。

`agent-team dev` 的 alignment / technical plan 发生在 session 创建前。这里使用两步绑定：

1. Interactive runner 先把 prompt 写到全局 ledger，记录 `prompt_id`，`session_id` 暂为空。
2. DevController 创建 session 时，把前期累积的 `prompt_id` 列表传给 `StateStore.create_session(...)`，写入 `session.json.prompt_trace_ids`。

这种方式不需要提前创建 draft session，也不会改变当前 `agent-team dev` 的交互流程。

## Runtime 集成点

需要接入 ledger 的位置：

- `agent_team/interactive.py`
  - alignment prompt 构造后、executor 调用前记录。
  - technical plan prompt 构造后、executor 调用前记录。
  - DevController 累积这些 prompt ids，并在创建 session 时绑定。

- `agent_team/stage_harness.py`
  - `stage_prompt(...)` 构造后、`StageExecutor.execute(...)` 调用前记录。
  - 记录 Product / Dev / QA / Acceptance 的 stage prompt。
  - 记录生成的 `prompt_id` 到 stage run artifact paths，方便 run 级定位。
  - 同步把 `enabled_skills_by_stage` 的注入结果写入 prompt trace 的 `skills` 和 `skill_manifest_path`。

- `agent_team/runtime_driver.py`
  - `_build_codex_prompt(...)` 生成后、`subprocess.run(codex exec ...)` 之前记录。
  - 记录 Product / TechPlan / Dev / QA / Acceptance 的 `codex-exec` prompt。
  - 将 `prompt_path` 和 `prompt_id` 写进 stage run trace details。
  - 将 `skill_manifest_path` 和 `skills` 也写进同一条 prompt trace。

- `agent_team/executor.py`
  - 现有 `{stage}_prompt.md` 文件不再作为唯一事实来源。
  - 可以保留兼容文件，但 canonical source 是 `prompt_traces/<prompt_id>/prompt.md`。

## 控制台与 API

`build_panel_snapshot(...)` 增加 `prompts` 字段：

```json
{
  "prompts": [
    {
      "prompt_id": "prompt-...",
      "kind": "stage",
      "stage": "Dev",
      "run_id": "dev-run-1",
      "executor": "codex-exec",
      "created_at": "2026-05-04T...",
      "path": "/.../.agent-team/prompt_traces/.../prompt.md",
      "sha256": "...",
      "bytes": 12345,
      "skill_manifest_path": "/.../.agent-team/<session_id>/stage_runs/dev-run-1_skill_injection.json",
      "skills": [
        {
          "name": "plan",
          "source": "builtin",
          "scope": "global",
          "delivery": "prompt",
          "content_sha256": "..."
        }
      ]
    }
  ]
}
```

Web Console 的 session detail 增加 `Prompts` 区块：

- 按 `created_at` 正序展示。
- 展示 `kind`、`stage`、`run_id`、`executor`、`bytes`、`sha256`。
- 展示当次注入的 skill 列表，至少包含 `name`、`source`、`scope`、`delivery`、`content_sha256`。
- 提供“查看原文”入口，读取 `prompt.md`。
- 提供 skill injection manifest 路径入口；如果没有注入 skill，则展示为空状态而不是隐藏字段。
- 原文路径必须通过现有 artifact path allowlist 或同等校验，只允许读取 state root 下的 prompt 文件。

API 可以复用 `/api/artifact?path=...` 读取 prompt 原文，因为 prompt 文件位于 state root 下。若前端需要更明确的语义，可以增加 `/api/prompts/{prompt_id}`，但第一版不强制新增该 endpoint。

## 错误处理

- Prompt trace 写入失败：不调用模型，当前执行直接返回 blocked / error。
- Prompt 文件缺失：session detail 仍返回 metadata，并标记 `exists=false`。
- `sha256` 不匹配：控制台展示校验失败，不自动修复。
- `session.json.prompt_trace_ids` 包含不存在的 id：控制台忽略原文读取，但保留一条缺失记录，方便排查。

## 安全与隐私

Prompt 可能包含用户原始需求、仓库结构、PRD、技术方案、实现报告、QA 报告和反馈意见，因此它和 stage artifacts 一样属于敏感运行时数据。

安全要求：

- Prompt trace 只写本地 state root。
- Web API 只能读取 state root 下的 prompt 文件。
- 不新增远程上传、共享或公开访问能力。
- 控制台展示 prompt 原文时不做脱敏，因为目标是审计完整输入；如果未来需要共享报告，应单独做导出脱敏功能。

## 测试策略

需要补这些测试：

- `tests/test_prompt_traces.py`
  - 记录 prompt 后生成 `prompt.md`、`meta.json`、`index.jsonl`。
  - `sha256` 与 prompt 原文一致。
  - session 绑定能把 `prompt_id` 写进 `session.json.prompt_trace_ids`。
  - `skills` 与 `skill_manifest_path` 会跟 prompt 一起写入元数据。

- `tests/test_runtime_driver.py`
  - `codex-exec` stage 执行前会记录 prompt。
  - stage run trace 包含 `prompt_id` 和 `prompt_path`。
  - 记录失败时不会调用 executor。

- `tests/test_stage_harness.py`
  - `agent-team dev` 的 stage harness prompt 会进入 ledger。
  - stage run artifact paths 包含 prompt trace。
  - prompt trace 保存当次注入的 skill 快照。

- `tests/test_dev_command.py`
  - alignment 和 technical plan prompt 在 session 创建前被记录。
  - session 创建后能关联这些前期 prompt。
  - 前期 prompt trace 在没有注入 skill 时记录空 `skills` 数组；未来有注入时保存同样的 skill snapshot。

- `tests/test_console_data.py`
  - session detail 返回 `prompts` 列表。
  - 缺失 prompt 文件时 `exists=false`，不会让 session detail 失败。

- `apps/web` 测试或现有构建检查
  - `SessionDetailPage` 能渲染 prompts 区块。
  - prompt 原文入口使用安全读取路径。

## 验收标准

实现完成后必须满足：

- 新建 session 并跑 `agent-team run --executor codex-exec` 时，每个实际发给 Codex 的 stage prompt 都有 prompt trace。
- 运行 `agent-team dev` 时，alignment、technical plan、Product / Dev / QA / Acceptance 的 prompt 都能从最终 session 查到。
- 给定一个 session id，可以列出该 session 的所有 prompt metadata。
- 给定一条 prompt metadata，可以打开完整 prompt 原文。
- 给定一条 prompt metadata，可以看到当次注入的 skill 清单和每个 skill 的内容 hash。
- prompt trace 写入失败时，不发生模型调用。
- Web Console 的 session detail 能展示 prompt 列表、原文入口和注入 skill 列表。
- 现有 request、workflow summary、stage artifacts、stage run trace 仍保持兼容。

## 自检

- 没有引入远程存储或外部服务。
- 没有改变 stage contract 和 stage artifact 的语义。
- 没有要求重构整个 session 创建流程。
- 前期 prompt 通过全局 ledger + session 绑定解决，可覆盖 session 创建前的交互。
- 控制台只读 prompt，不能修改 prompt trace。
