import type {
  AgentRunRecord,
  RuntimeEvent,
  SessionRecord,
  ToolCallRecord,
  WorkflowRecord,
  WorkflowStep,
} from "./schema.js";
import type { RuntimeStore } from "./store.js";

export const DEFAULT_STALLED_AFTER_MS = 120_000;

export type AgentRunRuntimeStatus = "running" | "stalled" | "completed" | "blocked" | "failed";

export type SessionRuntimeStatus =
  | "running"
  | "stalled"
  | "in_progress"
  | "waiting_human"
  | "blocked"
  | "timeout"
  | "failed"
  | "done";

export type RequirementStatus = "pending_alignment" | "aligned" | "changed" | "accepted";
export type ImplementationStatus = "not_started" | "in_progress" | "implemented" | "blocked";
export type VerificationStatus = "not_started" | "partial" | "passed" | "failed" | "skipped";
export type TraceStatus = "in_progress" | "complete" | "partial" | "blocked";

export type StatusLayers = {
  requirement_status: RequirementStatus;
  implementation_status: ImplementationStatus;
  verification_status: VerificationStatus;
  trace_status: TraceStatus;
};

export type AgentRunStatusSnapshot = {
  agent_run_id: string;
  role: string;
  runner: string;
  status: AgentRunRecord["status"];
  runtime_status: AgentRunRuntimeStatus;
  started_at: string;
  completed_at?: string;
  last_heartbeat_at?: string;
  heartbeat_count: number;
  elapsed_ms: number;
  heartbeat_age_ms?: number;
  executor_status?: string;
  result_parse_status?: string;
  prompt_trace_id?: string;
};

export type SessionStatusSnapshot = {
  generated_at: string;
  session_id: string;
  request: string;
  profile: string;
  workflow_status: string;
  status_layers: StatusLayers;
  runtime_status: SessionRuntimeStatus;
  current_stage: string;
  repo_root: string;
  state_root: string;
  summary: string;
  blocked_reason: string;
  stalled_after_ms: number;
  active_run: AgentRunStatusSnapshot | null;
  latest_run: AgentRunStatusSnapshot | null;
  latest_event: RuntimeEvent | null;
  latest_tool_call: ToolCallRecord | null;
  updated_at: string;
};

export async function readSessionStatus(
  store: RuntimeStore,
  sessionId: string,
  options: { stalledAfterMs?: number; now?: Date } = {},
): Promise<SessionStatusSnapshot> {
  const [session, workflow, agentRuns, events, toolCalls] = await Promise.all([
    store.loadSession(sessionId),
    store.loadWorkflow(sessionId),
    store.listAgentRuns(sessionId),
    store.readEvents(sessionId),
    store.readToolCalls(sessionId),
  ]);
  return buildSessionStatusSnapshot({
    session,
    workflow,
    agentRuns,
    events,
    toolCalls,
    stalledAfterMs: options.stalledAfterMs,
    now: options.now,
  });
}

export function buildSessionStatusSnapshot(args: {
  session: SessionRecord;
  workflow: WorkflowRecord;
  agentRuns: AgentRunRecord[];
  events?: RuntimeEvent[];
  toolCalls?: ToolCallRecord[];
  stalledAfterMs?: number;
  now?: Date;
}): SessionStatusSnapshot {
  const now = args.now ?? new Date();
  const stalledAfterMs = args.stalledAfterMs ?? DEFAULT_STALLED_AFTER_MS;
  const runs = [...args.agentRuns].sort((left, right) => left.started_at.localeCompare(right.started_at));
  const activeRun = [...runs].reverse().find((run) => run.status === "running") ?? null;
  const latestRun = runs.at(-1) ?? null;
  const activeRunStatus = activeRun ? summarizeAgentRun(activeRun, now, stalledAfterMs) : null;
  const latestRunStatus = latestRun ? summarizeAgentRun(latestRun, now, stalledAfterMs) : null;

  return {
    generated_at: now.toISOString(),
    session_id: args.session.session_id,
    request: args.session.request,
    profile: args.session.profile,
    workflow_status: args.workflow.status,
    status_layers: buildStatusLayers(args.workflow),
    runtime_status: sessionRuntimeStatus(args.workflow, activeRunStatus, latestRunStatus),
    current_stage: args.workflow.current_stage,
    repo_root: args.session.repo_root,
    state_root: args.session.state_root,
    summary: args.workflow.summary,
    blocked_reason: args.workflow.blocked_reason,
    stalled_after_ms: stalledAfterMs,
    active_run: activeRunStatus,
    latest_run: latestRunStatus,
    latest_event: args.events?.at(-1) ?? null,
    latest_tool_call: args.toolCalls?.at(-1) ?? null,
    updated_at: args.session.updated_at,
  };
}

export function buildStatusLayers(workflow: WorkflowRecord): StatusLayers {
  return {
    requirement_status: requirementStatus(workflow),
    implementation_status: implementationStatus(workflow),
    verification_status: verificationStatus(workflow),
    trace_status: traceStatus(workflow),
  };
}

export function summarizeAgentRun(
  run: AgentRunRecord,
  now: Date = new Date(),
  stalledAfterMs: number = DEFAULT_STALLED_AFTER_MS,
): AgentRunStatusSnapshot {
  const end = run.completed_at ? parseIso(run.completed_at) ?? now : now;
  const heartbeatAt = run.last_heartbeat_at ?? run.started_at;
  const heartbeatAgeMs = run.status === "running" ? ageMs(heartbeatAt, now) : undefined;
  const runtimeStatus: AgentRunRuntimeStatus =
    run.status === "running" && heartbeatAgeMs !== undefined && heartbeatAgeMs > stalledAfterMs
      ? "stalled"
      : run.status;
  return {
    agent_run_id: run.agent_run_id,
    role: run.role,
    runner: run.runner,
    status: run.status,
    runtime_status: runtimeStatus,
    started_at: run.started_at,
    completed_at: run.completed_at,
    last_heartbeat_at: run.last_heartbeat_at,
    heartbeat_count: run.heartbeat_count ?? 0,
    elapsed_ms: elapsedMs(run.started_at, end),
    heartbeat_age_ms: heartbeatAgeMs,
    executor_status: stringMetadata(run.metadata.executor_status),
    result_parse_status: stringMetadata(run.metadata.result_parse_status),
    prompt_trace_id: stringMetadata(run.metadata.prompt_trace_id),
  };
}

function sessionRuntimeStatus(
  workflow: WorkflowRecord,
  activeRun: AgentRunStatusSnapshot | null,
  latestRun: AgentRunStatusSnapshot | null,
): SessionRuntimeStatus {
  if (activeRun) {
    return activeRun.runtime_status === "stalled" ? "stalled" : "running";
  }
  if (workflow.status === "done" || workflow.status === "waiting_human") {
    return workflow.status;
  }
  if (latestRun?.status === "failed") {
    return "failed";
  }
  if (workflow.status === "blocked") {
    return latestRun?.executor_status === "timeout" ? "timeout" : "blocked";
  }
  return "in_progress";
}

function requirementStatus(workflow: WorkflowRecord): RequirementStatus {
  if (workflow.status === "done" || stepCompleted(workflow, ["acceptance", "session_handoff"])) {
    return "accepted";
  }
  if (stepHasStatus(workflow, ["product_definition", "technical_design"], ["blocked"])) {
    const changed = workflow.steps.some((step) => step.summary.toLowerCase().includes("rework"));
    return changed ? "changed" : "pending_alignment";
  }
  if (stepCompleted(workflow, ["planner", "repo_scout", "route", "product_definition", "technical_design"])) {
    return "aligned";
  }
  return "pending_alignment";
}

function implementationStatus(workflow: WorkflowRecord): ImplementationStatus {
  if (stepHasStatus(workflow, ["writer", "implementation"], ["blocked"])) {
    return "blocked";
  }
  if (stepHasStatus(workflow, ["writer", "implementation"], ["running"])) {
    return "in_progress";
  }
  if (stepCompleted(workflow, ["writer", "implementation"]) || workflow.files_changed.length > 0) {
    return "implemented";
  }
  return "not_started";
}

function verificationStatus(workflow: WorkflowRecord): VerificationStatus {
  if (stepHasStatus(workflow, ["verifier", "verification", "acceptance"], ["blocked"])) {
    return "failed";
  }
  if (stepHasStatus(workflow, ["verifier", "verification", "acceptance"], ["running"])) {
    return "partial";
  }
  if (stepCompleted(workflow, ["verifier", "verification", "acceptance"])) {
    return "passed";
  }
  if (workflow.status === "done" && implementationStatus(workflow) === "not_started") {
    return "skipped";
  }
  return "not_started";
}

function traceStatus(workflow: WorkflowRecord): TraceStatus {
  if (workflow.status === "done" && !workflow.blocked_reason) {
    return "complete";
  }
  if (workflow.status === "blocked" || workflow.blocked_reason || stepHasStatus(workflow, [], ["blocked"])) {
    return "blocked";
  }
  if (workflow.steps.some((step) => step.status === "pending" || step.status === "running")) {
    return "partial";
  }
  return "in_progress";
}

function stepCompleted(workflow: WorkflowRecord, roles: WorkflowStep["role"][]): boolean {
  return workflow.steps.some((step) => roles.includes(step.role) && step.status === "completed");
}

function stepHasStatus(
  workflow: WorkflowRecord,
  roles: WorkflowStep["role"][],
  statuses: WorkflowStep["status"][],
): boolean {
  return workflow.steps.some(
    (step) => (roles.length === 0 || roles.includes(step.role)) && statuses.includes(step.status),
  );
}

function elapsedMs(startedAt: string, endedAt: Date): number {
  const started = parseIso(startedAt);
  if (!started) {
    return 0;
  }
  return Math.max(0, endedAt.getTime() - started.getTime());
}

function ageMs(value: string, now: Date): number | undefined {
  const date = parseIso(value);
  return date ? Math.max(0, now.getTime() - date.getTime()) : undefined;
}

function parseIso(value: string): Date | undefined {
  const time = Date.parse(value);
  return Number.isFinite(time) ? new Date(time) : undefined;
}

function stringMetadata(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}
