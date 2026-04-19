# AI_Team CLI Runtime 使用说明

日期：2026-04-11

## 安装

正式安装方式：

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/AI_Team/releases/latest/download/install.sh | sh
```

固定版本安装：

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/AI_Team/releases/download/v0.1.0/install.sh | sh
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

### 3. 生成阶段 contract

```bash
ai-team build-stage-contract --session-id <session_id> --stage Product
```

### 4. 提交阶段 bundle

```bash
ai-team submit-stage-result --session-id <session_id> --bundle /path/to/bundle.json
```

### 5. 记录人工决策

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

生成 contract：

```bash
ai-team build-stage-contract --session-id <session_id> --stage Product
```

提交 bundle：

```bash
ai-team submit-stage-result --session-id <session_id> --bundle /path/to/bundle.json
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

## bundle 最小结构

```json
{
  "session_id": "<session_id>",
  "stage": "Product",
  "status": "completed",
  "artifact_name": "prd.md",
  "artifact_content": "# PRD\n\n## Acceptance Criteria\n- ...\n"
}
```

## 当前建议

- 日常入口统一使用 `ai-team`
- 不再把 `python3 -m ai_company ...` 当作主入口
- 当前最适合把它理解成一个“CLI runtime + 团队框架”，不是自动一键全跑的黑盒
