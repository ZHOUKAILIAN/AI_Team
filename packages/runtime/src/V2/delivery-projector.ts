import {
  type AgentRole,
  type DeliveryBlocker,
  type DeliveryPhase,
  type DeliveryPhaseStatus,
  type DeliveryWorkflowPhase,
  type DeliveryWorkflowRecord,
  type EvidenceRef,
  type ExecutionWorkflowRecord,
  latestTimestamp,
} from "./schema.js";

export const DELIVERY_PHASES: DeliveryPhase[] = ["requirement", "development", "verification", "handoff"];

export function createInitialDeliveryWorkflow(sessionId: string, updatedAt: string): DeliveryWorkflowRecord {
  return {
    schema_version: 1,
    session_id: sessionId,
    status: "in_progress",
    current_phase: "requirement",
    phases: DELIVERY_PHASES.map((phase) => ({
      phase,
      status: phase === "requirement" ? "in_progress" : "pending",
      summary: "",
      blockers: [],
      evidence_refs: [],
      updated_at: updatedAt,
    })),
    blockers: [],
    evidence_refs: [],
    summary: "Delivery workflow created.",
    updated_at: updatedAt,
  };
}

export function projectDeliveryWorkflow(
  execution: ExecutionWorkflowRecord,
  previous: DeliveryWorkflowRecord | undefined,
): DeliveryWorkflowRecord {
  const phases = DELIVERY_PHASES.map((phase) => projectPhase(phase, execution, previous));
  const blockers = phases.flatMap((phase) => phase.blockers).filter((blocker) => blocker.status === "open");
  const evidenceRefs = uniqueEvidence(phases.flatMap((phase) => phase.evidence_refs));
  const currentPhase = currentDeliveryPhase(execution, phases);
  const status =
    blockers.length > 0
      ? "blocked"
      : phases.some((phase) => phase.status === "waiting_human")
        ? "waiting_human"
        : phases.every((phase) => phase.status === "passed")
          ? "done"
          : "in_progress";

  return {
    schema_version: 1,
    session_id: execution.session_id,
    status,
    current_phase: currentPhase,
    phases,
    blockers,
    evidence_refs: evidenceRefs,
    summary: deliverySummary(phases, blockers),
    updated_at: execution.updated_at,
  };
}

export function deliveryPhaseForRole(role: AgentRole): DeliveryPhase {
  if (role === "implementation" || role === "writer" || role === "dev") {
    return "development";
  }
  if (role === "verification" || role === "verifier" || role === "governance_review" || role === "acceptance" || role === "qa") {
    return "verification";
  }
  if (role === "session_handoff" || role === "summarizer") {
    return "handoff";
  }
  return "requirement";
}

function projectPhase(
  phase: DeliveryPhase,
  execution: ExecutionWorkflowRecord,
  previous: DeliveryWorkflowRecord | undefined,
): DeliveryWorkflowPhase {
  const steps = execution.steps.filter((step) => deliveryPhaseForRole(step.role) === phase);
  const previousPhase = previous?.phases.find((item) => item.phase === phase);
  const evidenceRefs = uniqueEvidence(steps.flatMap(evidenceRefsForStep));
  const stepBlockers = steps
    .filter((step) => step.status === "blocked")
    .map((step) => blockerForStep(phase, step, execution, evidenceRefsForStep(step)));
  const blockers = executionBlockedInPhase(execution, phase) && stepBlockers.length === 0
    ? [blockerForExecution(phase, execution)]
    : stepBlockers;
  const status = phaseStatus(phase, execution, steps);
  const startedAt = steps.map((step) => step.started_at).find(Boolean) ?? previousPhase?.started_at;
  const completedAt =
    status === "passed"
      ? latestTimestamp(steps.map((step) => step.completed_at).filter(Boolean) as string[]) ?? previousPhase?.completed_at
      : undefined;

  return {
    phase,
    status,
    summary: phaseSummary(phase, status, steps.length, blockers),
    blockers,
    evidence_refs: evidenceRefs,
    started_at: startedAt,
    completed_at: completedAt,
    updated_at: execution.updated_at,
  };
}

function phaseStatus(
  phase: DeliveryPhase,
  execution: ExecutionWorkflowRecord,
  steps: ExecutionWorkflowRecord["steps"],
): DeliveryPhaseStatus {
  if (executionBlockedInPhase(execution, phase)) {
    return "blocked";
  }
  if (steps.length === 0) {
    return phase === "requirement" && execution.current_stage === "created" ? "in_progress" : "pending";
  }
  if (steps.some((step) => step.status === "blocked")) {
    return "blocked";
  }
  if (execution.status === "waiting_human" && deliveryPhaseForCurrentStage(execution.current_stage) === phase) {
    return "waiting_human";
  }
  if (steps.some((step) => step.status === "running")) {
    return "in_progress";
  }
  if (steps.every((step) => step.status === "completed" || step.status === "skipped")) {
    return "passed";
  }
  if (deliveryPhaseForCurrentStage(execution.current_stage) === phase && execution.status === "in_progress") {
    return "in_progress";
  }
  if (steps.some((step) => step.status === "completed")) {
    return "in_progress";
  }
  return "pending";
}

function currentDeliveryPhase(
  execution: ExecutionWorkflowRecord,
  phases: DeliveryWorkflowPhase[],
): DeliveryPhase {
  const blocked = phases.find((phase) => phase.status === "blocked");
  if (blocked) {
    return blocked.phase;
  }
  const waiting = phases.find((phase) => phase.status === "waiting_human");
  if (waiting) {
    return waiting.phase;
  }
  const current = deliveryPhaseForCurrentStage(execution.current_stage);
  if (current) {
    return current;
  }
  return phases.find((phase) => phase.status !== "passed")?.phase ?? "handoff";
}

function deliveryPhaseForCurrentStage(stage: string): DeliveryPhase | undefined {
  const normalizedStage = stage.split(":")[0] ?? stage;
  const roles: AgentRole[] = [
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
  ];
  return roles.includes(normalizedStage as AgentRole) ? deliveryPhaseForRole(normalizedStage as AgentRole) : undefined;
}

function blockerForStep(
  phase: DeliveryPhase,
  step: ExecutionWorkflowRecord["steps"][number],
  execution: ExecutionWorkflowRecord,
  evidenceRefs: EvidenceRef[],
): DeliveryBlocker {
  const ref = step.agent_run_id || step.prompt_trace_id || step.role;
  return {
    id: `${phase}:${step.role}:${ref}`,
    phase,
    source_role: step.role,
    reason: execution.blocked_reason || step.summary || `${step.role} blocked.`,
    status: "open",
    evidence_refs: evidenceRefs,
    created_at: step.completed_at ?? execution.updated_at,
  };
}

function blockerForExecution(
  phase: DeliveryPhase,
  execution: ExecutionWorkflowRecord,
): DeliveryBlocker {
  return {
    id: `${phase}:${execution.current_stage}:execution-blocked`,
    phase,
    source_role: sourceRoleForStage(execution.current_stage),
    reason: execution.blocked_reason || `${execution.current_stage} blocked.`,
    status: "open",
    evidence_refs: [],
    created_at: execution.updated_at,
  };
}

function executionBlockedInPhase(execution: ExecutionWorkflowRecord, phase: DeliveryPhase): boolean {
  return execution.status === "blocked" && deliveryPhaseForCurrentStage(execution.current_stage) === phase;
}

function sourceRoleForStage(stage: string): AgentRole | undefined {
  const normalizedStage = stage.split(":")[0] ?? stage;
  const roles: AgentRole[] = [
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
  ];
  return roles.includes(normalizedStage as AgentRole) ? normalizedStage as AgentRole : undefined;
}

function evidenceRefsForStep(step: ExecutionWorkflowRecord["steps"][number]): EvidenceRef[] {
  const refs: EvidenceRef[] = [];
  if (step.prompt_trace_id) {
    refs.push({
      kind: "prompt_trace",
      ref: step.prompt_trace_id,
      path: "",
      role: step.role,
      summary: `${step.role} prompt trace`,
    });
  }
  if (step.agent_run_id) {
    refs.push({
      kind: "agent_run",
      ref: step.agent_run_id,
      path: "",
      role: step.role,
      summary: `${step.role} agent run`,
    });
  }
  if (step.artifact_path) {
    refs.push({
      kind: "artifact",
      ref: step.artifact_path,
      path: step.artifact_path,
      role: step.role,
      summary: `${step.role} artifact`,
    });
  }
  for (const file of step.files_changed) {
    refs.push({ kind: "file", ref: file, path: file, role: step.role, summary: `${step.role} changed file` });
  }
  for (const command of step.commands_run) {
    refs.push({ kind: "command", ref: command, path: "", role: step.role, summary: `${step.role} command` });
  }
  return refs;
}

function phaseSummary(
  phase: DeliveryPhase,
  status: DeliveryPhaseStatus,
  stepCount: number,
  blockers: DeliveryBlocker[],
): string {
  if (blockers.length > 0) {
    return blockers[0]?.reason ?? `${phase} blocked.`;
  }
  if (status === "passed") {
    return `${phase} passed with ${stepCount} execution step(s).`;
  }
  if (status === "waiting_human") {
    return `${phase} is waiting for human decision.`;
  }
  if (status === "in_progress") {
    return `${phase} is in progress.`;
  }
  return `${phase} is pending.`;
}

function deliverySummary(phases: DeliveryWorkflowPhase[], blockers: DeliveryBlocker[]): string {
  if (blockers.length > 0) {
    return blockers[0]?.reason ?? "Delivery blocked.";
  }
  const waiting = phases.find((phase) => phase.status === "waiting_human");
  if (waiting) {
    return waiting.summary;
  }
  if (phases.every((phase) => phase.status === "passed")) {
    return "Delivery workflow completed.";
  }
  return phases.find((phase) => phase.status === "in_progress")?.summary ?? "Delivery workflow in progress.";
}

function uniqueEvidence(refs: EvidenceRef[]): EvidenceRef[] {
  const seen = new Set<string>();
  const unique: EvidenceRef[] = [];
  for (const ref of refs) {
    const key = `${ref.kind}:${ref.ref}:${ref.role ?? ""}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    unique.push(ref);
  }
  return unique;
}
