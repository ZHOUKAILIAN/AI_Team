import { z } from "zod";

export const WorkflowStatusSchema = z.enum(["in_progress", "waiting_human", "blocked", "done"]);
export type WorkflowStatus = z.infer<typeof WorkflowStatusSchema>;

export const DeliveryPhaseSchema = z.enum(["requirement", "development", "verification", "handoff"]);
export type DeliveryPhase = z.infer<typeof DeliveryPhaseSchema>;

export const DeliveryPhaseStatusSchema = z.enum(["pending", "in_progress", "waiting_human", "blocked", "passed"]);
export type DeliveryPhaseStatus = z.infer<typeof DeliveryPhaseStatusSchema>;

export const AgentRoleSchema = z.enum([
  "planner",
  "repo_scout",
  "test_scout",
  "writer",
  "verifier",
  "summarizer",
  "route",
  "intake_summary",
  "product",
  "dev",
  "qa",
  "product_definition",
  "project_runtime",
  "technical_design",
  "implementation",
  "verification",
  "governance_review",
  "acceptance",
  "session_handoff",
  "migration",
]);
export type AgentRole = z.infer<typeof AgentRoleSchema>;

export const ToolCallKindSchema = z.enum([
  "agent_run",
  "shell",
  "apply_patch",
  "read_file",
  "list_files",
  "migration",
  "runtime",
]);
export type ToolCallKind = z.infer<typeof ToolCallKindSchema>;

export const WorktreeRecordSchema = z.object({
  path: z.string(),
  branch: z.string().default(""),
  base_ref: z.string().default(""),
  base_commit: z.string().default(""),
  policy_source: z.string().default(""),
  policy_snapshot_path: z.string().default(""),
});
export type WorktreeRecord = z.infer<typeof WorktreeRecordSchema>;

export const RequestSourceSchema = z.object({
  type: z.enum(["file", "directory_file"]),
  path: z.string(),
  sha256: z.string(),
  bytes: z.number().int().nonnegative(),
});
export type RequestSourceRecord = z.infer<typeof RequestSourceSchema>;

export const SessionSchema = z.object({
  schema_version: z.literal(1),
  session_id: z.string(),
  request: z.string(),
  request_sources: z.array(RequestSourceSchema).default([]),
  workflow_id: z.string().default(""),
  delivery_status: WorkflowStatusSchema,
  execution_status: WorkflowStatusSchema,
  status: WorkflowStatusSchema,
  current_phase: DeliveryPhaseSchema,
  project_root: z.string().default(""),
  repo_root: z.string(),
  state_root: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  current_stage: z.string(),
  source: z.enum(["new", "migrated"]),
  prompt_trace_ids: z.array(z.string()).default([]),
  worktree: WorktreeRecordSchema.optional(),
  migration: z
    .object({
      source_root: z.string(),
      source_session_id: z.string(),
      status: z.enum(["complete", "partial"]),
    })
    .optional(),
});
export type SessionRecord = z.infer<typeof SessionSchema>;

export const EvidenceRefSchema = z.object({
  kind: z.enum(["prompt_trace", "artifact", "agent_run", "file", "command", "event"]),
  ref: z.string(),
  role: AgentRoleSchema.optional(),
  path: z.string().default(""),
  summary: z.string().default(""),
});
export type EvidenceRef = z.infer<typeof EvidenceRefSchema>;

export const DeliveryBlockerSchema = z.object({
  id: z.string(),
  phase: DeliveryPhaseSchema,
  source_role: AgentRoleSchema.optional(),
  reason: z.string(),
  status: z.enum(["open", "resolved"]).default("open"),
  evidence_refs: z.array(EvidenceRefSchema).default([]),
  created_at: z.string(),
});
export type DeliveryBlocker = z.infer<typeof DeliveryBlockerSchema>;

export const DeliveryWorkflowPhaseSchema = z.object({
  phase: DeliveryPhaseSchema,
  status: DeliveryPhaseStatusSchema,
  summary: z.string().default(""),
  blockers: z.array(DeliveryBlockerSchema).default([]),
  evidence_refs: z.array(EvidenceRefSchema).default([]),
  started_at: z.string().optional(),
  completed_at: z.string().optional(),
  updated_at: z.string(),
});
export type DeliveryWorkflowPhase = z.infer<typeof DeliveryWorkflowPhaseSchema>;

export const DeliveryWorkflowSchema = z.object({
  schema_version: z.literal(1),
  session_id: z.string(),
  status: WorkflowStatusSchema,
  current_phase: DeliveryPhaseSchema,
  phases: z.array(DeliveryWorkflowPhaseSchema),
  blockers: z.array(DeliveryBlockerSchema).default([]),
  evidence_refs: z.array(EvidenceRefSchema).default([]),
  summary: z.string().default(""),
  updated_at: z.string(),
});
export type DeliveryWorkflowRecord = z.infer<typeof DeliveryWorkflowSchema>;

export const ExecutionWorkflowStepSchema = z.object({
  role: AgentRoleSchema,
  status: z.enum(["pending", "running", "completed", "blocked", "skipped"]),
  agent_run_id: z.string().optional(),
  prompt_trace_id: z.string().default(""),
  artifact_path: z.string().default(""),
  files_changed: z.array(z.string()).default([]),
  commands_run: z.array(z.string()).default([]),
  summary: z.string().default(""),
  started_at: z.string().optional(),
  completed_at: z.string().optional(),
});
export type ExecutionWorkflowStep = z.infer<typeof ExecutionWorkflowStepSchema>;

export const ExecutionWorkflowSchema = z.object({
  schema_version: z.literal(1),
  session_id: z.string(),
  status: WorkflowStatusSchema,
  current_stage: z.string(),
  steps: z.array(ExecutionWorkflowStepSchema),
  summary: z.string().default(""),
  blocked_reason: z.string().default(""),
  files_changed: z.array(z.string()).default([]),
  commands_run: z.array(z.string()).default([]),
  updated_at: z.string(),
});
export type ExecutionWorkflowRecord = z.infer<typeof ExecutionWorkflowSchema>;

export const RuntimeEventSchema = z.object({
  at: z.string(),
  session_id: z.string(),
  kind: z.string(),
  role: AgentRoleSchema.optional(),
  status: z.string().optional(),
  message: z.string().default(""),
  details: z.record(z.string(), z.unknown()).default({}),
});
export type RuntimeEvent = z.infer<typeof RuntimeEventSchema>;

export const AgentRunSchema = z.object({
  schema_version: z.literal(1),
  session_id: z.string(),
  agent_run_id: z.string(),
  role: AgentRoleSchema,
  status: z.enum(["running", "completed", "blocked", "failed"]),
  runner: z.enum(["openai_sandbox", "codex_exec", "local_fallback"]),
  input: z.string(),
  output: z.string().default(""),
  started_at: z.string(),
  last_heartbeat_at: z.string().optional(),
  heartbeat_count: z.number().int().nonnegative().default(0),
  completed_at: z.string().optional(),
  error: z.string().default(""),
  metadata: z.record(z.string(), z.unknown()).default({}),
});
export type AgentRunRecord = z.infer<typeof AgentRunSchema>;

export const PromptTraceSchema = z.object({
  schema_version: z.literal(1),
  prompt_id: z.string(),
  session_id: z.string(),
  role: AgentRoleSchema,
  kind: z.enum(["stage", "runtime"]).default("stage"),
  runner: z.enum(["openai_sandbox", "codex_exec", "local_fallback"]).optional(),
  source: z.string(),
  path: z.string(),
  sha256: z.string(),
  bytes: z.number(),
  created_at: z.string(),
  metadata: z.record(z.string(), z.unknown()).default({}),
});
export type PromptTraceRecord = z.infer<typeof PromptTraceSchema>;

export const ArtifactRecordSchema = z.object({
  schema_version: z.literal(1),
  artifact_id: z.string(),
  session_id: z.string(),
  role: AgentRoleSchema,
  name: z.string(),
  path: z.string(),
  bytes: z.number(),
  created_at: z.string(),
  metadata: z.record(z.string(), z.unknown()).default({}),
});
export type ArtifactRecord = z.infer<typeof ArtifactRecordSchema>;

export const ToolCallSchema = z.object({
  at: z.string(),
  session_id: z.string(),
  agent_run_id: z.string(),
  role: AgentRoleSchema,
  kind: ToolCallKindSchema,
  name: z.string(),
  input: z.record(z.string(), z.unknown()).default({}),
  output: z.record(z.string(), z.unknown()).default({}),
  exit_code: z.number().nullable().optional(),
  duration_ms: z.number().optional(),
});
export type ToolCallRecord = z.infer<typeof ToolCallSchema>;

export const TokenUsageSchema = z.object({
  input_tokens: z.number().int().nonnegative().default(0),
  output_tokens: z.number().int().nonnegative().default(0),
  total_tokens: z.number().int().nonnegative().default(0),
  reasoning_tokens: z.number().int().nonnegative().default(0),
  raw: z.unknown().optional(),
});
export type TokenUsage = z.infer<typeof TokenUsageSchema>;

export const MetricRecordSchema = z.object({
  schema_version: z.literal(1),
  at: z.string(),
  session_id: z.string(),
  workflow_id: z.string(),
  workflow_run_id: z.string(),
  kind: z.string(),
  stage: z.string(),
  role: AgentRoleSchema,
  attempt: z.number().int().positive(),
  stage_started_at: z.string(),
  stage_completed_at: z.string(),
  stage_duration_ms: z.number().int().nonnegative(),
  executor_duration_ms: z.number().int().nonnegative().optional(),
  runner: z.string().optional(),
  agent_run_id: z.string().optional(),
  executor_status: z.string().optional(),
  verdict: z.string().optional(),
  files_changed_count: z.number().int().nonnegative().default(0),
  commands_run_count: z.number().int().nonnegative().default(0),
  artifacts_count: z.number().int().nonnegative().default(0),
  token_usage: TokenUsageSchema.optional(),
  details: z.record(z.string(), z.unknown()).default({}),
});
export type MetricRecord = z.infer<typeof MetricRecordSchema>;

export const RunResultSchema = z.object({
  session_id: z.string(),
  status: WorkflowStatusSchema,
  delivery_status: WorkflowStatusSchema,
  execution_status: WorkflowStatusSchema,
  state_root: z.string(),
  session_dir: z.string(),
  repo_root: z.string(),
  current_phase: DeliveryPhaseSchema,
  current_stage: z.string(),
  summary: z.string(),
  blocked_reason: z.string().default(""),
});
export type RunResult = z.infer<typeof RunResultSchema>;

export const ProductDevQaStageRoleSchema = z.enum(["intake_summary", "product", "dev", "qa"]);
export type ProductDevQaStageRole = z.infer<typeof ProductDevQaStageRoleSchema>;

export const ProductDevQaStageStepSchema = z.enum(["technical_plan", "implementation"]);
export type ProductDevQaStageStep = z.infer<typeof ProductDevQaStageStepSchema>;

export const ProductDevQaWorkflowRunStatusSchema = z.enum([
  "created",
  "running",
  "waiting_human",
  "blocked",
  "done",
  "cancelled",
]);
export type ProductDevQaWorkflowRunStatus = z.infer<typeof ProductDevQaWorkflowRunStatusSchema>;

export const ProductDevQaWorkflowRunSchema = z.object({
  schema_version: z.literal(1),
  workflow_id: z.literal("product-dev-qa"),
  workflow_run_id: z.string(),
  session_id: z.string(),
  request: z.string(),
  status: ProductDevQaWorkflowRunStatusSchema,
  current_role: ProductDevQaStageRoleSchema.nullable().default(null),
  current_step: ProductDevQaStageStepSchema.nullable().default(null),
  current_stage: z.string(),
  waiting_on: z.enum(["product_check", "dev_plan_check"]).nullable().default(null),
  stage_attempt_counts: z.record(z.string(), z.number().int().nonnegative()).default({}),
  summary: z.string().default(""),
  blocked_reason: z.string().default(""),
  last_stage_key: z.string().default(""),
  last_stage_attempt: z.number().int().nonnegative().default(0),
  last_stage_verdict: z.enum(["passed", "failed", "blocked"]).nullable().default(null),
  last_stage_summary: z.string().default(""),
  last_stage_artifacts: z.array(z.string()).default([]),
  started_at: z.string(),
  updated_at: z.string(),
  completed_at: z.string().nullable().default(null),
});
export type ProductDevQaWorkflowRunRecord = z.infer<typeof ProductDevQaWorkflowRunSchema>;

export const RuntimeConfigSchema = z.object({
  schema_version: z.literal(1),
  default_model: z.string().default("gpt-5.4-mini"),
  state_root: z.string().default(".agt2"),
  executor: z
    .object({
      default_max_turns: z.number().int().positive().default(8),
    })
    .default({
      default_max_turns: 8,
    }),
  task_worktree: z
    .object({
      enabled: z.boolean().default(false),
      base_ref_candidates: z.array(z.string()).default(["origin/test", "origin/main", "test", "main"]),
      branch_prefix: z.string().default("feature/"),
      worktree_root: z.string().default(".worktrees"),
      slug_max_length: z.number().int().positive().default(40),
    })
    .default({
      enabled: false,
      base_ref_candidates: ["origin/test", "origin/main", "test", "main"],
      branch_prefix: "feature/",
      worktree_root: ".worktrees",
      slug_max_length: 40,
    }),
  monitoring: z
    .object({
      heartbeat_interval_ms: z.number().int().positive().default(30_000),
      stalled_after_ms: z.number().int().positive().default(120_000),
    })
    .default({
      heartbeat_interval_ms: 30_000,
      stalled_after_ms: 120_000,
    }),
  human_gates: z.boolean().default(false),
});
export type RuntimeConfig = z.infer<typeof RuntimeConfigSchema>;

export const SessionIndexEntrySchema = z.object({
  session_id: z.string(),
  request: z.string(),
  workflow_id: z.string().default(""),
  delivery_status: WorkflowStatusSchema,
  execution_status: WorkflowStatusSchema,
  status: WorkflowStatusSchema,
  current_phase: DeliveryPhaseSchema,
  current_stage: z.string(),
  project_root: z.string(),
  worktree_path: z.string(),
  state_root: z.string(),
  branch: z.string().default(""),
  base_ref: z.string().default(""),
  base_commit: z.string().default(""),
  updated_at: z.string(),
  created_at: z.string(),
});
export type SessionIndexEntry = z.infer<typeof SessionIndexEntrySchema>;

export const SessionIndexSchema = z.object({
  schema_version: z.literal(1),
  sessions: z.array(SessionIndexEntrySchema).default([]),
});
export type SessionIndex = z.infer<typeof SessionIndexSchema>;

export function formatReadableDateTime(value: string | number | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) {
    return typeof value === "string" ? value : "";
  }
  const year = date.getFullYear();
  const month = padDatePart(date.getMonth() + 1);
  const day = padDatePart(date.getDate());
  const hour = padDatePart(date.getHours());
  const minute = padDatePart(date.getMinutes());
  const second = padDatePart(date.getSeconds());
  return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
}

export function nowReadableDateTime(): string {
  return formatReadableDateTime(new Date());
}

export const nowIso = nowReadableDateTime;

export function compareTimestamps(left: string | undefined, right: string | undefined): number {
  const leftTime = timestampMs(left);
  const rightTime = timestampMs(right);
  if (leftTime !== undefined && rightTime !== undefined) {
    return leftTime - rightTime;
  }
  return (left ?? "").localeCompare(right ?? "");
}

export function latestTimestamp(values: string[]): string | undefined {
  return values.sort((left, right) => compareTimestamps(right, left))[0];
}

function timestampMs(value: string | undefined): number | undefined {
  if (!value) {
    return undefined;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function padDatePart(value: number): string {
  return String(value).padStart(2, "0");
}
