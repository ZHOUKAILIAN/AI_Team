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

## ⚙️ 工作流与双模式机制
基于 Codex Agent 的能力设定，本项目支持两者不同的执行流转模式：

### 模式 A：端到端自动流转 (端到端运行 `/build-e2e`)
适用于边界清晰、容易闭环的小型需求。AI 将接管全局调度：
- 您仅需触发 `/build-e2e`，AI 将自动依次执行 Product -> Dev -> QA -> Ops 的流转。
- 您（CEO）只在最后环节被 `@` 唤醒进行 Acceptance（验收）的最终确认。

### 模式 B：分步交互模式 (Step-by-Step)
适用于大型史诗级需求（Epic），在每一个环节交付定稿前都需要您进行强管控。
1. **产品设计**：运行 `/product`。在 `.ai_company_state/artifacts/` 产出 PRD 与需求文档。
2. **技术实现**：运行 `/dev`。依据 PRD 进行架构设计与干净利落的代码落地。
3. **质量检测**：运行 `/qa`。根据 PRD 维度进行严格测试，如报错则自驱打回 Dev 修复。
4. **最终验收**：运行 `/acceptance`。作为最后把关，确认业务价值和端到端可用性。
5. **增长与反馈**：运行 `/ops`。追踪数据发布记录并回传市场反馈。

*注：所有角色的上下文记忆、交接文档与会话日志均存放在 `.ai_company_state/` 私有目录，实现与代码仓库的物理隔离。*

## 🧠 本地运行时与学习闭环
当前仓库已经内置一个可执行的本地 workflow engine，默认执行链路为：

`Product -> Dev -> QA -> Acceptance`

与原始文档式工作流相比，这一版多了三个关键能力：
- **全程留痕**：每个阶段都会生成 artifact、journal、findings，并写入 session。
- **可审计 diff**：每次运行都会生成 `review.md`，自动附带阶段产物之间的 diff。
- **学习闭环**：如果下游阶段发现问题，会把 lesson、context patch、skill patch 回写到 `.ai_company_state/memory/<Role>/`，下一轮执行时自动叠加到对应 agent 的有效上下文中。

### 目录说明
- `Product/`、`Dev/`、`QA/`、`Acceptance/`、`Ops/`：角色的种子身份定义，包含 `context.md`、`memory.md`、`SKILL.md`
- `.ai_company_state/sessions/<session_id>/`：一次完整运行的全过程日志
- `.ai_company_state/artifacts/<session_id>/`：阶段产物，如 `prd.md`、`tech_spec.md`、`qa_report.md`、`acceptance_report.md`
- `.ai_company_state/memory/<Role>/`：运行时学习叠加层，保存 `lessons.md`、`context_patch.md`、`skill_patch.md`

### 命令
先初始化状态目录：

```bash
python3 -m ai_company init-state
```

运行一次完整闭环：

```bash
python3 -m ai_company run --request "实现一个可以持续自学习的 AI 公司闭环" --print-review
```

查看最近一次 review：

```bash
python3 -m ai_company review
```

### agent-friendly 模式
如果是人直接在终端里操作，还是可以用 `run`。但如果是 agent 接到你的自然语言需求，推荐直接走 `agent-run`，把你的原话完整传进去：

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

### 安装成 Codex Skill
如果你想后面在别的 Codex 会话里复用这套能力，直接安装仓库内置 skill：

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

这个 skill 的职责是触发和路由，真正执行仍然会落到仓库里的：

```bash
python3 -m ai_company agent-run --message "<你的原话>" --print-review
```

### 学习闭环如何工作
1. `Product` 把原始需求转成 PRD，并显式写出验收标准。
2. `Dev` 基于 PRD 产出技术方案。
3. `QA` 检查交接质量，发现问题时输出结构化 finding。
4. `Acceptance` 以 finding 作为最终闸门，决定 `accepted` 或 `rejected`。
5. 主控 orchestrator 把 finding 定向回写到目标角色的运行时记忆层。
6. 下一轮加载角色时，会自动把这些学习记录叠加进有效 context / skill / memory，形成持续增强。

### 当前边界
- 默认 backend 是**确定性模板后端**，适合演示流程、记忆演进、diff 和 review。
- 如果要让 `Dev` 阶段真的调用 LLM 去改代码、让 `QA` 跑真实浏览器或测试套件，可以在此 runtime 之上替换 backend，而不需要重写主控、状态存储和学习闭环。

---
*致力于通过智能体（Agentic AI）协作模式构建高效自主化运转的软件体系。*
