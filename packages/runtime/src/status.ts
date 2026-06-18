import type {
  AgentRunRecord,
  DeliveryBlocker,
  DeliveryWorkflowPhase,
  DeliveryWorkflowRecord,
  EvidenceRef,
  ExecutionWorkflowRecord,
  RuntimeEvent,
  SessionRecord,
  ToolCallRecord,
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
  delivery_status: string;
  execution_status: string;
  runtime_status: SessionRuntimeStatus;
  current_phase: string;
  current_stage: string;
  repo_root: string;
  state_root: string;
  summary: string;
  blocked_reason: string;
  phases: DeliveryWorkflowPhase[];
  blockers: DeliveryBlocker[];
  evidence_refs: EvidenceRef[];
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
  const [session, deliveryWorkflow, executionWorkflow, agentRuns, events, toolCalls] = await Promise.all([
    store.loadSession(sessionId),
    store.loadDeliveryWorkflow(sessionId),
    store.loadExecutionWorkflow(sessionId),
    store.listAgentRuns(sessionId),
    store.readEvents(sessionId),
    store.readToolCalls(sessionId),
  ]);
  return buildSessionStatusSnapshot({
    session,
    deliveryWorkflow,
    executionWorkflow,
    agentRuns,
    events,
    toolCalls,
    stalledAfterMs: options.stalledAfterMs,
    now: options.now,
  });
}

export function buildSessionStatusSnapshot(args: {
  session: SessionRecord;
  deliveryWorkflow: DeliveryWorkflowRecord;
  executionWorkflow: ExecutionWorkflowRecord;
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
    workflow_status: args.deliveryWorkflow.status,
    delivery_status: args.deliveryWorkflow.status,
    execution_status: args.executionWorkflow.status,
    runtime_status: sessionRuntimeStatus(args.deliveryWorkflow, activeRunStatus, latestRunStatus),
    current_phase: args.deliveryWorkflow.current_phase,
    current_stage: args.executionWorkflow.current_stage,
    repo_root: args.session.repo_root,
    state_root: args.session.state_root,
    summary: args.deliveryWorkflow.summary || args.executionWorkflow.summary,
    blocked_reason: args.deliveryWorkflow.blockers.find((blocker) => blocker.status === "open")?.reason ?? args.executionWorkflow.blocked_reason,
    phases: args.deliveryWorkflow.phases,
    blockers: args.deliveryWorkflow.blockers,
    evidence_refs: args.deliveryWorkflow.evidence_refs,
    stalled_after_ms: stalledAfterMs,
    active_run: activeRunStatus,
    latest_run: latestRunStatus,
    latest_event: args.events?.at(-1) ?? null,
    latest_tool_call: args.toolCalls?.at(-1) ?? null,
    updated_at: args.session.updated_at,
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
  deliveryWorkflow: DeliveryWorkflowRecord,
  activeRun: AgentRunStatusSnapshot | null,
  latestRun: AgentRunStatusSnapshot | null,
): SessionRuntimeStatus {
  if (activeRun) {
    return activeRun.runtime_status === "stalled" ? "stalled" : "running";
  }
  if (deliveryWorkflow.status === "done" || deliveryWorkflow.status === "waiting_human") {
    return deliveryWorkflow.status;
  }
  if (latestRun?.status === "failed") {
    return "failed";
  }
  if (deliveryWorkflow.status === "blocked") {
    return latestRun?.executor_status === "timeout" ? "timeout" : "blocked";
  }
  return "in_progress";
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
