import path from "node:path";
import { buildAgentRunner, type AgentRunner, type AgentTaskResult } from "./runner.js";
import {
  type AgentRole,
  type RunResult,
  type RuntimeProfile,
  type WorktreeRecord,
  type WorkflowRecord,
  nowIso,
} from "./schema.js";
import { renderSkillInjection, resolveSkillRouting, skillRoutingMetadata } from "./skill-routing.js";
import { RuntimeStore } from "./store.js";

export type RunWorkflowOptions = {
  repoRoot: string;
  projectRoot?: string;
  stateRoot?: string;
  request?: string;
  sessionId?: string;
  profile?: RuntimeProfile;
  humanGates?: boolean;
  worktree?: WorktreeRecord;
  runner?: AgentRunner;
};

export type WorkflowStepPlan = { role: AgentRole; writeAllowed: boolean; humanGateAfter?: boolean };

const QUICK_STEPS: WorkflowStepPlan[] = [
  { role: "planner", writeAllowed: false },
  { role: "repo_scout", writeAllowed: false },
  { role: "writer", writeAllowed: true },
  { role: "verifier", writeAllowed: false },
  { role: "summarizer", writeAllowed: false },
];

const INVESTIGATE_STEPS: WorkflowStepPlan[] = [
  { role: "planner", writeAllowed: false },
  { role: "repo_scout", writeAllowed: false },
  { role: "test_scout", writeAllowed: false },
  { role: "summarizer", writeAllowed: false },
];

const FULL_STEPS: WorkflowStepPlan[] = [
  { role: "route", writeAllowed: false },
  { role: "product_definition", writeAllowed: false, humanGateAfter: true },
  { role: "project_runtime", writeAllowed: false },
  { role: "technical_design", writeAllowed: false, humanGateAfter: true },
  { role: "implementation", writeAllowed: true },
  { role: "verification", writeAllowed: false },
  { role: "governance_review", writeAllowed: false },
  { role: "acceptance", writeAllowed: false },
  { role: "session_handoff", writeAllowed: false, humanGateAfter: true },
];

export async function runWorkflow(options: RunWorkflowOptions): Promise<RunResult> {
  const repoRoot = path.resolve(options.repoRoot);
  const stateRoot = path.resolve(options.stateRoot ?? path.join(repoRoot, ".agt"));
  const store = new RuntimeStore(stateRoot);
  const session = options.sessionId
    ? await store.loadSession(options.sessionId)
    : await store.createSession({
        request: requiredRequest(options.request),
        profile: options.profile ?? "quick",
        repoRoot,
        projectRoot: options.projectRoot,
        worktree: options.worktree,
      });
  const profile = session.profile;
  const runner = options.runner ?? buildAgentRunner(store);
  const steps = stepsForProfile(profile);
  let workflow = await ensureWorkflowSteps(store, session.session_id, steps);

  if (workflow.status === "done") {
    return runResult({ sessionId: session.session_id, workflow, profile, stateRoot, repoRoot, store });
  }
  if (workflow.status === "waiting_human") {
    return runResult({ sessionId: session.session_id, workflow, profile, stateRoot, repoRoot, store });
  }

  const outputs: string[] = [];
  let filesChanged: string[] = workflow.files_changed;
  let commandsRun: string[] = workflow.commands_run;
  for (const step of remainingSteps(workflow, steps)) {
    await store.updateWorkflow(session.session_id, (workflow) => ({
      ...workflow,
      status: "in_progress",
      current_stage: step.role,
      steps: workflow.steps.map((item) =>
        item.role === step.role
          ? { ...item, status: "running", started_at: nowIso() }
          : item,
      ),
      updated_at: nowIso(),
    }));
    const routing = await resolveSkillRouting({
      repoRoot,
      projectRoot: session.project_root || repoRoot,
      role: step.role,
      profile,
    });
    const prompt = promptForStep(
      profile,
      step.role,
      session.request,
      completedSummaries(workflow, outputs),
      renderSkillInjection(routing),
    );
    const trace = await store.recordPromptTrace({
      sessionId: session.session_id,
      role: step.role,
      prompt,
      runner: runner.name,
      source: "runtime.runWorkflow",
      metadata: {
        profile,
        write_allowed: step.writeAllowed,
        skill_routing: skillRoutingMetadata(routing),
      },
    });
    if (routing.missing_required_skills.length > 0) {
      const blockedRun = await store.createAgentRun({
        sessionId: session.session_id,
        role: step.role,
        runner: runner.name,
        input: prompt,
        metadata: {
          profile,
          write_allowed: step.writeAllowed,
          executor_status: "blocked",
          result_parse_status: "not_produced",
          prompt_trace_id: trace.prompt_id,
          routing_config_gap: true,
        },
      });
      const completed = await store.completeAgentRun(blockedRun, {
        status: "blocked",
        output: blockedOutput(
          step.role,
          `Routing config gap: missing required skills ${routing.missing_required_skills.join(", ")}.`,
        ),
        metadata: {
          ...blockedRun.metadata,
          routing_config_gap: true,
          missing_required_skills: routing.missing_required_skills,
        },
      });
      const artifact = await store.writeArtifact({
        sessionId: session.session_id,
        role: step.role,
        name: artifactNameForRole(step.role),
        content: completed.output,
        metadata: {
          agent_run_id: completed.agent_run_id,
          prompt_trace_id: trace.prompt_id,
          executor_status: "blocked",
          result_parse_status: "not_produced",
          routing_config_gap: true,
        },
      });
      workflow = await store.updateWorkflow(session.session_id, (workflow) => ({
        ...workflow,
        current_stage: step.role,
        steps: workflow.steps.map((item) =>
          item.role === step.role
            ? {
                ...item,
                status: "blocked",
                agent_run_id: completed.agent_run_id,
                prompt_trace_id: trace.prompt_id,
                artifact_path: artifact.path,
                files_changed: [],
                commands_run: [],
                completed_at: nowIso(),
                summary: firstLine(completed.output),
              }
            : item,
        ),
        status: "blocked",
        blocked_reason: completed.output,
        files_changed: filesChanged,
        commands_run: commandsRun,
        summary: firstLine(completed.output),
        updated_at: nowIso(),
      }));
      await store.appendEvent({
        at: nowIso(),
        session_id: session.session_id,
        kind: "workflow_step_blocked",
        role: step.role,
        status: "blocked",
        message: `${step.role} blocked because routing requirements were not satisfied.`,
        details: {
          agent_run_id: completed.agent_run_id,
          prompt_trace_id: trace.prompt_id,
          missing_required_skills: routing.missing_required_skills,
          routing_config_gap: true,
        },
      });
      break;
    }
    await store.updateWorkflow(session.session_id, (workflow) => ({
      ...workflow,
      steps: workflow.steps.map((item) =>
        item.role === step.role ? { ...item, prompt_trace_id: trace.prompt_id } : item,
      ),
      updated_at: nowIso(),
    }));
    const result = await runStepSafely({
      store,
      runner,
      sessionId: session.session_id,
      role: step.role,
      profile,
      repoRoot,
      prompt,
      writeAllowed: step.writeAllowed,
      traceId: trace.prompt_id,
    });
    const artifact = await store.writeArtifact({
      sessionId: session.session_id,
      role: step.role,
      name: artifactNameForRole(step.role),
      content: result.output,
      metadata: {
        agent_run_id: result.agentRun.agent_run_id,
        prompt_trace_id: trace.prompt_id,
        executor_status: result.agentRun.metadata.executor_status ?? result.agentRun.status,
        result_parse_status: result.agentRun.metadata.result_parse_status ?? "",
      },
    });
    outputs.push(result.output);
    filesChanged = unique([...filesChanged, ...result.filesChanged]);
    commandsRun = unique([...commandsRun, ...result.commandsRun]);
    workflow = await store.updateWorkflow(session.session_id, (workflow) => ({
      ...workflow,
      current_stage: step.role,
      steps: workflow.steps.map((item) =>
        item.role === step.role
          ? {
              ...item,
              status: result.agentRun.status === "completed" ? "completed" : "blocked",
              agent_run_id: result.agentRun.agent_run_id,
              prompt_trace_id: trace.prompt_id,
              artifact_path: artifact.path,
              files_changed: result.filesChanged,
              commands_run: result.commandsRun,
              completed_at: nowIso(),
              summary: firstLine(result.output),
            }
          : item,
      ),
      status: result.agentRun.status === "completed" ? workflow.status : "blocked",
      blocked_reason: result.agentRun.status === "completed" ? workflow.blocked_reason : result.output,
      files_changed: filesChanged,
      commands_run: commandsRun,
      summary: firstLine(result.output),
      updated_at: nowIso(),
    }));
    if (result.agentRun.status !== "completed") {
      await store.appendEvent({
        at: nowIso(),
        session_id: session.session_id,
        kind: "workflow_step_blocked",
        role: step.role,
        status: result.agentRun.status,
        message: `${step.role} blocked before workflow could continue.`,
        details: {
          agent_run_id: result.agentRun.agent_run_id,
          prompt_trace_id: trace.prompt_id,
          executor_status: result.agentRun.metadata.executor_status ?? result.agentRun.status,
          result_parse_status: result.agentRun.metadata.result_parse_status ?? "",
        },
      });
      break;
    }
    if (options.humanGates && step.humanGateAfter) {
      workflow = await store.updateWorkflow(session.session_id, (workflow) => ({
        ...workflow,
        status: "waiting_human",
        current_stage: step.role,
        summary: `Waiting for human decision after ${step.role}.`,
        updated_at: nowIso(),
      }));
      await store.appendEvent({
        at: nowIso(),
        session_id: session.session_id,
        kind: "human_gate_waiting",
        role: step.role,
        status: "waiting_human",
        message: `Waiting for human decision after ${step.role}.`,
        details: {},
      });
      break;
    }
  }

  workflow = await store.updateWorkflow(session.session_id, (current) => {
    if (current.status === "waiting_human") {
      return current;
    }
    const blocked = current.steps.some((step) => step.status === "blocked");
    const done = current.steps.every((step) => step.status === "completed" || step.status === "skipped");
    return {
      ...current,
      status: blocked ? "blocked" : done ? "done" : "in_progress",
      current_stage: blocked || !done ? current.current_stage : "done",
      summary: outputs.at(-1) ?? current.summary,
      files_changed: filesChanged,
      commands_run: commandsRun,
      updated_at: nowIso(),
    };
  });

  return runResult({ sessionId: session.session_id, workflow, profile, stateRoot, repoRoot, store });
}

export async function recordHumanDecision(options: {
  stateRoot: string;
  sessionId: string;
  decision: "go" | "no-go" | "rework";
  targetRole?: AgentRole;
}): Promise<RunResult> {
  const store = new RuntimeStore(options.stateRoot);
  const session = await store.loadSession(options.sessionId);
  const workflow = await store.loadWorkflow(options.sessionId);
  const now = nowIso();
  const updated = await store.updateWorkflow(options.sessionId, (current) => {
    if (options.decision === "no-go") {
      return {
        ...current,
        status: "blocked",
        blocked_reason: "Human decision: no-go.",
        updated_at: now,
      };
    }
    if (options.decision === "rework") {
      const target = options.targetRole ?? current.current_stage;
      return {
        ...current,
        status: "in_progress",
        current_stage: target,
        blocked_reason: "",
        steps: current.steps.map((step) =>
          shouldResetForRework(current, step.role, target)
            ? {
                ...step,
                status: "pending",
                agent_run_id: undefined,
                prompt_trace_id: "",
                artifact_path: "",
                files_changed: [],
                commands_run: [],
                completed_at: undefined,
                summary: "",
              }
            : step,
        ),
        summary: `Rework requested from ${target}.`,
        updated_at: now,
      };
    }
    const next = nextPendingStep(current);
    return {
      ...current,
      status: next ? "in_progress" : "done",
      current_stage: next?.role ?? "done",
      blocked_reason: "",
      updated_at: now,
    };
  });
  await store.appendEvent({
    at: now,
    session_id: options.sessionId,
    kind: "human_decision_recorded",
    role: workflow.current_stage as AgentRole,
    status: options.decision,
    message: `Human decision: ${options.decision}.`,
    details: { target_role: options.targetRole ?? "" },
  });
  return runResult({
    sessionId: session.session_id,
    workflow: updated,
    profile: session.profile,
    stateRoot: store.stateRoot,
    repoRoot: session.repo_root,
    store,
  });
}

export function stepsForProfile(profile: RuntimeProfile): WorkflowStepPlan[] {
  if (profile === "quick") {
    return QUICK_STEPS;
  }
  if (profile === "investigate") {
    return INVESTIGATE_STEPS;
  }
  return FULL_STEPS;
}

async function ensureWorkflowSteps(
  store: RuntimeStore,
  sessionId: string,
  steps: WorkflowStepPlan[],
): Promise<WorkflowRecord> {
  const workflow = await store.loadWorkflow(sessionId);
  if (workflow.steps.length > 0) {
    return workflow;
  }
  return store.updateWorkflow(sessionId, (workflow) => ({
    ...workflow,
    current_stage: steps[0]?.role ?? "done",
    steps: steps.map((step) => ({
      role: step.role,
      status: "pending",
      prompt_trace_id: "",
      artifact_path: "",
      files_changed: [],
      commands_run: [],
      summary: "",
    })),
    updated_at: nowIso(),
  }));
}

function remainingSteps(workflow: WorkflowRecord, steps: WorkflowStepPlan[]): WorkflowStepPlan[] {
  const byRole = new Map(workflow.steps.map((step) => [step.role, step.status]));
  return steps.filter((step) => {
    const status = byRole.get(step.role);
    return status !== "completed" && status !== "skipped";
  });
}

function completedSummaries(workflow: WorkflowRecord, outputs: string[]): string[] {
  return [
    ...workflow.steps
      .filter((step) => step.status === "completed" && step.summary)
      .map((step) => `${step.role}: ${step.summary}`),
    ...outputs,
  ];
}

async function runStepSafely(args: {
  store: RuntimeStore;
  runner: AgentRunner;
  sessionId: string;
  role: AgentRole;
  profile: RuntimeProfile;
  repoRoot: string;
  prompt: string;
  writeAllowed: boolean;
  traceId: string;
}): Promise<AgentTaskResult> {
  try {
    const result = await args.runner.runTask({
      sessionId: args.sessionId,
      role: args.role,
      profile: args.profile,
      repoRoot: args.repoRoot,
      prompt: args.prompt,
      writeAllowed: args.writeAllowed,
    });
    if (result.agentRun.status !== "completed") {
      return normalizeBlockedResult(args, result);
    }
    return result;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const agentRun = await args.store.createAgentRun({
      sessionId: args.sessionId,
      role: args.role,
      runner: args.runner.name,
      input: args.prompt,
      metadata: {
        profile: args.profile,
        write_allowed: args.writeAllowed,
        executor_status: isTimeoutMessage(message) ? "timeout" : "failed",
        result_parse_status: "not_produced",
        prompt_trace_id: args.traceId,
      },
    });
    const completed = await args.store.completeAgentRun(agentRun, {
      status: "blocked",
      output: blockedOutput(args.role, message),
      error: message,
      metadata: {
        ...agentRun.metadata,
        blocked_kind: isTimeoutMessage(message) ? "executor_timeout" : "executor_error",
      },
    });
    return {
      agentRun: completed,
      output: completed.output,
      filesChanged: [],
      commandsRun: [],
    };
  }
}

function normalizeBlockedResult(
  args: {
    store: RuntimeStore;
    role: AgentRole;
    profile: RuntimeProfile;
    writeAllowed: boolean;
    traceId: string;
  },
  result: AgentTaskResult,
): Promise<AgentTaskResult> {
  const metadata = result.agentRun.metadata;
  const executorStatus = String(metadata.executor_status ?? result.agentRun.status);
  const resultParseStatus = String(metadata.result_parse_status ?? (result.output ? "recovered_after_executor_failure" : "not_produced"));
  return args.store.completeAgentRun(result.agentRun, {
    status: "blocked",
    output: blockedOutput(args.role, result.output || result.agentRun.error || "Agent run did not complete."),
    metadata: {
      ...metadata,
      profile: args.profile,
      write_allowed: args.writeAllowed,
      prompt_trace_id: args.traceId,
      executor_status: executorStatus,
      result_parse_status: resultParseStatus,
    },
  }).then((normalizedRun) => ({
    ...result,
    agentRun: normalizedRun,
    output: normalizedRun.output,
  }));
}

function promptForStep(
  profile: RuntimeProfile,
  role: AgentRole,
  request: string,
  previousOutputs: string[],
  skillInjection: string,
): string {
  return [
    `Profile: ${profile}`,
    `Role: ${role}`,
    `User request: ${request}`,
    skillInjection,
    previousOutputs.length ? `Previous agent summaries:\n${previousOutputs.join("\n\n---\n\n")}` : "",
    "Produce a concise, evidence-backed result for this role.",
  ]
    .filter(Boolean)
    .join("\n\n");
}

function artifactNameForRole(role: AgentRole): string {
  const names: Partial<Record<AgentRole, string>> = {
    planner: "planner-report.md",
    repo_scout: "repo-scout-report.md",
    test_scout: "test-scout-report.md",
    writer: "writer-report.md",
    verifier: "verifier-report.md",
    summarizer: "summary.md",
    route: "route-packet.md",
    product_definition: "product-definition-delta.md",
    project_runtime: "project-runtime-delta.md",
    technical_design: "technical-design.md",
    implementation: "implementation.md",
    verification: "verification-report.md",
    governance_review: "governance-review.md",
    acceptance: "acceptance-report.md",
    session_handoff: "session-handoff.md",
  };
  return names[role] ?? `${role}.md`;
}

function nextPendingStep(workflow: WorkflowRecord) {
  return workflow.steps.find((step) => step.status !== "completed" && step.status !== "skipped");
}

function shouldResetForRework(workflow: WorkflowRecord, role: AgentRole, target: string): boolean {
  const targetIndex = workflow.steps.findIndex((step) => step.role === target);
  const roleIndex = workflow.steps.findIndex((step) => step.role === role);
  return targetIndex >= 0 && roleIndex >= targetIndex;
}

function runResult(args: {
  sessionId: string;
  workflow: WorkflowRecord;
  profile: RuntimeProfile;
  stateRoot: string;
  repoRoot: string;
  store: RuntimeStore;
}): RunResult {
  return {
    session_id: args.sessionId,
    status: args.workflow.status,
    profile: args.profile,
    state_root: args.stateRoot,
    session_dir: args.store.sessionDir(args.sessionId),
    repo_root: args.repoRoot,
    current_stage: args.workflow.current_stage,
    summary: args.workflow.summary,
    blocked_reason: args.workflow.blocked_reason,
  };
}

function requiredRequest(value: string | undefined): string {
  const request = value?.trim();
  if (!request) {
    throw new Error("runWorkflow requires request when sessionId is not provided.");
  }
  return request;
}

function firstLine(value: string): string {
  return value.split("\n").find((line) => line.trim())?.trim().slice(0, 240) ?? "";
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function blockedOutput(role: AgentRole, reason: string): string {
  const guidance =
    role === "verification" || role === "verifier"
      ? "Verification did not complete. Treat this as needs_verification and rerun or request rework with the recorded prompt trace."
      : "The workflow step did not complete. Rerun this step or request rework with the recorded prompt trace.";
  return [`${role} blocked.`, `Reason: ${reason}`, guidance].join("\n");
}

function isTimeoutMessage(message: string): boolean {
  return /timeout|timed out|ETIMEDOUT|AbortError/i.test(message);
}
