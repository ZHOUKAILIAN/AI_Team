# Protocol-Owned Output Contract

Date: 2026-05-19

## 背景

RW-001 真实运行中暴露出一个结构性问题：模型执行了任务，但在输出协议字段时生成了框架不稳定消费的 key。

典型例子：

- runtime contract 要求 evidence key：`self_verification`
- 模型输出：`self_verification_check`、`self_verification_semantics`

这说明当前设计把“协议结构”和“业务内容”都交给模型生成，导致状态机、gate、统计与回溯依赖的 key 可能漂移。

## 目标

建立一套 **Protocol-Owned Output Contract**：

> runtime 拥有协议结构和状态流转；模型只执行 stage 任务并填充内容 value。

## 核心原则

1. **Runtime owns keys**
   - 所有影响状态机、gate、统计、回溯、文件路由、证据匹配的 key 都由 runtime 生成或枚举约束。

2. **Model fills values**
   - 模型负责填写文档内容、summary、issue、lesson、risk、command 描述、metadata 等自然语言或业务内容。

3. **State machine consumes runtime verdicts, not raw model output**
   - 模型输出只是 StageCandidate。
   - runtime 经过协议校验、客观校验、语义/治理校验后生成 StageVerdict。
   - 状态机只消费 StageVerdict。

4. **Result is slot-based**
   - 不依赖 `status = "passed"` 这种单个 value 驱动状态。
   - 使用互斥结果槽：`passed` / `failed` / `blocked`。
   - exactly one slot must be filled.

## Runtime-owned fields

以下字段属于 runtime-owned，不允许模型自由发明或改名：

- `stage`
- `status` / verdict state
- `artifact_name`
- `artifact_key`
- evidence keys
- finding ids
- `target_stage`
- `severity`
- `completion_signal`
- `acceptance_status`
- `current_state`
- `next_state`
- `required_outputs`
- `required_evidence`

## Model-owned values

以下内容可以由模型生成：

- `artifact_content`
- `summary`
- `journal`
- `issue`
- `lesson`
- `risk`
- `rollback`
- `command` 描述
- evidence 内部说明
- finding 的自然语言解释
- `metadata` 内的业务细节

## StageCandidate

模型输出的结果是候选结果，不直接驱动状态机。

建议结构：

```json
{
  "artifact_content": "<model-filled document>",
  "evidence_by_name": {
    "self_code_review": {
      "kind": "artifact",
      "summary": "<model-filled>",
      "artifact_path": "implementation.md",
      "metadata": {
        "checks": ["scope", "non_goals", "file_list"]
      }
    },
    "self_verification": {
      "kind": "command",
      "summary": "<model-filled>",
      "command": "npm run check",
      "exit_code": 0,
      "metadata": {
        "checks": ["file_presence", "package_json", "workspace"]
      }
    }
  },
  "findings_by_id": {},
  "candidate_result": {
    "passed": {
      "reason": "<model recommendation>"
    },
    "failed": null,
    "blocked": null
  }
}
```

注意：

- `self_code_review` / `self_verification` 由 contract 生成，不由模型命名。
- 模型不得输出 `self_verification_check` 替代 `self_verification`。
- 细分检查项放进 `metadata.checks`。

## StageVerdict

runtime 校验 StageCandidate 后生成 StageVerdict。

```json
{
  "stage": "Implementation",
  "verdict": {
    "passed": {
      "reason": "Runtime verified required outputs and evidence.",
      "validated_outputs": ["README.md", ".gitignore", "package.json", "pnpm-workspace.yaml"],
      "validated_evidence": ["self_code_review", "self_verification"]
    },
    "failed": null,
    "blocked": null
  }
}
```

状态机只消费 StageVerdict，不直接消费模型的 `candidate_result`。

## Slot-based Result Union

结果槽必须满足 exactly one active slot：

- `passed != null` 且 `failed == null` 且 `blocked == null`
- 或 `failed != null` 且 `passed == null` 且 `blocked == null`
- 或 `blocked != null` 且 `passed == null` 且 `failed == null`

如果多个槽被填或全部为空，属于 protocol failure。

## 状态流转

状态流转由 runtime 状态机决定：

- `Implementation verdict.passed` → `Verification`
- `Verification verdict.failed` → `Implementation`
- `GovernanceReview verdict.passed` → `Acceptance`
- `GovernanceReview verdict.passed_with_cautions` → `Acceptance`
- `GovernanceReview verdict.blocked` → `Blocked`
- `Acceptance verdict.failed.rework_target = Implementation` → `Implementation`
- `Acceptance verdict.failed` 且无 `rework_target` → `WaitForHumanDecision`
- `SessionHandoff verdict.passed` → `WaitForHumanDecision`
- human `go` → `Done`

模型可以建议下一步，但不能驱动状态转移。

## Validator layers

每个 stage 的推进至少经过三层验证：

1. Protocol validation
   - schema valid
   - required protocol keys present
   - enum legal
   - exactly one result slot active
   - no unknown required key substitution

2. Objective validation
   - required files exist
   - commands actually succeeded
   - evidence fields exist
   - no out-of-scope files
   - artifact written

3. Semantic / governance validation
   - 内容是否符合需求
   - finding 是否阻塞
   - acceptance 是否应 go/no-go
   - rework target 是否合理

## Diagnostics

协议错误必须和任务失败分开。

示例：

```text
Protocol violation:
- required evidence key missing: self_verification
- unknown evidence key: self_verification_check

Fix:
Use exact key self_verification.
Move sub-check details into metadata.checks.
```

不要把此类问题笼统报成 `Implementation failed`。

## Implementation plan

### P0

1. 回滚 prefix evidence matching。
2. gate 恢复 exact evidence key match。
3. 增加 near-match diagnostics，但不放行。
4. prompt 明确 required evidence key 必须逐字使用。
5. 支持 `evidence_by_name` 输入并 normalize 到内部 `evidence[]`。

### P1

1. 由 StageContract 生成 evidence template。
2. 引入 StageCandidate / StageVerdict 数据模型。
3. 引入 slot-based result union。
4. 状态机改为消费 StageVerdict。

### P2

1. 拆分 protocol failure / task failure / governance failure / executor failure。
2. 为每个 stage 增加 objective validators。
3. UI/CLI 显示 candidate、verdict、state transition 的分层诊断。
