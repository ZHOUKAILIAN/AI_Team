# AI_Team CLI Runtime 当前流程

日期：2026-04-11

## 当前流程本质

当前流程已经不再依赖 skill 直接控制阶段推进，而是由 runtime 状态机控制。

主链路如下：

```text
start-session
-> Intake
-> Product
-> WaitForCEOApproval
-> Dev
-> QA
-> Acceptance
-> WaitForHumanDecision
-> Done
```

其中 QA 失败会回到 Dev，Acceptance 的人工 `rework` 可以回到 Product 或 Dev。

## 当前关键命令

- `ai-team start-session`
- `ai-team current-stage`
- `ai-team resume`
- `ai-team step`
- `ai-team build-stage-contract`
- `ai-team acquire-stage-run`
- `ai-team submit-stage-result`
- `ai-team verify-stage-result`
- `ai-team record-human-decision`
- `ai-team record-feedback`

## 当前流程推进方式

### 1. 创建 session

```bash
ai-team start-session --message "执行这个需求：<你的需求>"
```

### 2. 查看当前阶段

```bash
ai-team current-stage --session-id <session_id>
```

### 3. 查看下一步动作

```bash
ai-team step --session-id <session_id>
```

### 4. 生成当前阶段 contract

```bash
ai-team build-stage-contract --session-id <session_id> --stage Product
```

### 5. acquire 当前 stage run

```bash
ai-team acquire-stage-run --session-id <session_id> --stage Product
```

### 6. worker 执行并产出 bundle

当前 worker 不由 runtime 自动调度，仍由操作者或 bridge 层触发。

### 7. 回交 candidate result

```bash
ai-team submit-stage-result --session-id <session_id> --bundle /path/to/bundle.json
```

### 8. 验证 candidate result

```bash
ai-team verify-stage-result --session-id <session_id>
```

只有 gate 通过，workflow 才会推进。

### 9. 遇到等待态时记录人工决策

```bash
ai-team record-human-decision --session-id <session_id> --decision go
```

## 当前状态机规则

### Product

Product 正常完成后进入：

- `WaitForCEOApproval`

### WaitForCEOApproval

只能通过人工决策推进：

- `go` -> `Dev`
- `rework` -> `Product`
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

- `workflow_summary.md`
- `session.json`
- `stage_runs/*.json`
- stage records
- result bundle

而不是当前会话里“感觉已经做到哪一步了”。

## 当前边界

当前这套流程已经能稳定控流程，但还没有完全自动跑流程。
