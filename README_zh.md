# 一人 AI 公司 (One-Person AI Company)

**语言策略 / Language Policy**：
这份说明文档提供[英文版 (English)](README.md)与中文版。但为了保持 AI 协作的最高效能与沟通一致性，各角色目录内部的上下文、记忆体和入职手册（`context.md`）均严格采用**英文**。

**仓库地址**：`git@github.com:ZHOUKAILIAN/AI_Team.git`

---

## 🌟 项目简介
欢迎来到 **一人 AI 公司**！本项目模拟了一个完整的软件科技公司架构，由一个人与多个专业 AI 角色协作运营。通过定义清晰的角色、职责和工作流，我们将独立的单人开发者转变为一个全功能、跨领域的完整产品交付团队。

## 🏢 公司组织架构
我们的公司分为五个核心部门，每个部门都有其专属的角色设定、工作基调和特定职责：

### 1. 📢 产品经理 (Product Manager) - `/Product`
- **角色**：定义“做什么”以及“为什么做”。
- **基调**：专业、严谨、以用户为中心。
- **职责**：把控产品愿景、撰写需求文档（PRD）、管理价值交付，对齐各方目标。

### 2. 💻 软件研发 (Software Engineer) - `/Dev`
- **角色**：将产品需求转化为健壮的、可工作的软件实现。
- **基调**：极客、严谨、高效。
- **职责**：技术落地、系统架构设计、把控代码质量。

### 3. 🛡️ 质量保证 (QA Engineer) - `/QA`
- **角色**：产品交付前的最后一道质量防线。
- **基调**：细致入微、严谨、专业、对缺陷零容忍。
- **职责**：质量保证、风险控制、制定测试策略与用例覆盖、缺陷管理。

### 4. ⚖️ 验收经理 (Acceptance Manager) - `/Acceptance`
- **角色**：作为 QA 之外的最后一层端到端验证，确认产品是否真正解决业务场景和用户问题的终极把关人。
- **基调**：全局观、客观、以交付为导向。
- **职责**：业务价值验证、需求满足度核查、发布准备及流程完整度监督。

### 5. 🚀 运营经理 (Operations Manager) - `/Ops`
- **角色**：驱动体验，促进用户增长并确保产品上线后的交互活跃度。
- **基调**：富有同理心、专业、高效、具创新力。
- **职责**：用户增长策略、宣发上市活动、构建市场反馈闭环、赋能用户。

## ⚙️ 工作流契约（权威）
真实工作流契约为：

`Product -> CEO 批准 -> Dev <-> QA -> Acceptance -> 人类 Go/No-Go 决策`

含义如下：
- Product 先产出需求与目标。
- 必须先经过 CEO 批准，Dev 才能进入实现。
- Dev 与 QA 双向迭代，直到关键验证证据完整。
- Acceptance 给出最终建议。
- 最终 Go/No-Go 由人类决策。

角色边界：
- Dev 内部可以使用自己的实现方法论和自验证方式，但这些都不属于 QA。
- QA 必须独立重跑关键验证，不能只接受 Dev 的口头结论。
- 缺少证据必须 blocked。

每次会话必须产出的契约文档：
- `prd.md`
- `implementation.md`
- `qa_report.md`
- `acceptance_report.md`
- `workflow_summary.md`

正常使用时推荐的入口：
- 一次性本地初始化：`./scripts/company-init.sh`
- 日常执行入口：`$ai-team-run`

*注：所有角色的上下文记忆、交接文档与会话日志均存放在 `.ai_company_state/` 私有目录，实现与代码仓库的物理隔离。*

## 🚀 快速启动
如果你要在这个仓库里使用真正的项目级 AI_Team 工作流，推荐这样启动：

1. 先确保 Codex 是在这个仓库的项目根目录打开的。

2. 先为当前 clone 生成本地隐藏的 Codex 文件：

```bash
./scripts/company-init.sh
```

3. 再把一个需求丢进流程：

```text
$ai-team-run
```

如果你更喜欢 shell，也可以在项目根目录下执行：

```bash
./scripts/company-init.sh
./scripts/company-run.sh "执行这个需求：<你的需求>"
```

`company-init.sh` 会按需生成项目本地的 `.codex/` 与 `.agents/` 文件，并保持它们不进入 git。

正常使用时，优先走项目根目录 helper 加 repo 本地 run skill，不建议让用户自己执行 `python3 -m ai_company ...`。

## ✅ 这套流程能做什么
这套流程的目标，是把一个需求真正跑过多角色交接，而不是退化成只有 Dev 自证的单角色流程。

它会做这些事：
- Product 先写 `prd.md`，并在进入 Dev 之前把验收标准写清楚。
- Product 完成后，流程会停一次，等 CEO 批准。
- Dev 负责实现，并把自己的自验证与命令证据写进 `implementation.md`。
- QA 必须独立重跑关键验证，并把结果写进 `qa_report.md`。
- 如果 QA 失败，会自动回到 Dev 修复后再重测。
- Acceptance 只输出 AI 验收建议，写入 `acceptance_report.md`；如果是可执行的 `recommended_no_go` / `blocked`，也可以把结构化 finding 定向回 Product 或 Dev。
- 人类反馈也可以通过 `record-feedback` 进入同一条学习闭环。
- 最终 Go/No-Go 仍然由人来决定。

## 🧾 会不会记录，记录放哪里
会，这套流程会把每次 session 的记录都落到本地。

主要存储位置：
- `.ai_company_state/artifacts/<session_id>/`：本轮必须交接的产物，比如 `prd.md`、`implementation.md`、`qa_report.md`、`acceptance_report.md`、`workflow_summary.md`；如果声明了 review contract，还会包含 `acceptance_contract.json`、`review_completion.json` 这类机器可读审查产物
- `.ai_company_state/sessions/<session_id>/`：每个阶段的 journal、findings、元数据，以及 `review.md`
- `.ai_company_state/memory/<Role>/`：从下游 finding 回写的 lessons 和 patch

如果你想最快看懂这一轮当前跑到哪，先看 `workflow_summary.md`。

## 🧠 本地运行时与学习闭环
当前仓库已经内置一个可执行的本地 workflow engine，其元数据链路与以下契约一致：

`Product -> CEO 批准 -> Dev <-> QA -> Acceptance -> 人类 Go/No-Go 决策`

与原始文档式工作流相比，这一版多了三个关键能力：
- **全程留痕**：每个阶段都会生成 artifact、journal、findings，并写入 session。
- **可审计 diff**：每次运行都会生成 `review.md`，自动附带阶段产物之间的 diff。
- **学习闭环**：如果下游阶段发现问题，会把 lesson、context patch、skill patch 回写到 `.ai_company_state/memory/<Role>/`，下一轮执行时自动叠加到对应 agent 的有效上下文中。
- **标准化学习叠加层**：学习记录会保存可复用规则和明确的 completion signal，而不是模糊摘要。

### 目录说明
- `Product/`、`Dev/`、`QA/`、`Acceptance/`、`Ops/`：角色的种子身份定义，包含 `context.md`、`memory.md`、`SKILL.md`
- `.codex/agents/`：通过 `./scripts/company-init.sh` 按需生成的项目本地 Codex 子代理，覆盖 `Product`、`Dev`、`QA`、`Acceptance`
- `.agents/skills/ai-team-run/`：通过 `./scripts/company-init.sh` 按需生成的项目本地执行 skill
- `.ai_company_state/sessions/<session_id>/`：一次完整运行的全过程日志
- `.ai_company_state/artifacts/<session_id>/`：阶段产物，如 `prd.md`、`implementation.md`、`qa_report.md`、`acceptance_report.md`、`workflow_summary.md`、`acceptance_contract.json`，以及 `review_completion.json` 这类 review artifacts
- `.ai_company_state/memory/<Role>/`：运行时学习叠加层，保存 `lessons.md`、`context_patch.md`、`skill_patch.md`

### 命令
这些是偏底层的维护命令。正常使用时，优先在项目根目录打开 Codex，先执行一次 `./scripts/company-init.sh`，后续通过 `$ai-team-run` 运行。

先初始化状态目录：

```bash
python3 -m ai_company init-state
```

初始化项目级 Codex workflow 配置：

```bash
python3 -m ai_company codex-init
```

运行一次完整闭环（`run` 和 `agent-run` 是确定性/演示 runtime 命令）：

```bash
python3 -m ai_company run --request "实现一个可以持续自学习的 AI 公司闭环" --print-review
```

查看最近一次 review：

```bash
python3 -m ai_company review
```

把人工反馈记成结构化 learning finding：

```bash
python3 -m ai_company record-feedback --session-id <session_id> --source-stage Acceptance --target-stage Dev --issue "<问题>" --lesson "<经验>" --context-update "<约束>" --skill-update "<目标>"
```

如果是 page-root 视觉还原或 `<= 0.5px` 的 Figma 验收，必备证据集是 `runtime_screenshot`、`overlay_diff`、`page_root_recursive_audit`。

机器可读的 native-node policy 在 `ai_company/acceptance_policy.json`；它会把 `wechat_native_capsule` 这类宿主原生节点排除出业务 diff，只要求检查 safe-area avoidance。

如果某个 session 声明了 review contract，`start-session` 会落盘 `acceptance_contract.json` 并预生成 `review_completion.json`。只有当 `review_completion.json` 明确声明审查完成，且必需 artifact / evidence 全部覆盖后，Acceptance 才能结束这一轮。

宿主工具和本机环境变更默认一律拦截。如果 QA 或 Acceptance 需要重启外部工具、修改本机配置，流程必须先停下来等待用户显式批准。

### 项目级 Codex 集成
这个仓库支持官方 project-scoped Codex 集成，但隐藏文件改为本地按需生成，不再直接跟踪进 git：

- `.codex/agents/*.toml`：`Product`、`Dev`、`QA`、`Acceptance` 的本地子代理
- `.agents/skills/ai-team-run/`：本地执行 skill

最佳实践：
- 在项目根目录打开 Codex
- 每个 clone 先执行一次 `./scripts/company-init.sh`
- 日常执行优先使用 `$ai-team-run`

这些生成出来的隐藏文件都被 git 忽略，所以 fresh clone 会保持干净。

手动 shell 兜底：

```bash
./scripts/company-init.sh
./scripts/company-run.sh "执行这个需求：做一个支持下游纠偏和自学习的 AI 公司流程"
```

### agent-friendly 模式
如果是人直接在终端里操作，可以用 `run` 查看确定性/演示 runtime 元数据。如果是 agent 接到你的自然语言需求，推荐直接走 `agent-run`，把你的原话完整传进去（同样是确定性/演示 runtime 元数据）：

```bash
python3 -m ai_company agent-run --message "执行这个需求：做一个支持下游纠偏和学习闭环的 AI 公司流程" --print-review
```

这一层会自动做两件事：
- 识别是否是自然语言触发语句
- 从你的原话里提取真正的需求内容，再执行完整 workflow

推荐给 agent 的触发句式：
- `/company-run ...`
- `执行这个需求：...`
- `按 AI Company 流程跑这个需求：...`
- `按 AI Company 流程执行：...`

如果消息里没有匹配到触发前缀，`agent-run` 会把整条消息当作需求本体执行。

若要走权威工作流 bootstrap，请使用：

```bash
python3 -m ai_company start-session --message "<你的原话>"
```

### 安装成 Codex Skill
如果你想在这个仓库之外复用，直接安装仓库内置的全局 skill：

```bash
./scripts/install-codex-skill.sh
```

安装后 skill 会被复制到：

```bash
~/.codex/skills/ai-company-workflow
```

之后你可以直接对 Codex 说：
- `/company-run 做一个支持下游纠偏和自学习的 AI 公司流程`
- `执行这个需求：做一个支持下游纠偏和自学习的 AI 公司流程`

这个全局 skill 的职责是触发和路由。对用户来说，入口仍然是 skill 本身，bootstrap 会由 helper script 在内部处理。

### 一键全局安装
如果是别的小伙伴在另一台电脑上安装，推荐直接走一键安装脚本。它会同时做两件事：
- 把 skill 安装到 `~/.codex/skills/ai-company-workflow`
- 把运行时仓库 vendor 到 `~/.codex/vendor/ai-team`

如果仓库是公开的，可以直接运行：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ZHOUKAILIAN/AI_Team/main/scripts/install-codex-ai-team.sh)
```

如果已经 clone 了仓库，也可以直接运行：

```bash
./scripts/install-codex-ai-team.sh
```

安装完成后，Codex 侧推荐直接使用：
- `/company-run 做一个支持下游纠偏和自学习的 AI 公司流程`
- `执行这个需求：做一个支持下游纠偏和自学习的 AI 公司流程`

安装后的稳定运行时位置是：

```bash
~/.codex/vendor/ai-team
```

安装后的 skill 内部会优先调用：

```bash
~/.codex/skills/ai-company-workflow/scripts/company-run.sh "<你的原话>"
```

### 学习闭环如何工作
1. `Product` 把原始需求转成 PRD，并显式写出验收标准。
2. `Dev` 基于 PRD 落实现，并把自验证与命令证据写入 `implementation.md`。
3. `QA` 独立重跑关键验证，发现问题时输出结构化 finding。
4. `Acceptance` 基于这些证据给出 AI 验收建议；如果是可执行的 no-go，也可以继续产出新的 finding 回流给 `Product` 或 `Dev`。
5. 人类反馈也可以通过 `record-feedback` 归一化为结构化 finding。
6. 主控 orchestrator 把 finding 定向回写到目标角色的运行时记忆层。
7. 下一轮加载角色时，会自动把这些学习记录叠加进有效 context / skill / memory，形成持续增强。
8. 视觉还原类 finding 可以显式声明 `runtime_screenshot`、`overlay_diff`、`page_root_recursive_audit` 这类 required evidence，避免把“测试绿了”误当成最终视觉签收。

### 当前边界
- 默认 backend 是**确定性模板后端**，适合演示流程、记忆演进、diff 和 review。
- 它输出的 `acceptance_status` 只是建议态（`recommended_go`、`recommended_no_go`、`blocked`），workflow summary 最终会停在 `WaitForHumanDecision`，不是最终发布批准。
- 如果要让 `Dev` 阶段真的调用 LLM 去改代码、让 `QA` 跑真实浏览器或测试套件，可以在此 runtime 之上替换 backend，而不需要重写主控、状态存储和学习闭环。

## 文档与 SOP

### 标准操作流程
- **[文档驱动 AI 团队开发 SOP](docs/SOP_简洁版.md)**: 面向中文使用者的文档驱动需求整理、执行与验收指南。

### 与 ai-doc-driven-dev 集成
SOP 描述了推荐的两阶段工作流：
1. **阶段一**：使用 `ai-doc-driven-dev` 初始化结构化文档。
2. **阶段二**：使用 `AI_Team` 通过多角色 AI 协作执行已经文档化的需求。

这形成了一个完整闭环：**文档化 -> 执行 -> 验证 -> 学习**

---
*致力于通过智能体（Agentic AI）协作模式构建高效自主化运转的软件体系。*
