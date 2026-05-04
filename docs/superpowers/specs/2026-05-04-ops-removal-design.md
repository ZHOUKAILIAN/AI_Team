# Ops Removal 设计说明

日期：2026-05-04

## 背景

当前项目的默认流程是 `Product -> TechPlan -> Dev -> QA -> Acceptance`。`Ops` 只作为预留角色资产存在，没有进入默认执行链路，也没有参与 `run` / `dev` 的自动阶段推进。

这会带来两个问题：

- 项目定位里多了一个当前不用的角色，增加理解和维护成本。
- 角色资产、文档、默认加载列表里保留了一个不参与主流程的分支，后续 prompt / skill / role 约定会持续产生噪音。

## 目标

删除默认使用场景里的 `Ops`，让项目只保留实际在用的五个阶段：

- Product
- TechPlan
- Dev
- QA
- Acceptance

同时保留少量兼容兜底，避免老 session、历史 artifact、反馈记录、或外部输入里出现 `Ops` 时直接报错。

## 范围

要移除的内容：

- `Ops/` 目录下的角色文档与 memory 资产。
- `agent_team/assets/roles/Ops/` 目录下的打包资产。
- 默认角色名、README、设计文档、控制台或提示词中对 Ops 的默认展示。
- 任何默认会把 Ops 当成团队成员加载的路径。

要保留的内容：

- `artifact_name_for_stage("Ops") -> release_notes.md` 这种兼容映射。
- 对历史数据中出现的 `Ops` 进行只读解析的容错能力。

## 设计原则

### 1. 主流程只保留真实在用的阶段

默认文档、默认角色列表、默认加载行为都不再出现 Ops。这样新用户和新维护者看到的就是当前真实流程。

### 2. 兼容层只做读，不做主流程扩展

兼容层只用于：

- 读取历史 session
- 读取历史 artifact
- 读取旧反馈或旧 memory

兼容层不应再让 Ops 进入默认 stage machine 或默认执行链路。

### 3. 不做额外迁移

这次删除不引入数据迁移脚本。历史数据仍然保留在磁盘上，只是代码不再把 Ops 当成默认角色。

## 文件边界

需要修改的文件：

- `agent_team/roles.py`
  - 从 `DEFAULT_ROLE_NAMES` 移除 `Ops`。

- `agent_team/project_structure.py`
  - 从默认角色映射里移除 Ops 的角色目录。

- `agent_team/state.py`
  - 保留 `artifact_name_for_stage("Ops")` 的兼容返回值，但不要再把 Ops 作为默认活跃阶段显示。

- `README.md`
  - 删除对 Ops 的默认流程描述和角色列表。

- `Ops/`
  - 删除整个目录。

- `agent_team/assets/roles/Ops/`
  - 删除整个目录。

可能需要同步调整的测试：

- `tests/test_project_structure.py`
- `tests/test_docs.py`
- `tests/test_skill_package.py`
- `tests/test_runtime_driver.py`
- `tests/test_cli.py`

## 行为约束

删除完成后应满足：

- 默认 `agent-team dev` / `agent-team run` 的流程里不会再加载 Ops。
- 新生成的文档不会再把 Ops 写进默认团队介绍。
- 角色/技能列表里不会再出现 Ops，除非用户显式访问历史数据或兼容路径。
- 旧 session 如果引用了 `Ops`，读取阶段名和 artifact 名不会崩。

## 错误处理

- 如果历史 session 的 artifact 中出现 `Ops`，系统继续按兼容映射处理。
- 如果外部输入显式请求 `Ops`，返回明确错误或空结果，不自动扩展为默认角色。
- 删除后若测试还在期待 Ops 默认存在，应更新测试而不是保留过时行为。

## 验收标准

实现完成后必须满足：

- `Ops/` 和 `agent_team/assets/roles/Ops/` 不再存在。
- 默认角色加载列表不包含 Ops。
- README 不再把 Ops 描述成默认团队成员。
- 默认执行链路不再把 Ops 当成阶段。
- 历史数据仍可用，至少不会因为 `Ops` 的 artifact 名称解析而报错。

## 自检

- 删除范围只覆盖当前不用的默认角色，不碰主流程五阶段。
- 保留兼容兜底，避免历史数据破坏。
- 不新增迁移脚本，不扩大变更范围。
