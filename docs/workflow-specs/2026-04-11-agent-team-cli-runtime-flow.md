# Agent Team CLI Runtime 当前流程

日期：2026-04-11

## 当前流程本质

当前流程已经不再依赖 skill 直接控制阶段推进，而是由 runtime 状态机控制。

主链路如下：

```text
start-session
-> Intake
-> Product
-> WaitForCEOApproval
-> TechPlan
-> WaitForTechPlanApproval
-> Dev
-> QA
-> Acceptance
-> WaitForHumanDecision
-> Done
```

其中 QA 失败会回到 Dev，Acceptance 的人工 `rework` 可以回到 Product、TechPlan 或 Dev。

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

创建后，当前 session 的全部运行态文件都会集中在 `.agent-team/<session_id>/`。

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

- `go` -> `TechPlan`
- `rework` -> `Product`
- `no-go` -> `Done`

### TechPlan

TechPlan 正常完成后进入：

- `WaitForTechPlanApproval`

### WaitForTechPlanApproval

只能通过人工决策推进：

- `go` -> `Dev`
- `rework` -> `TechPlan`
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
- `rework TechPlan` -> `TechPlan`
- `rework Dev` -> `Dev`

## 当前事实来源

当前流程事实来源是：

- `workflow_summary.md`
- `session.json`
- `stage_runs/*.json`
- stage records
- result bundle

只读看板读取这些事实来源，但不写入任何 workflow state。

而不是当前会话里“感觉已经做到哪一步了”。

## 当前边界

当前这套流程已经能稳定控流程，但还没有完全自动跑流程。
