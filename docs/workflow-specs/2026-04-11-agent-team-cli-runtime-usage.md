# Agent Team CLI Runtime 使用说明

日期：2026-04-11

> 归档说明：本文记录 2026-04-11 的早期 CLI 设计和命令形态。当前实现已经收口为 JS/TypeScript runtime，现行入口、安装和状态目录以仓库根目录 `README.md` 与 `docs/workflow-specs/2026-06-06-js-runtime-rewrite.md` 为准。

## 安装

正式安装方式：

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/agent-team-runtime/releases/latest/download/install.sh | sh
```

固定版本安装：

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/agent-team-runtime/releases/download/v0.1.0/install.sh | sh
```

安装前提：

- Python 3.13+
- `curl`
- `shasum` 或 `sha256sum`

如果是在仓库里做本地开发，再执行：

```bash
pip install -e .
```

安装完成后使用统一入口：

```bash
agent-team
```

## 最短使用路径

### 1. 启动一个 session

```bash
agent-team start-session --message "做一个新的功能"
```

### 2. 查看当前阶段

```bash
agent-team current-stage --session-id <session_id>
```

### 3. 查看下一步 runtime 动作

```bash
agent-team step --session-id <session_id>
```

如果只想看对用户友好的摘要：

```bash
agent-team status --session-id <session_id>
```

默认状态目录在仓库根目录下：

```text
.agent-team/<session_id>/
```

这里只放人类要直接阅读的阶段产物，例如 `product-requirements.md`、`acceptance_plan.md`、`technical_plan.md`、`implementation.md`、`qa_report.md`、`acceptance_report.md` 和 `review.md`。

机器状态、agent prompt、执行上下文、trace、stdout / stderr 等回溯材料放在：

```text
.agent-team/_runtime/sessions/<session_id>/
```
如果想一次性准备好状态目录和项目级文档结构，先运行 `agent-team init`。

### 4. 生成阶段 contract

```bash
agent-team build-stage-contract --session-id <session_id> --stage Product
```

### 5. 认领当前 stage run

```bash
agent-team acquire-stage-run --session-id <session_id> --stage Product
```

### 6. 提交阶段候选 bundle

```bash
agent-team submit-stage-result --session-id <session_id> --bundle /path/to/bundle.json
```

### 7. 验证候选 bundle 并推进 workflow

```bash
agent-team verify-stage-result --session-id <session_id>
```

只有 `verify-stage-result` 返回 `gate_status: PASSED` 后，runtime 才会调用外层 workflow 状态机推进到下一 stage 或等待态。

### 8. 记录人工决策

```bash
agent-team record-human-decision --session-id <session_id> --decision go
```

## 常用命令

初始化状态目录和项目级文档结构：

```bash
agent-team init
```

查看当前阶段：

```bash
agent-team current-stage --session-id <session_id>
```

查看用户友好状态：

```bash
agent-team status --session-id <session_id>
```

查看当前 session 的可视化快照：

```bash
agent-team panel-snapshot --session-id <session_id>
```

打开本地只读 panel：

```bash
agent-team panel --session-id <session_id> --port 8765
```

恢复查看：

```bash
agent-team resume --session-id <session_id>
```

查看下一步动作：

```bash
agent-team step --session-id <session_id>
```

`step` 会输出当前 stage、下一步动作、`contract_id`、`required_outputs` 和 `required_evidence`，用于避免 worker 靠记忆推进流程。

生成 contract：

```bash
agent-team build-stage-contract --session-id <session_id> --stage Product
```

认领 stage run：

```bash
agent-team acquire-stage-run --session-id <session_id> --stage Product
```

提交 candidate bundle：

```bash
agent-team submit-stage-result --session-id <session_id> --bundle /path/to/bundle.json
```

验证 candidate bundle：

```bash
agent-team verify-stage-result --session-id <session_id>
```

记录人工决策：

```bash
agent-team record-human-decision --session-id <session_id> --decision go
```

回写反馈：

```bash
agent-team record-feedback --session-id <session_id> --source-stage Acceptance --target-stage Dev --issue "<issue>"
```

如果这条反馈本身就是人工 rework 决策，可以在同一条命令里把 workflow 拉回目标阶段：

```bash
agent-team record-feedback --session-id <session_id> --source-stage Acceptance --target-stage Dev --issue "<issue>" --apply-rework
```

查看 review：

```bash
agent-team review
```

输出只读看板 JSON：

```bash
agent-team board-snapshot --all-workspaces
```

启动本地 React Console 的全工作区视图：

```bash
agent-team serve-board --all-workspaces --port 8765 --poll-interval 5
```

## bundle 最小结构

```json
{
  "session_id": "<session_id>",
  "stage": "Product",
  "contract_id": "<contract_id>",
  "status": "completed",
  "artifact_name": "product-requirements.md",
  "artifact_content": "# PRD\n\n## Acceptance Plan\n- [Acceptance Plan](acceptance_plan.md)\n",
  "acceptance_plan_content": "# Acceptance Plan\n\n## Requirements\n- [PRD](product-requirements.md)\n\n## Verification\n- ...",
  "evidence": [
    {
      "name": "explicit_acceptance_plan",
      "kind": "artifact",
      "summary": "Acceptance plan describes verification method and evidence."
    }
  ]
}
```

`evidence` 必须是 machine-readable 对象。runtime 会按 contract 里的 `evidence_specs` 检查 `name`、`kind` 和必填字段，例如 `summary`。

## 只读看板

输出聚合 JSON：

```bash
agent-team board-snapshot --all-workspaces
```

启动本地 React Console 的全工作区视图：

```bash
agent-team serve-board --all-workspaces --port 8765 --poll-interval 5
```

React Console 按 `Project -> Worktree -> Session` 展示所有 workspace 的只读状态，每 5 秒轮询刷新。

## 当前建议

- 日常入口统一使用 `agent-team`
- 不再把早期模块直跑形式当作主入口
- 当前最适合把它理解成一个“CLI runtime + 团队框架”，不是自动一键全跑的黑盒
