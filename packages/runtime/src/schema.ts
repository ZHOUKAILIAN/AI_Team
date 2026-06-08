import { z } from "zod";

export const ProfileSchema = z.enum(["quick", "investigate", "full"]);
export type RuntimeProfile = z.infer<typeof ProfileSchema>;

export const WorkflowStatusSchema = z.enum(["in_progress", "waiting_human", "blocked", "done"]);
export type WorkflowStatus = z.infer<typeof WorkflowStatusSchema>;

export const AgentRoleSchema = z.enum([
  "planner",
  "repo_scout",
  "test_scout",
  "writer",
  "verifier",
  "summarizer",
  "route",
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

export const SessionSchema = z.object({
  schema_version: z.literal(1),
  session_id: z.string(),
  request: z.string(),
  profile: ProfileSchema,
  status: WorkflowStatusSchema,
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

export const WorkflowStepSchema = z.object({
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
export type WorkflowStep = z.infer<typeof WorkflowStepSchema>;

export const WorkflowSchema = z.object({
  schema_version: z.literal(1),
  session_id: z.string(),
  profile: ProfileSchema,
  status: WorkflowStatusSchema,
  current_stage: z.string(),
  steps: z.array(WorkflowStepSchema),
  summary: z.string().default(""),
  blocked_reason: z.string().default(""),
  files_changed: z.array(z.string()).default([]),
  commands_run: z.array(z.string()).default([]),
  updated_at: z.string(),
});
export type WorkflowRecord = z.infer<typeof WorkflowSchema>;

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
  runner: z.enum(["openai_sandbox", "local_fallback"]),
  input: z.string(),
  output: z.string().default(""),
  started_at: z.string(),
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
  runner: z.enum(["openai_sandbox", "local_fallback"]).optional(),
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

export const RunResultSchema = z.object({
  session_id: z.string(),
  status: WorkflowStatusSchema,
  profile: ProfileSchema,
  state_root: z.string(),
  session_dir: z.string(),
  repo_root: z.string(),
  current_stage: z.string(),
  summary: z.string(),
  blocked_reason: z.string().default(""),
});
export type RunResult = z.infer<typeof RunResultSchema>;

export const RuntimeConfigSchema = z.object({
  schema_version: z.literal(1),
  default_profile: ProfileSchema.default("quick"),
  default_model: z.string().default("gpt-5.4-mini"),
  state_root: z.string().default(".agt"),
  max_turns: z
    .object({
      quick: z.number().int().positive().default(4),
      investigate: z.number().int().positive().default(5),
      full: z.number().int().positive().default(8),
    })
    .default({
      quick: 4,
      investigate: 5,
      full: 8,
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
  human_gates: z.boolean().default(false),
});
export type RuntimeConfig = z.infer<typeof RuntimeConfigSchema>;

export const SessionIndexEntrySchema = z.object({
  session_id: z.string(),
  request: z.string(),
  status: WorkflowStatusSchema,
  current_stage: z.string(),
  profile: ProfileSchema,
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

// 返回当前时间的 ISO 字符串，用作所有 runtime 记录的统一时间格式。
// Returns the current time as an ISO string for all runtime records.
export function nowIso(): string {
  return new Date().toISOString();
}
