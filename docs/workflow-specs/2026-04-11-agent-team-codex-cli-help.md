# Agent Team Codex 运行 Help

日期：2026-04-11

## 这份文档是给谁看的

这份 help 是给 `Codex App` 里的执行代理看的。

目标不是让 Codex 自己重新发明流程，而是让 Codex 明确知道：

- `agent-team` CLI 是流程控制器
- Codex 是当前 stage 的执行者
- skill 只是入口和角色资产，不负责替代 runtime 控流程

## 运行定位

当前这套系统不是“一条命令自动完成所有角色”的黑盒。

当前推荐运行方式是：

- 用 `agent-team` 创建和推进 session
- 用 `agent-team` 生成 stage contract
- 用 `agent-team` acquire 当前 stage run
- 让 Codex 读取 contract，在真实仓库里执行当前角色工作
- 由 Codex 产出 stage-result bundle
- 用 `agent-team` 提交 candidate bundle
- 用 `agent-team` verify candidate bundle，只有 gate 通过才推进状态
- 在等待人工审批的状态停下来，等待人类记录决策

## 最小 harness 循环

当前最小 harness 循环是：

`start-session -> step -> build-stage-contract -> acquire-stage-run -> execute stage work -> submit-stage-result -> verify-stage-result -> wait or next stage`

完整最小链路是：

`Product -> CEO approval -> Dev -> QA -> Acceptance -> human Go/No-Go`

## Codex 的工作方式

### 1. 启动 session

```bash
agent-team start-session --message "执行这个需求：<需求内容>"
```

Codex 需要记住输出里的：

- `session_id`
- `artifact_dir`
- `summary_path`

其中 `artifact_dir` 和 `summary_path` 都会落在仓库内的 `.agent-team/<session_id>/`。

### 2. 查看当前状态

```bash
agent-team current-stage --session-id <session_id>
```

如果要给用户展示当前进度，优先使用：

```bash
agent-team status --session-id <session_id>
```

它会输出当前项目、当前角色和当前状态，并同步到 `.agent-team/<session_id>/status.md`。

如果当前状态是等待态，先不要继续执行 stage。

也可以让 runtime 直接提示下一步：

```bash
agent-team step --session-id <session_id>
```

`step` 输出里的 `contract_id`、`required_outputs` 和 `required_evidence` 是当前执行的硬约束，不要用对话记忆替代这些字段。

如果需要看当前 action、阻塞原因和最近 timeline，可以直接打开：

```bash
agent-team panel --session-id <session_id> --port 8765
```

### 3. 构建当前 stage contract

```bash
agent-team build-stage-contract --session-id <session_id> --stage <stage_name>
```

Codex 需要把 contract 视为当前阶段的权威输入。

Codex 应该从 contract 里读取：

- 当前阶段目标
- 必需产物
- 禁止动作
- 证据要求
- 当前输入资产
- 角色 context / memory / skill overlay

### 4. acquire 当前 stage run

```bash
agent-team acquire-stage-run --session-id <session_id> --stage <stage_name>
```

这一步会创建 `RUNNING` 状态的 stage-run record。没有 active run 时，runtime 不接受 stage-result bundle。

### 5. 执行当前阶段

Codex 在真实仓库里完成当前角色工作。

当前阶段结束时，Codex 需要产出一个 stage-result bundle JSON，然后提交给 runtime。

最小 bundle 结构：

```json
{
  "session_id": "<session_id>",
  "stage": "Product",
  "contract_id": "<contract_id>",
  "status": "completed",
  "artifact_name": "prd.md",
  "artifact_content": "# PRD\n\n## Acceptance Criteria\n- ...\n",
  "journal": "# Product Journal\n",
  "findings": [],
  "evidence": [
    {
      "name": "explicit_acceptance_criteria",
      "kind": "report",
      "summary": "PRD includes explicit acceptance criteria."
    }
  ],
  "summary": "Stage completed"
}
```

`evidence` 必须是结构化对象。runtime 会按 `build-stage-contract` 输出的 `evidence_specs` 检查证据名称、类型和必填字段；只有写在 journal 里的“已验证”不算证据。

### 6. 提交阶段候选结果

```bash
agent-team submit-stage-result --session-id <session_id> --bundle /path/to/bundle.json
```

这一步只会把 run 置为 `SUBMITTED`，不会推进 workflow。

### 7. 验证候选结果

```bash
agent-team verify-stage-result --session-id <session_id>
```

只有输出 `gate_status: PASSED` 时，runtime 才会把 run 置为 `PASSED` 并调用 workflow 状态机。

验证后再看下一步：

```bash
agent-team step --session-id <session_id>
```

### 8. 等待人工决策时停止

Product 完成后，runtime 会进入 `WaitForCEOApproval`。

Acceptance 完成后，runtime 会进入 `WaitForHumanDecision`。

这两个状态下，Codex 不应擅自推进下一阶段，而应等待人类使用：

```bash
agent-team record-human-decision --session-id <session_id> --decision go
```

或者：

```bash
agent-team record-human-decision --session-id <session_id> --decision rework --target-stage Dev
```

## 反馈与自我迭代

如果人类、QA 或 Acceptance 发现问题，Codex 不应该只把问题留在对话里。

需要把问题沉淀回 runtime：

```bash
agent-team record-feedback \
  --session-id <session_id> \
  --source-stage Acceptance \
  --target-stage Dev \
  --issue "<issue>" \
  --lesson "<lesson>" \
  --context-update "<context rule>" \
  --skill-update "<skill rule>"
```

这会把反馈写入角色 memory overlay，并在后续 `build-stage-contract` 时重新注入。

## Codex 必须遵守的边界

- 不要跳过 `QA`
- 不要用 Dev 自测代替 `QA`
- 不要让 `Acceptance` 代替最终人工 Go / No-Go
- 不要绕开 `agent-team` 直接私自改 stage 状态
- 不要跳过 `acquire-stage-run` 或把 `submit-stage-result` 当成完成信号
- 不要把 deterministic metadata 当成真实 QA/Acceptance 证据

## 完成信号

对 Codex 来说，这份 help 的完成信号是：

- 能正确使用 `agent-team start-session`
- 能根据 `agent-team build-stage-contract` 执行当前角色
- 能通过 `agent-team acquire-stage-run` 认领 stage run
- 能产出并提交 `submit-stage-result`
- 能用 `agent-team verify-stage-result` 触发 gatekeeper 验证
- 遇到等待态时会停止并等待人工决策
- 能用 `agent-team record-feedback` 把问题沉淀回下一轮 contract
