# Agent Team CLI Runtime 当前流程

日期：2026-04-11

> 归档说明：本文记录 2026-04-11 的早期流程命令。当前实现已经收口为 JS/TypeScript runtime，现行流程以 `agt run/status/inspect/decision/server/migrate` 和仓库根目录 `README.md` 为准。

## 当前流程本质

当前流程已经不再依赖 skill 直接控制阶段推进，而是由 runtime 状态机控制。

主链路如下：

```text
start-session
-> Intake
-> Product
-> WaitForCEOApproval
-> Dev technical plan
-> WaitForTechnicalPlanApproval
-> Dev
-> QA
-> Acceptance
-> WaitForHumanDecision
-> Done
```

其中 QA 失败会回到 Dev，Acceptance 的人工 `rework` 可以回到 Product 或 Dev。

## 当前关键命令

- `agent-team start-session`
- `agent-team status`
- `agent-team current-stage`
- `agent-team resume`
- `agent-team step`
- `agent-team build-stage-contract`
- `agent-team acquire-stage-run`
- `agent-team submit-stage-result`
- `agent-team verify-stage-result`
- `agent-team record-human-decision`
- `agent-team record-feedback`
- `agent-team board-snapshot`
- `agent-team serve-board`

## 当前流程推进方式

### 1. 创建 session

```bash
agent-team start-session --message "<你的需求>"
```

创建后，人类可读阶段产物会集中在 `.agent-team/<session_id>/`，机器运行态文件会集中在 `.agent-team/_runtime/sessions/<session_id>/`。

### 2. 查看当前阶段

```bash
agent-team current-stage --session-id <session_id>
```

### 3. 查看下一步动作

```bash
agent-team step --session-id <session_id>
```

面向用户展示时优先使用：

```bash
agent-team status --session-id <session_id>
```

### 4. 生成当前阶段 contract

```bash
agent-team build-stage-contract --session-id <session_id> --stage Product
```

### 5. acquire 当前 stage run

```bash
agent-team acquire-stage-run --session-id <session_id> --stage Product
```

### 6. worker 执行并产出 bundle

当前 worker 不由 runtime 自动调度，仍由操作者或 bridge 层触发。

### 7. 回交 candidate result

```bash
agent-team submit-stage-result --session-id <session_id> --bundle /path/to/bundle.json
```

### 8. 验证 candidate result

```bash
agent-team verify-stage-result --session-id <session_id>
```

只有 gate 通过，workflow 才会推进。

### 9. 遇到等待态时记录人工决策

```bash
agent-team record-human-decision --session-id <session_id> --decision go
```

## 当前状态机规则

### Product

Product 正常完成后进入：

- `WaitForCEOApproval`

### WaitForCEOApproval

只能通过人工决策推进：

- `go` -> `Dev`（先产出 technical_plan.md）
- `rework` -> `Product`
- `no-go` -> `Done`

### Dev technical plan

Dev 的技术方案 pass 正常完成后进入：

- `WaitForTechnicalPlanApproval`

### WaitForTechnicalPlanApproval

只能通过人工决策推进：

- `go` -> `Dev`
- `rework` -> `Dev`（重新生成 technical_plan.md）
- `no-go` -> `Done`

### Dev

Dev 正常完成后进入：

- `QA`

### QA

如果失败或存在 findings：

- 回到 `Dev`

如果通过：

- 进入 `Acceptance`

### Acceptance

如果 blocked：

- 进入 `Blocked`

否则：

- 进入 `WaitForHumanDecision`

### WaitForHumanDecision

人工决策：

- `go` -> `Done`
- `no-go` -> `Done`
- `rework Product` -> `Product`
- `rework Dev` -> `Dev`

## 当前事实来源

当前流程事实来源是：

- `.agent-team/<session_id>/` 下的人类可读阶段产物
- `_runtime/sessions/<session_id>/workflow_summary.json`
- `_runtime/sessions/<session_id>/session.json`
- `_runtime/sessions/<session_id>/roles/<role>/attempt-001/execution-contexts/<role>-input-context.json`
- `_runtime/sessions/<session_id>/roles/<role>/attempt-001/execution-contexts/<role>-task-contract.json`
- `_runtime/sessions/<session_id>/roles/<role>/attempt-001/execution-contexts/<role>-output-schema.json`
- `_runtime/sessions/<session_id>/roles/<role>/attempt-001/execution-contexts/<role>-agent-prompt-bundle.md`（仅 `--trace-prompts`）
- `_runtime/sessions/<session_id>/roles/<role>/attempt-001/stage-results/<role>-stage-result.json`
- `_runtime/sessions/<session_id>/roles/<role>/attempt-001/stage-results/<role>-output-<artifact-name>.md`
- `_runtime/sessions/<session_id>/roles/<role>/attempt-001/command-outputs/<role>-command-stdout.txt`
- `_runtime/sessions/<session_id>/roles/<role>/attempt-001/command-outputs/<role>-command-stderr.txt`

只读看板读取这些事实来源，但不写入任何 workflow state。

而不是当前会话里“感觉已经做到哪一步了”。

## 当前边界

当前这套流程已经能稳定控流程，但还没有完全自动跑流程。
