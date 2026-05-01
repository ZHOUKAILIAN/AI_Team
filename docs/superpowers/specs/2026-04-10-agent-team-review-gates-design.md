# Agent Team Review Gates Design

## Goal

Harden Agent Team so review-driven workflows are enforced through machine-readable contracts and completion gates instead of relying on conversational judgment.

## Problem

Recent sessions exposed four systemic gaps:

1. Intake preserved the user's raw message, but did not persist the requested acceptance method, boundary, tolerance, or evidence contract in a structured form.
2. Acceptance could drift from the requested review method because there was no completion gate for review-only workflows such as `figma-restoration-review`.
3. Environment mutations such as changing host-tool configuration were attempted ad hoc instead of being blocked behind explicit user approval.
4. The local `figma-restoration-review` skill contains ambiguity around tolerance handling and lacks platform-native exclusion guidance.

## Design

### 1. Structured Acceptance Contract

Add a machine-readable acceptance contract captured at intake and persisted with the workflow session.

Required fields:
- `review_method`
- `boundary`
- `recursive`
- `tolerance_px`
- `required_dimensions`
- `required_artifacts`
- `required_evidence`
- `native_node_policy`
- `allow_host_environment_changes`

For `figma-restoration-review`, the contract should default to:
- boundary: `page_root` when the message describes a page-level Figma node
- required dimensions: `Structure`, `Geometry`, `Style`, `Content`, `State`
- required artifacts: `deviation_checklist.md`, `review_completion.json`
- required evidence for strict page-root visual parity: `runtime_screenshot`, `overlay_diff`, `page_root_recursive_audit`
- native-node policy: `miniprogram`
- host environment changes: `false` unless explicitly granted

### 2. Review Completion Gate

Add a completion gate that runs after Acceptance and before final closure.

Rules:
- If a session declares a review method, required review artifacts must exist.
- `review_completion.json` must explicitly declare completion instead of relying on free-form prose.
- If the contract requires runtime evidence, missing evidence forces `blocked`.
- If review artifacts are incomplete, the workflow cannot emit a terminal "done" state.

### 3. Environment Mutation Gate

Add an environment gate for host-tool changes.

Rules:
- Host environment changes are denied by default.
- If Acceptance or QA would need to mutate host configuration, restart external tools, or open/close host applications, the workflow should stop with a blocked gate unless the contract explicitly allows those changes.
- The blocked reason must say that explicit user approval is required.

### 4. Review-Only Separation

When the contract declares a read-only review method, Acceptance must not be treated as implementation.

Rules:
- Acceptance may produce findings and route actionable UI gaps back to Dev.
- Acceptance may not claim the review is complete unless the review completion artifact says so.
- Review-only completion and Dev remediation are separate rounds.

### 5. `figma-restoration-review` Skill Fixes

Patch the local skill in `/Users/zhoukailian/Desktop/mySelf/skills/figma-restoration-review/`:
- remove the geometry severity ambiguity where `<= 0.5 px` is both pass and `minor`
- add a platform-native exclusion section for host-owned UI such as `wechat_native_capsule`
- require explicit unresolved items instead of silent omission
- require review outputs that line up with Agent Team's acceptance contract
- make the review-only boundary unambiguous

## Expected Outcome

After this change:
- the user's acceptance method becomes a persistent contract rather than disposable prompt text
- Agent Team cannot silently skip a requested review method
- environment mutations require explicit permission
- `figma-restoration-review` becomes stricter, clearer, and easier to integrate into Agent Team acceptance gates
