# AI_Team CLI Runtime 使用说明

日期：2026-04-11

## 安装

在仓库根目录执行：

```bash
pip install -e .
```

安装完成后使用统一入口：

```bash
ai-team
```

## 最短使用路径

### 1. 启动一个 session

```bash
ai-team start-session --message "执行这个需求：做一个新的功能"
```

### 2. 查看当前阶段

```bash
ai-team current-stage --session-id <session_id>
```

### 3. 查看下一步 runtime 动作

```bash
ai-team step --session-id <session_id>
```

### 4. 生成阶段 contract

```bash
ai-team build-stage-contract --session-id <session_id> --stage Product
```

### 5. 认领当前 stage run

```bash
ai-team acquire-stage-run --session-id <session_id> --stage Product
```

### 6. 提交阶段候选 bundle

```bash
ai-team submit-stage-result --session-id <session_id> --bundle /path/to/bundle.json
```

### 7. 验证候选 bundle 并推进 workflow

```bash
ai-team verify-stage-result --session-id <session_id>
```

只有 `verify-stage-result` 返回 `gate_status: PASSED` 后，runtime 才会调用外层 workflow 状态机推进到下一 stage 或等待态。

### 8. 记录人工决策

```bash
ai-team record-human-decision --session-id <session_id> --decision go
```

## 常用命令

初始化状态目录：

```bash
ai-team init-state
```

初始化项目级 bridge 文件：

```bash
ai-team codex-init
```

查看当前阶段：

```bash
ai-team current-stage --session-id <session_id>
```

恢复查看：

```bash
ai-team resume --session-id <session_id>
```

查看下一步动作：

```bash
ai-team step --session-id <session_id>
```

`step` 会输出当前 stage、下一步动作、`contract_id`、`required_outputs` 和 `required_evidence`，用于避免 worker 靠记忆推进流程。

生成 contract：

```bash
ai-team build-stage-contract --session-id <session_id> --stage Product
```

认领 stage run：

```bash
ai-team acquire-stage-run --session-id <session_id> --stage Product
```

提交 candidate bundle：

```bash
ai-team submit-stage-result --session-id <session_id> --bundle /path/to/bundle.json
```

验证 candidate bundle：

```bash
ai-team verify-stage-result --session-id <session_id>
```

记录人工决策：

```bash
ai-team record-human-decision --session-id <session_id> --decision go
```

回写反馈：

```bash
ai-team record-feedback --session-id <session_id> --source-stage Acceptance --target-stage Dev --issue "<issue>"
```

查看 review：

```bash
ai-team review
```

输出只读看板 JSON：

```bash
ai-team board-snapshot --all-workspaces
```

启动本地只读看板：

```bash
ai-team serve-board --all-workspaces --port 8765 --poll-interval 5
```

## bundle 最小结构

```json
{
  "session_id": "<session_id>",
  "stage": "Product",
  "contract_id": "<contract_id>",
  "status": "completed",
  "artifact_name": "prd.md",
  "artifact_content": "# PRD\n\n## Acceptance Criteria\n- ...\n",
  "evidence": [
    {
      "name": "explicit_acceptance_criteria",
      "kind": "report",
      "summary": "PRD includes explicit acceptance criteria."
    }
  ]
}
```

`evidence` 必须是 machine-readable 对象。runtime 会按 contract 里的 `evidence_specs` 检查 `name`、`kind` 和必填字段，例如 `summary`。

## 只读看板

输出聚合 JSON：

```bash
ai-team board-snapshot --all-workspaces
```

启动本地看板：

```bash
ai-team serve-board --all-workspaces --port 8765 --poll-interval 5
```

看板按 `Project -> Worktree -> Session` 展示所有 workspace 的只读状态，每 5 秒轮询刷新。

## 当前建议

- 日常入口统一使用 `ai-team`
- 不再把 `python3 -m ai_company ...` 当作主入口
- 当前最适合把它理解成一个“CLI runtime + 团队框架”，不是自动一键全跑的黑盒
