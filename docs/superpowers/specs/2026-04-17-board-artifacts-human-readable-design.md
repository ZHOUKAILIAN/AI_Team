# Board Artifacts Human-Readable Design

Date: 2026-04-17

## Goal

把只读看板里的 `Artifacts` 区域从“文件路径清单”改成“人能看懂的产物说明区”。

用户应该先理解每个 artifact 的业务含义，再决定是否预览文件内容。文件路径仍可保留，但必须降级为辅助信息。

## Current Problem

当前 `Artifacts` 区域直接展示：

- `acceptance_contract`
- `dev`
- `product`
- `request`
- `workflow_summary`

这些 key 和绝对路径对 runtime 有意义，但对人没有足够上下文。用户看到路径列表时，不知道哪个是核心产物、哪个是系统元数据，也不知道每个文件应该回答什么问题。

## Approved Direction

采用方案 B：产物卡片分区。

页面按两类展示 artifact：

- 业务产物：人真正需要阅读和判断的交付物。
- 运行时元数据：runtime 用来解释流程状态、合同和输入来源的辅助文件。

每个 artifact 显示为一张小卡片：

- 中文标题
- 一句话说明
- 文件名
- 主要操作：预览内容
- 可选辅助信息：完整路径

## Artifact Mapping

已知 artifact key 的展示映射：

- `request`
  - 标题：原始需求
  - 分类：运行时元数据
  - 说明：启动这个 session 时记录的需求输入。
- `workflow_summary`
  - 标题：流程摘要
  - 分类：运行时元数据
  - 说明：当前状态、阶段、人工决策和已记录产物。
- `acceptance_contract`
  - 标题：验收约束
  - 分类：运行时元数据
  - 说明：这条需求的验收条件、证据要求和边界规则。
- `product`
  - 标题：产品方案 / PRD
  - 分类：业务产物
  - 说明：Product 阶段产出的需求方案和验收标准。
- `dev`
  - 标题：实现说明
  - 分类：业务产物
  - 说明：Dev 阶段产出的实现计划或交付说明。
- `qa`
  - 标题：QA 验证结果
  - 分类：业务产物
  - 说明：QA 阶段产出的验证结论、风险和证据。
- `acceptance`
  - 标题：验收建议
  - 分类：业务产物
  - 说明：Acceptance 阶段产出的产品级验收建议。

未知 artifact key 使用 fallback：

- 标题：artifact key
- 分类：其他产物
- 说明：这个 artifact 暂无内置说明，可预览内容查看。

## Interaction

点击 `预览内容` 后，继续使用现有 `/api/artifact?path=...` 只读预览能力。

预览区域应显示当前预览的中文标题，避免用户不知道正在看哪个文件。

如果没有 artifact，显示“暂无产物”。

## Boundaries

这个改动只影响前端展示：

- 不改变 `/api/board` 数据结构。
- 不改变 `/api/artifact` 白名单安全规则。
- 不新增任何状态写操作。
- 不新增 approve、verify、submit、rework 等控制按钮。
- 不自动摘要文件内容，避免引入 AI 或额外依赖。

## Testing

更新 `tests/test_board_server.py`，断言 HTML 包含：

- artifact 分区渲染函数
- artifact 元数据映射函数
- 中文标题，例如 `产品方案 / PRD`
- 预览按钮文案，例如 `预览内容`

继续运行：

```bash
/tmp/agent-team-runtime-enforced-venv/bin/python -m unittest tests.test_board_server
```
