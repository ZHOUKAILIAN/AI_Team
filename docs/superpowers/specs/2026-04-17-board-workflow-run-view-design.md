# Board Workflow Run View Design

Date: 2026-04-17

## Goal

把只读看板的主视图从“阶段标签 + 原始字段”升级成真正的 workflow run 视图。

页面第一屏默认优先回答：

1. 卡在哪
2. 为什么卡在这里
3. 下一步谁做什么
4. 当前进度和已有交付物

## Current Problem

当前页面主要展示：

- 一排阶段 pill
- `current_stage`
- `human_decision`
- `active_run`
- `artifact_paths`

这些字段对 runtime 内部排查有用，但不适合人直接阅读。用户看到 `QA` 高亮、`human_decision: go`、`No active or latest run` 时，需要自己推断：

- 现在到底是不是卡住了
- 卡在什么阶段
- 为什么没有 run
- 下一步该谁来做

这会把“状态解释”工作推给用户。

## Approved Direction

采用方案 B：Workflow Run Board。

主视图不再把“阶段条”当作核心，而是把 session 解释成一条正在运行的工作流。每个节点都必须回答：

- 负责人是谁
- 当前状态是什么
- 为什么是这个状态
- 已经交付了什么
- 下一步谁来处理

## Information Hierarchy

页面第一屏按下面顺序组织：

### 1. Current Bottleneck

顶部先给出一段人话总结：

- 当前停在哪个节点
- 是 blocked、waiting、in progress 还是 done
- 造成当前状态的直接原因
- 下一步动作

示例：

`当前停在 QA。原因：还没有 QA stage run，因此验证还没有进入可跟踪状态。下一步：QA 认领并开始验证。`

### 2. Workflow Run Board

下面用节点卡片展示完整工作流：

- Product
- WaitForCEOApproval
- Dev
- QA
- Acceptance
- WaitForHumanDecision
- Done

每个节点卡片包含：

- 节点名称
- 负责人
- 状态标签
- 一句状态说明
- 已有交付物摘要
- 是否为当前节点

当前节点卡片视觉上突出显示。

### 3. Delivery / Evidence

工作流节点之后，才展示 artifacts 与预览。

Artifacts 仍是重要信息，但降级为解释“这个节点已经产出了什么”，而不是主视图。

## Node Model

每个 workflow 节点使用统一的人类可读状态，而不是直接暴露 runtime 原始枚举。

建议状态文案：

- `已完成`
- `进行中`
- `等待处理`
- `等待人工确认`
- `已阻塞`
- `未开始`

节点说明优先从现有 summary 和 run 信息推导：

- 如果当前节点存在 active run
  - 显示为 `进行中` 或 `等待验证`
- 如果节点已有 stage artifact，但当前不在此节点
  - 显示为 `已完成`
- 如果当前节点就是该节点，但没有 active run
  - 显示为 `等待处理`
- 如果流程处于 WaitForCEOApproval / WaitForHumanDecision
  - 显示为 `等待人工确认`
- 如果 workflow summary 有 blocked reason
  - 当前节点显示为 `已阻塞`
- 其后的节点
  - 显示为 `未开始`

## Legacy Session Handling

这次设计必须特别处理“历史 session 没有 stage run”的情况。

对于这类 session：

- 不再只显示 `No active or latest run`
- 要明确解释成：
  - `当前阶段已经进入 QA，但还没有可跟踪的 QA run`
  - 或
  - `这是历史 session，缺少新版本 stage-run 记录`

也就是说，页面必须把“缺 run 记录”翻译成人话，而不是把内部缺口直接原样显示给用户。

## Current Bottleneck Summary Rules

顶部摘要规则：

- 如果 blocked
  - 写 `当前已阻塞`
  - 带上 blocked reason
  - 给出建议处理方
- 如果当前阶段没有 active run
  - 写 `当前停在 <stage>`
  - 原因写为 `还没有 <stage> run` 或 `等待该角色接手`
- 如果当前阶段有 run 且 state=RUNNING
  - 写 `当前由 <role> 处理中`
- 如果 run=SUBMITTED / VERIFYING
  - 写 `当前等待 gate 验证`
- 如果处于人工等待节点
  - 写 `当前等待人工决策`

每种情况下都必须给出一个明确的 `下一步`。

## Artifact Integration

Artifacts 区域继续保留，但改成 supporting section：

- 业务产物
- 运行时元数据
- 其他产物

它负责回答：

- 当前节点已经交付了什么
- 有哪些事实依据可以点开看

不再承担“解释整个流程”的责任。

## Boundaries

这个改动只影响看板展示层：

- 不修改 `/api/board` 数据结构
- 不修改 runtime 状态机
- 不新增写操作
- 不新增 approve / verify / submit / rework 按钮
- 不引入 AI 摘要

实现方式应优先复用现有 summary、active run、artifact paths 进行前端映射。

## Testing

更新 `tests/test_board_server.py`，断言 HTML 包含：

- workflow run board 渲染函数
- current bottleneck summary 渲染函数
- legacy session 无 run 时的人话提示逻辑
- 节点状态中文映射

继续使用：

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_board_server
```
