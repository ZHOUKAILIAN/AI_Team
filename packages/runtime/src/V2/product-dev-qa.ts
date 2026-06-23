import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import {
  createDefaultV2HookManager,
  type V2ExecutorHookContext,
  type V2HookManager,
  type V2StageHookContext,
} from "./hooks.js";
import { buildAgentRunner, type AgentRunner, type AgentTaskResult } from "./runner.js";
import {
  type AgentRole,
  type AgentRunRecord,
  type DeliveryPhase,
  type DeliveryPhaseStatus,
  type DeliveryWorkflowRecord,
  type ExecutionWorkflowRecord,
  type ProductDevQaStageRole,
  type ProductDevQaStageStep,
  type ProductDevQaWorkflowRunRecord,
  type RequestSourceRecord,
  type RunResult,
  type TokenUsage,
  type WorkflowStatus,
  type WorktreeRecord,
  nowIso,
} from "./schema.js";
import {
  renderSkillInjection,
  resolveSkillRouting,
  skillRoutingAuditMetadata,
  skillRoutingMetadata,
} from "./skill-routing.js";
import { RuntimeStore, writeJson } from "./store.js";
import { emptyTokenUsage } from "./usage.js";

export const PRODUCT_DEV_QA_WORKFLOW_ID = "product-dev-qa" as const;

type StageKey = "intake_summary" | "product" | "dev.technical_plan" | "dev.implementation" | "qa";
type StageVerdict = "passed" | "failed" | "blocked";
type HumanGate = "product_check" | "dev_plan_check";

type ProductDevQaStagePlan = {
  key: StageKey;
  role: AgentRole;
  currentRole: ProductDevQaStageRole;
  currentStep: ProductDevQaStageStep | null;
  currentStage: string;
  directoryParts: string[];
  canWriteCode: boolean;
  goal: string;
  includeRequest: boolean;
  requiredInputs: string[];
  requiredOutputs: string[];
  requiredEvidence: string[];
  executor: {
    maxTurns: number;
  };
};

type StageExecutionOutcome = {
  verdict: StageVerdict;
  output: string;
  agentRun: AgentRunRecord;
  filesChanged: string[];
  commandsRun: string[];
  tokenUsage: TokenUsage;
  promptTraceId: string;
  artifactPaths: string[];
  artifactNames: string[];
  summary: string;
  reason: string;
  repoRoot: string;
  projectRoot: string;
  promptPath: string;
  contextPacketPath: string;
  skillRouting: Record<string, unknown>;
  stageStartedAt: string;
  stageStartedAtIso: string;
  executorStartedAt: string;
  executorCompletedAt: string;
  executorDurationMs: number;
};

export type RunProductDevQaWorkflowOptions = {
  repoRoot: string;
  projectRoot?: string;
  stateRoot?: string;
  request?: string;
  sessionId?: string;
  worktree?: WorktreeRecord;
  requestSources?: RequestSourceRecord[];
  runner?: AgentRunner;
  maxQaFailureLoops?: number;
};

export type RecordProductDevQaDecisionOptions = {
  stateRoot: string;
  sessionId: string;
  decision: "go" | "no-go";
  runner?: AgentRunner;
  maxQaFailureLoops?: number;
};

const STAGES: Record<StageKey, ProductDevQaStagePlan> = {
  intake_summary: {
    key: "intake_summary",
    role: "intake_summary",
    currentRole: "intake_summary",
    currentStep: null,
    currentStage: "intake_summary",
    directoryParts: ["intake_summary"],
    canWriteCode: false,
    goal: "Generate the first request summary for this delivery workflow.",
    includeRequest: true,
    requiredInputs: [],
    requiredOutputs: ["request-summary.md"],
    requiredEvidence: ["request_summary_generated"],
    executor: { maxTurns: 3 },
  },
  product: {
    key: "product",
    role: "product",
    currentRole: "product",
    currentStep: null,
    currentStage: "product",
    directoryParts: ["product"],
    canWriteCode: false,
    goal: "Define the product contract and handoff for development.",
    includeRequest: true,
    requiredInputs: ["request-summary.md"],
    requiredOutputs: ["product-contract.md", "product-handoff.md"],
    requiredEvidence: ["scope_defined", "acceptance_criteria_defined", "qa_focus_defined"],
    executor: { maxTurns: 5 },
  },
  "dev.technical_plan": {
    key: "dev.technical_plan",
    role: "dev",
    currentRole: "dev",
    currentStep: "technical_plan",
    currentStage: "dev:technical_plan",
    directoryParts: ["dev", "technical-plan"],
    canWriteCode: false,
    goal: "Produce the technical plan before implementation.",
    includeRequest: false,
    requiredInputs: ["request-summary.md", "product-contract.md", "product-handoff.md"],
    requiredOutputs: ["technical-plan.md"],
    requiredEvidence: ["implementation_plan_defined", "test_strategy_defined", "implementation_ambiguities_declared"],
    executor: { maxTurns: 5 },
  },
  "dev.implementation": {
    key: "dev.implementation",
    role: "dev",
    currentRole: "dev",
    currentStep: "implementation",
    currentStage: "dev:implementation",
    directoryParts: ["dev", "implementation"],
    canWriteCode: true,
    goal: "Implement the approved technical plan and record self-test evidence.",
    includeRequest: false,
    requiredInputs: ["request-summary.md", "product-contract.md", "product-handoff.md", "technical-plan.md"],
    requiredOutputs: [
      "implementation-report.md",
      "self-test-report.md",
      "implementation-ambiguities.json",
      "qa-handoff.md",
    ],
    requiredEvidence: ["code_changed", "self_tests_recorded", "implementation_ambiguities_declared"],
    executor: { maxTurns: 8 },
  },
  qa: {
    key: "qa",
    role: "qa",
    currentRole: "qa",
    currentStep: null,
    currentStage: "qa",
    directoryParts: ["qa"],
    canWriteCode: false,
    goal: "Independently verify whether local delivery is complete.",
    includeRequest: false,
    requiredInputs: [
      "request-summary.md",
      "product-contract.md",
      "product-handoff.md",
      "technical-plan.md",
      "implementation-report.md",
      "self-test-report.md",
      "implementation-ambiguities.json",
      "qa-handoff.md",
    ],
    requiredOutputs: ["qa-report.md", "verification-evidence.json"],
    requiredEvidence: ["independent_verification", "unverified_items_declared"],
    executor: { maxTurns: 6 },
  },
};

const EXECUTION_STAGE_ORDER: StageKey[] = [
  "intake_summary",
  "product",
  "dev.technical_plan",
  "dev.implementation",
  "qa",
];

export async function runProductDevQaWorkflow(options: RunProductDevQaWorkflowOptions): Promise<RunResult> {
  const repoRoot = path.resolve(options.repoRoot);
  const stateRoot = path.resolve(options.stateRoot ?? path.join(repoRoot, ".agt2"));
  const store = new RuntimeStore(stateRoot);
  const session = options.sessionId
    ? await store.loadSession(options.sessionId)
    : await store.createSession({
        request: requiredRequest(options.request),
        repoRoot,
        projectRoot: options.projectRoot,
        workflowId: PRODUCT_DEV_QA_WORKFLOW_ID,
        worktree: options.worktree,
        requestSources: options.requestSources,
      });
  const workflow = await ensureProductDevQaWorkflow(store, session.session_id);
  const runner = options.runner ?? buildAgentRunner(store);
  const hooks = createDefaultV2HookManager(store);
  let current = workflow;

  while (true) {
    current = await store.loadProductDevQaWorkflow(session.session_id);
    if (current.status === "waiting_human" || current.status === "blocked" || current.status === "done" || current.status === "cancelled") {
      return productDevQaRunResult(store, session.session_id);
    }

    const stage = nextRunnableStage(current);
    if (!stage) {
      current = await transitionToDone(store, current);
      return productDevQaRunResult(store, session.session_id);
    }

    const running = await markStageRunning(store, current, stage);
    try {
      const outcome = await executeStage({
        store,
        sessionId: session.session_id,
        repoRoot: session.repo_root,
        projectRoot: session.project_root || session.repo_root,
        request: session.request,
        workflow: running.workflow,
        stage,
        attemptNumber: running.attemptNumber,
        runner,
        hooks,
      });
      current = await transitionAfterStage({
        store,
        workflow: running.workflow,
        stage,
        outcome,
        maxQaFailureLoops: options.maxQaFailureLoops ?? 3,
        hooks,
      });
    } catch (error) {
      current = await blockStageRuntimeError({
        store,
        workflow: running.workflow,
        stage,
        attemptNumber: running.attemptNumber,
        runner,
        error,
      });
    }
  }
}

export async function recordProductDevQaHumanDecision(
  options: RecordProductDevQaDecisionOptions,
): Promise<RunResult> {
  const store = new RuntimeStore(options.stateRoot);
  const session = await store.loadSession(options.sessionId);
  const workflow = await store.loadProductDevQaWorkflow(options.sessionId);
  if (workflow.workflow_id !== PRODUCT_DEV_QA_WORKFLOW_ID) {
    throw new Error(`Session is not a ${PRODUCT_DEV_QA_WORKFLOW_ID} workflow: ${options.sessionId}`);
  }
  if (workflow.status !== "waiting_human" || !workflow.waiting_on) {
    throw new Error(`Session is not waiting for a Product/Dev plan decision: ${options.sessionId}`);
  }

  const now = nowIso();
  if (options.decision === "no-go") {
    const blocked: ProductDevQaWorkflowRunRecord = {
      ...workflow,
      status: "blocked",
      waiting_on: null,
      blocked_reason: `Human decision rejected ${workflow.waiting_on}.`,
      summary: `Blocked by human decision at ${workflow.waiting_on}.`,
      updated_at: now,
    };
    await store.appendEvent({
      at: now,
      session_id: options.sessionId,
      kind: "human_decision_recorded",
      role: workflow.current_role ?? undefined,
      status: options.decision,
      message: `Human decision: ${options.decision}.`,
      details: { waiting_on: workflow.waiting_on, workflow_id: PRODUCT_DEV_QA_WORKFLOW_ID },
    });
    await setExecutionStatusForWorkflow(store, blocked, "blocked");
    await writeAndSyncWorkflow(store, blocked);
    return productDevQaRunResult(store, options.sessionId);
  }

  const nextStage = nextStageAfterGate(workflow.waiting_on);
  const approved = setWorkflowStage({
    ...workflow,
    status: "running",
    waiting_on: null,
    blocked_reason: "",
    summary: `Human approved ${workflow.waiting_on}; continuing to ${nextStage}.`,
    updated_at: now,
  }, STAGES[nextStage]);
  await store.appendEvent({
    at: now,
    session_id: options.sessionId,
    kind: "human_decision_recorded",
    role: workflow.current_role ?? undefined,
    status: options.decision,
    message: `Human decision: ${options.decision}.`,
    details: { waiting_on: workflow.waiting_on, next_stage: nextStage, workflow_id: PRODUCT_DEV_QA_WORKFLOW_ID },
  });
  await writeAndSyncWorkflow(store, approved);
  return runProductDevQaWorkflow({
    repoRoot: session.repo_root,
    projectRoot: session.project_root,
    stateRoot: store.stateRoot,
    sessionId: options.sessionId,
    runner: options.runner,
    maxQaFailureLoops: options.maxQaFailureLoops,
  });
}

export async function isProductDevQaSession(store: RuntimeStore, sessionId: string): Promise<boolean> {
  const session = await store.loadSession(sessionId);
  return session.workflow_id === PRODUCT_DEV_QA_WORKFLOW_ID;
}

async function ensureProductDevQaWorkflow(
  store: RuntimeStore,
  sessionId: string,
): Promise<ProductDevQaWorkflowRunRecord> {
  const existing = await store.loadProductDevQaWorkflow(sessionId).catch(() => undefined);
  if (existing) {
    return existing;
  }
  const session = await store.loadSession(sessionId);
  const now = nowIso();
  const workflow: ProductDevQaWorkflowRunRecord = {
    schema_version: 1,
    workflow_id: PRODUCT_DEV_QA_WORKFLOW_ID,
    workflow_run_id: session.session_id,
    session_id: session.session_id,
    request: session.request,
    status: "created",
    current_role: null,
    current_step: null,
    current_stage: "created",
    waiting_on: null,
    stage_attempt_counts: {},
    summary: "Product-Dev-QA workflow created.",
    blocked_reason: "",
    last_stage_key: "",
    last_stage_attempt: 0,
    last_stage_verdict: null,
    last_stage_summary: "",
    last_stage_artifacts: [],
    started_at: now,
    updated_at: now,
    completed_at: null,
  };
  await ensureProductDevQaExecutionWorkflow(store, sessionId, now);
  await writeAndSyncWorkflow(store, workflow);
  return workflow;
}

async function ensureProductDevQaExecutionWorkflow(
  store: RuntimeStore,
  sessionId: string,
  updatedAt: string,
): Promise<ExecutionWorkflowRecord> {
  const existing = await store.loadExecutionWorkflow(sessionId);
  if (existing.steps.length > 0) {
    return existing;
  }
  return store.updateExecutionWorkflow(sessionId, (workflow) => ({
    ...workflow,
    status: "in_progress",
    current_stage: "created",
    steps: EXECUTION_STAGE_ORDER.map((key) => ({
      role: STAGES[key].role,
      status: "pending",
      prompt_trace_id: "",
      artifact_path: "",
      files_changed: [],
      commands_run: [],
      summary: "",
    })),
    updated_at: updatedAt,
  }));
}

function nextRunnableStage(workflow: ProductDevQaWorkflowRunRecord): ProductDevQaStagePlan | undefined {
  if (workflow.status === "created" || workflow.current_stage === "created") {
    return STAGES.intake_summary;
  }
  return stageFromCurrentStage(workflow.current_stage);
}

function stageFromCurrentStage(currentStage: string): ProductDevQaStagePlan | undefined {
  return Object.values(STAGES).find((stage) => stage.currentStage === currentStage || stage.key === currentStage);
}

async function markStageRunning(
  store: RuntimeStore,
  workflow: ProductDevQaWorkflowRunRecord,
  stage: ProductDevQaStagePlan,
): Promise<{ workflow: ProductDevQaWorkflowRunRecord; attemptNumber: number }> {
  const attemptNumber = (workflow.stage_attempt_counts[stage.key] ?? 0) + 1;
  const now = nowIso();
  const running = setWorkflowStage({
    ...workflow,
    status: "running",
    waiting_on: null,
    blocked_reason: "",
    stage_attempt_counts: {
      ...workflow.stage_attempt_counts,
      [stage.key]: attemptNumber,
    },
    last_stage_key: stage.key,
    last_stage_attempt: attemptNumber,
    last_stage_verdict: null,
    last_stage_summary: "",
    last_stage_artifacts: [],
    summary: `${stage.currentStage} running.`,
    updated_at: now,
  }, stage);
  await setExecutionStageStatus(store, running, stage, "running", {});
  await writeAndSyncWorkflow(store, running);
  return { workflow: running, attemptNumber };
}

async function executeStage(args: {
  store: RuntimeStore;
  sessionId: string;
  repoRoot: string;
  projectRoot: string;
  request: string;
  workflow: ProductDevQaWorkflowRunRecord;
  stage: ProductDevQaStagePlan;
  attemptNumber: number;
  runner: AgentRunner;
  hooks: V2HookManager;
}): Promise<StageExecutionOutcome> {
  const attemptDir = stageAttemptDir(args.store, args.sessionId, args.stage, args.attemptNumber);
  await mkdir(attemptDir, { recursive: true });
  await writeJson(path.join(attemptDir, "pre-state.json"), args.workflow);
  const stageStartedAtIso = args.workflow.updated_at;
  const stageStartedAt = dateOnly(stageStartedAtIso);
  const stageCtx: V2StageHookContext = {
    sessionId: args.sessionId,
    workflowId: PRODUCT_DEV_QA_WORKFLOW_ID,
    workflowRunId: args.workflow.workflow_run_id,
    stage: args.stage.key,
    role: args.stage.role,
    attempt: args.attemptNumber,
    repoRoot: args.repoRoot,
    projectRoot: args.projectRoot,
    stateRoot: args.store.stateRoot,
    stageStartedAt,
    inputArtifacts: args.stage.requiredInputs,
    requiredOutputs: args.stage.requiredOutputs,
    requiredEvidence: args.stage.requiredEvidence,
  };
  try {
    await args.hooks.beforeStage(stageCtx);
  } catch (error) {
    await notifyStageError(args.hooks, stageCtx, "before_stage", error);
  }

  let artifactInputs: Awaited<ReturnType<typeof readInputArtifacts>>;
  let routing: Awaited<ReturnType<typeof resolveSkillRouting>>;
  try {
    artifactInputs = await readInputArtifacts(args.store, args.sessionId, args.stage.requiredInputs);
    routing = await resolveSkillRouting({
      repoRoot: args.repoRoot,
      projectRoot: args.projectRoot,
      workflowId: PRODUCT_DEV_QA_WORKFLOW_ID,
      stage: args.stage.key,
      role: args.stage.role,
    });
  } catch (error) {
    await notifyStageError(args.hooks, stageCtx, "prepare_context", error);
    throw error;
  }
  const contextPacket = {
    schema_version: 1,
    workflow_run_id: args.workflow.workflow_run_id,
    workflow_id: PRODUCT_DEV_QA_WORKFLOW_ID,
    role: args.stage.currentRole,
    step: args.stage.currentStep,
    stage: args.stage.key,
    attempt: args.attemptNumber,
    goal: args.stage.goal,
    input_artifacts: args.stage.requiredInputs,
    output_artifacts: args.stage.requiredOutputs,
    required_evidence: args.stage.requiredEvidence,
    missing_input_artifacts: artifactInputs.missing,
    constraints: {
      can_write_code: args.stage.canWriteCode,
      must_produce_verdict: args.stage.role === "qa",
    },
    skill_routing: skillRoutingMetadata(routing),
  };
  const contextPacketPath = path.join(attemptDir, "context-packet.json");
  await writeJson(contextPacketPath, contextPacket);
  await writeJson(path.join(attemptDir, "skill-routing.json"), skillRoutingAuditMetadata(routing));

  const prompt = renderStagePrompt({
    request: args.request,
    stage: args.stage,
    artifactInputs: artifactInputs.contents,
    missingInputArtifacts: artifactInputs.missing,
    skillInjection: renderSkillInjection(routing),
  });
  const trace = await args.store.recordPromptTrace({
    sessionId: args.sessionId,
    role: args.stage.role,
    prompt,
    runner: args.runner.name,
    source: "runtime.productDevQaWorkflow",
    metadata: {
      workflow_id: PRODUCT_DEV_QA_WORKFLOW_ID,
      stage: args.stage.key,
      step: args.stage.currentStep ?? "",
      attempt: args.attemptNumber,
      write_allowed: args.stage.canWriteCode,
      skill_routing: skillRoutingAuditMetadata(routing),
    },
  });
  const promptPath = path.join(attemptDir, "prompt.md");
  await writeFile(promptPath, prompt);
  await writeJson(path.join(attemptDir, "prompt.meta.json"), trace);

  const executorStartedAt = nowIso();
  const executorStartedMs = Date.now();
  const executorCtx: V2ExecutorHookContext = {
    ...stageCtx,
    executorStartedAt,
    runner: args.runner.name,
    maxTurns: args.stage.executor.maxTurns,
    writeAllowed: args.stage.canWriteCode,
    promptTraceId: trace.prompt_id,
    promptPath,
    contextPacketPath,
    skillRouting: skillRoutingMetadata(routing),
  };
  try {
    await args.hooks.beforeExecutor(executorCtx);
  } catch (error) {
    await notifyStageError(args.hooks, stageCtx, "before_executor", error);
  }

  let result: AgentTaskResult;
  if (routing.missing_required_skills.length > 0) {
    const blockedRun = await args.store.createAgentRun({
      sessionId: args.sessionId,
      role: args.stage.role,
      runner: args.runner.name,
      input: prompt,
      metadata: {
        workflow_id: PRODUCT_DEV_QA_WORKFLOW_ID,
        stage: args.stage.key,
        prompt_trace_id: trace.prompt_id,
        routing_config_gap: true,
        missing_required_skills: routing.missing_required_skills,
      },
    });
    const completed = await args.store.completeAgentRun(blockedRun, {
      status: "blocked",
      output: `Routing config gap: missing required skills ${routing.missing_required_skills.join(", ")}.`,
      metadata: {
        routing_config_gap: true,
        missing_required_skills: routing.missing_required_skills,
      },
    });
    result = {
      agentRun: completed,
      output: completed.output,
      filesChanged: [],
      commandsRun: [],
      tokenUsage: emptyTokenUsage(),
    };
  } else {
    result = await runStageSafely({
      store: args.store,
      runner: args.runner,
      sessionId: args.sessionId,
      role: args.stage.role,
      repoRoot: args.repoRoot,
      prompt,
      writeAllowed: args.stage.canWriteCode,
      maxTurns: args.stage.executor.maxTurns,
      traceId: trace.prompt_id,
      stageKey: args.stage.key,
      stageCtx,
      hooks: args.hooks,
    });
  }
  const executorCompletedAt = nowIso();
  const executorDurationMs = Date.now() - executorStartedMs;
  try {
    await args.hooks.afterExecutor({
      ...executorCtx,
      executorCompletedAt,
      executorDurationMs,
      agentRunId: result.agentRun.agent_run_id,
      executorStatus: result.agentRun.status,
      filesChanged: result.filesChanged,
      commandsRun: result.commandsRun,
      tokenUsage: result.tokenUsage,
    });
  } catch (error) {
    await notifyStageError(args.hooks, stageCtx, "after_executor", error);
  }

  const baseVerdict: StageVerdict =
    result.agentRun.status === "completed"
      ? args.stage.key === "qa"
        ? parseQaVerdict(result.output)
        : "passed"
      : "blocked";
  const artifactRecords = [];
  if (baseVerdict !== "blocked") {
    try {
      for (const name of args.stage.requiredOutputs) {
        artifactRecords.push(await args.store.writeArtifact({
          sessionId: args.sessionId,
          role: args.stage.role,
          name,
          content: renderOutputArtifact({
            name,
            stage: args.stage,
            verdict: baseVerdict,
            output: result.output,
            filesChanged: result.filesChanged,
            commandsRun: result.commandsRun,
          }),
          metadata: {
            workflow_id: PRODUCT_DEV_QA_WORKFLOW_ID,
            stage: args.stage.key,
            attempt: args.attemptNumber,
            agent_run_id: result.agentRun.agent_run_id,
            prompt_trace_id: trace.prompt_id,
            verdict: baseVerdict,
          },
        }));
      }
    } catch (error) {
      await notifyStageError(args.hooks, stageCtx, "write_artifacts", error);
    }
  }
  const artifactNames = artifactRecords.map((artifact) => artifact.name);
  const artifactPaths = artifactRecords.map((artifact) => artifact.path);
  const summary = firstLine(result.output) || `${args.stage.currentStage} ${baseVerdict}.`;
  const reason = baseVerdict === "failed"
    ? "QA reported VERDICT: failed."
    : baseVerdict === "blocked"
      ? result.output || result.agentRun.error || `${args.stage.currentStage} blocked.`
      : "";

  try {
    await writeJson(path.join(attemptDir, "candidate.json"), {
      schema_version: 1,
      stage: args.stage.key,
      attempt: args.attemptNumber,
      output: result.output,
      files_changed: result.filesChanged,
      commands_run: result.commandsRun,
      token_usage: result.tokenUsage,
      artifact_names: artifactNames,
      artifact_paths: artifactPaths,
    });
    await writeJson(path.join(attemptDir, "verdict.json"), {
      schema_version: 1,
      stage: args.stage.key,
      attempt: args.attemptNumber,
      verdict: baseVerdict,
      reason,
      required_outputs: args.stage.requiredOutputs,
      produced_artifacts: artifactNames,
      evidence_refs: {
        prompt_trace_id: trace.prompt_id,
        agent_run_id: result.agentRun.agent_run_id,
      },
      token_usage: result.tokenUsage,
    });
    await writeJson(path.join(attemptDir, "executor-run.json"), {
      agent_run: result.agentRun,
      files_changed: result.filesChanged,
      commands_run: result.commandsRun,
      token_usage: result.tokenUsage,
      executor_started_at: executorStartedAt,
      executor_completed_at: executorCompletedAt,
      executor_duration_ms: executorDurationMs,
    });
  } catch (error) {
    await notifyStageError(args.hooks, stageCtx, "write_artifacts", error);
  }

  return {
    verdict: baseVerdict,
    output: result.output,
    agentRun: result.agentRun,
    filesChanged: result.filesChanged,
    commandsRun: result.commandsRun,
    tokenUsage: result.tokenUsage,
    promptTraceId: trace.prompt_id,
    artifactPaths,
    artifactNames,
    summary,
    reason,
    repoRoot: args.repoRoot,
    projectRoot: args.projectRoot,
    promptPath,
    contextPacketPath,
    skillRouting: skillRoutingMetadata(routing),
    stageStartedAt,
    stageStartedAtIso,
    executorStartedAt,
    executorCompletedAt,
    executorDurationMs,
  };
}

async function transitionAfterStage(args: {
  store: RuntimeStore;
  workflow: ProductDevQaWorkflowRunRecord;
  stage: ProductDevQaStagePlan;
  outcome: StageExecutionOutcome;
  maxQaFailureLoops: number;
  hooks: V2HookManager;
}): Promise<ProductDevQaWorkflowRunRecord> {
  const now = nowIso();
  await setExecutionStageStatus(args.store, args.workflow, args.stage, args.outcome.verdict === "blocked" ? "blocked" : "completed", {
    agent_run_id: args.outcome.agentRun.agent_run_id,
    prompt_trace_id: args.outcome.promptTraceId,
    artifact_path: args.outcome.artifactPaths[0] ?? "",
    files_changed: args.outcome.filesChanged,
    commands_run: args.outcome.commandsRun,
    completed_at: now,
    summary: `${args.stage.currentStage}: ${args.outcome.summary}`,
  });

  let next: ProductDevQaWorkflowRunRecord;
  if (args.outcome.verdict === "blocked") {
    next = {
      ...args.workflow,
      status: "blocked",
      blocked_reason: args.outcome.reason || `${args.stage.currentStage} blocked.`,
      summary: args.outcome.reason || `${args.stage.currentStage} blocked.`,
      last_stage_verdict: "blocked",
      last_stage_summary: args.outcome.summary,
      last_stage_artifacts: args.outcome.artifactNames,
      updated_at: now,
    };
    await setExecutionStatusForWorkflow(args.store, next, "blocked");
  } else if (args.stage.key === "product") {
    next = {
      ...args.workflow,
      status: "waiting_human",
      current_role: "product",
      current_step: null,
      current_stage: "product",
      waiting_on: "product_check",
      summary: "Waiting for human check after Product contract.",
      last_stage_verdict: "passed",
      last_stage_summary: args.outcome.summary,
      last_stage_artifacts: args.outcome.artifactNames,
      updated_at: now,
    };
    await setExecutionStatusForWorkflow(args.store, next, "waiting_human");
  } else if (args.stage.key === "dev.technical_plan") {
    next = {
      ...args.workflow,
      status: "waiting_human",
      current_role: "dev",
      current_step: "technical_plan",
      current_stage: "dev:technical_plan",
      waiting_on: "dev_plan_check",
      summary: "Waiting for human check after Dev technical plan.",
      last_stage_verdict: "passed",
      last_stage_summary: args.outcome.summary,
      last_stage_artifacts: args.outcome.artifactNames,
      updated_at: now,
    };
    await setExecutionStatusForWorkflow(args.store, next, "waiting_human");
  } else if (args.stage.key === "qa" && args.outcome.verdict === "failed") {
    if ((args.workflow.stage_attempt_counts.qa ?? 0) >= args.maxQaFailureLoops) {
      next = {
        ...args.workflow,
        status: "blocked",
        blocked_reason: `QA failed ${args.workflow.stage_attempt_counts.qa ?? 0} time(s); stopping to avoid an infinite loop.`,
        summary: "QA failed repeatedly and needs human review.",
        last_stage_verdict: "failed",
        last_stage_summary: args.outcome.summary,
        last_stage_artifacts: args.outcome.artifactNames,
        updated_at: now,
      };
      await setExecutionStatusForWorkflow(args.store, next, "blocked");
    } else {
      next = setWorkflowStage({
        ...args.workflow,
        status: "running",
        waiting_on: null,
        summary: "QA failed; returning directly to Dev implementation.",
        blocked_reason: "",
        last_stage_verdict: "failed",
        last_stage_summary: args.outcome.summary,
        last_stage_artifacts: args.outcome.artifactNames,
        updated_at: now,
      }, STAGES["dev.implementation"]);
      await resetExecutionFromStage(args.store, next, "dev.implementation");
    }
  } else if (args.stage.key === "qa") {
    next = {
      ...args.workflow,
      status: "done",
      current_role: "qa",
      current_step: null,
      current_stage: "done",
      waiting_on: null,
      summary: "Local code changes and QA verification report are complete.",
      blocked_reason: "",
      last_stage_verdict: "passed",
      last_stage_summary: args.outcome.summary,
      last_stage_artifacts: args.outcome.artifactNames,
      updated_at: now,
      completed_at: now,
    };
    await setExecutionStatusForWorkflow(args.store, next, "done");
  } else {
    const nextStage = args.stage.key === "intake_summary" ? STAGES.product : STAGES.qa;
    next = setWorkflowStage({
      ...args.workflow,
      status: "running",
      waiting_on: null,
      summary: `${args.stage.currentStage} passed; continuing to ${nextStage.currentStage}.`,
      blocked_reason: "",
      last_stage_verdict: "passed",
      last_stage_summary: args.outcome.summary,
      last_stage_artifacts: args.outcome.artifactNames,
      updated_at: now,
    }, nextStage);
    await setExecutionStatusForWorkflow(args.store, next, "in_progress");
  }

  await writeAndSyncWorkflow(args.store, next);
  const attemptDir = stageAttemptDir(args.store, args.workflow.session_id, args.stage, args.workflow.stage_attempt_counts[args.stage.key] ?? 1);
  await writeJson(path.join(attemptDir, "post-state.json"), next);
  try {
    await args.hooks.afterStage({
      sessionId: args.workflow.session_id,
      workflowId: PRODUCT_DEV_QA_WORKFLOW_ID,
      workflowRunId: args.workflow.workflow_run_id,
      stage: args.stage.key,
      role: args.stage.role,
      attempt: args.workflow.stage_attempt_counts[args.stage.key] ?? 1,
      repoRoot: args.outcome.repoRoot,
      projectRoot: args.outcome.projectRoot,
      stateRoot: args.store.stateRoot,
      stageStartedAt: args.outcome.stageStartedAt,
      inputArtifacts: args.stage.requiredInputs,
      requiredOutputs: args.stage.requiredOutputs,
      requiredEvidence: args.stage.requiredEvidence,
      executorStartedAt: args.outcome.executorStartedAt,
      runner: args.outcome.agentRun.runner,
      maxTurns: args.stage.executor.maxTurns,
      writeAllowed: args.stage.canWriteCode,
      promptTraceId: args.outcome.promptTraceId,
      promptPath: args.outcome.promptPath,
      contextPacketPath: args.outcome.contextPacketPath,
      skillRouting: args.outcome.skillRouting,
      executorCompletedAt: args.outcome.executorCompletedAt,
      executorDurationMs: args.outcome.executorDurationMs,
      agentRunId: args.outcome.agentRun.agent_run_id,
      executorStatus: args.outcome.agentRun.status,
      filesChanged: args.outcome.filesChanged,
      commandsRun: args.outcome.commandsRun,
      tokenUsage: args.outcome.tokenUsage,
      stageCompletedAt: now,
      stageDurationMs: durationMs(args.outcome.stageStartedAtIso, now),
      verdict: args.outcome.verdict,
      summary: args.outcome.summary,
      reason: args.outcome.reason,
      artifactNames: args.outcome.artifactNames,
      artifactPaths: args.outcome.artifactPaths,
      nextStatus: next.status,
      nextStage: next.current_stage,
    });
  } catch (error) {
    await notifyStageError(args.hooks, {
      sessionId: args.workflow.session_id,
      workflowId: PRODUCT_DEV_QA_WORKFLOW_ID,
      workflowRunId: args.workflow.workflow_run_id,
      stage: args.stage.key,
      role: args.stage.role,
      attempt: args.workflow.stage_attempt_counts[args.stage.key] ?? 1,
      repoRoot: args.outcome.repoRoot,
      projectRoot: args.outcome.projectRoot,
      stateRoot: args.store.stateRoot,
      stageStartedAt: args.outcome.stageStartedAt,
      inputArtifacts: args.stage.requiredInputs,
      requiredOutputs: args.stage.requiredOutputs,
      requiredEvidence: args.stage.requiredEvidence,
    }, "after_stage", error);
  }
  return next;
}

async function blockStageRuntimeError(args: {
  store: RuntimeStore;
  workflow: ProductDevQaWorkflowRunRecord;
  stage: ProductDevQaStagePlan;
  attemptNumber: number;
  runner: AgentRunner;
  error: unknown;
}): Promise<ProductDevQaWorkflowRunRecord> {
  const now = nowIso();
  const message = errorMessage(args.error);
  const agentRun = await args.store.createAgentRun({
    sessionId: args.workflow.session_id,
    role: args.stage.role,
    runner: args.runner.name,
    input: `${args.stage.currentStage} runtime error`,
    metadata: {
      workflow_id: PRODUCT_DEV_QA_WORKFLOW_ID,
      stage: args.stage.key,
      attempt: args.attemptNumber,
      runtime_error: true,
    },
  });
  const completed = await args.store.completeAgentRun(agentRun, {
    status: "blocked",
    output: message,
    error: message,
    metadata: {
      runtime_error: true,
    },
  });
  const blocked: ProductDevQaWorkflowRunRecord = {
    ...args.workflow,
    status: "blocked",
    waiting_on: null,
    blocked_reason: message,
    summary: `${args.stage.currentStage} blocked by runtime error: ${message}`,
    last_stage_verdict: "blocked",
    last_stage_summary: message,
    last_stage_artifacts: [],
    updated_at: now,
  };
  await setExecutionStageStatus(args.store, blocked, args.stage, "blocked", {
    agent_run_id: completed.agent_run_id,
    prompt_trace_id: "",
    artifact_path: "",
    files_changed: [],
    commands_run: [],
    completed_at: now,
    summary: `${args.stage.currentStage}: runtime error: ${message}`,
  });
  await setExecutionStatusForWorkflow(args.store, blocked, "blocked");
  await writeAndSyncWorkflow(args.store, blocked);
  const attemptDir = stageAttemptDir(args.store, args.workflow.session_id, args.stage, args.attemptNumber);
  await mkdir(attemptDir, { recursive: true });
  await writeJson(path.join(attemptDir, "post-state.json"), blocked);
  await writeJson(path.join(attemptDir, "runtime-error.json"), {
    schema_version: 1,
    stage: args.stage.key,
    attempt: args.attemptNumber,
    error: message,
    agent_run_id: completed.agent_run_id,
  });
  await args.store.appendEvent({
    at: now,
    session_id: args.workflow.session_id,
    kind: "stage_blocked_by_error",
    role: args.stage.role,
    status: "blocked",
    message,
    details: {
      workflow_id: PRODUCT_DEV_QA_WORKFLOW_ID,
      workflow_run_id: args.workflow.workflow_run_id,
      stage: args.stage.key,
      attempt: args.attemptNumber,
      agent_run_id: completed.agent_run_id,
    },
  });
  return blocked;
}

async function transitionToDone(
  store: RuntimeStore,
  workflow: ProductDevQaWorkflowRunRecord,
): Promise<ProductDevQaWorkflowRunRecord> {
  const now = nowIso();
  const done: ProductDevQaWorkflowRunRecord = {
    ...workflow,
    status: "done",
    current_role: "qa",
    current_step: null,
    current_stage: "done",
    waiting_on: null,
    summary: "Local code changes and QA verification report are complete.",
    updated_at: now,
    completed_at: now,
  };
  await setExecutionStatusForWorkflow(store, done, "done");
  await writeAndSyncWorkflow(store, done);
  return done;
}

function setWorkflowStage(
  workflow: ProductDevQaWorkflowRunRecord,
  stage: ProductDevQaStagePlan,
): ProductDevQaWorkflowRunRecord {
  return {
    ...workflow,
    current_role: stage.currentRole,
    current_step: stage.currentStep,
    current_stage: stage.currentStage,
  };
}

async function runStageSafely(args: {
  store: RuntimeStore;
  runner: AgentRunner;
  sessionId: string;
  role: AgentRole;
  repoRoot: string;
  prompt: string;
  writeAllowed: boolean;
  maxTurns: number;
  traceId: string;
  stageKey: StageKey;
  stageCtx: V2StageHookContext;
  hooks: V2HookManager;
}): Promise<AgentTaskResult> {
  try {
    const result = await args.runner.runTask({
      sessionId: args.sessionId,
      role: args.role,
      repoRoot: args.repoRoot,
      prompt: args.prompt,
      writeAllowed: args.writeAllowed,
      maxTurns: args.maxTurns,
    });
    if (result.agentRun.status === "completed") {
      return result;
    }
    const completed = await args.store.completeAgentRun(result.agentRun, {
      status: "blocked",
      output: result.output || result.agentRun.error || `${args.stageKey} did not complete.`,
      metadata: {
        workflow_id: PRODUCT_DEV_QA_WORKFLOW_ID,
        stage: args.stageKey,
        prompt_trace_id: args.traceId,
      },
    });
    return { ...result, agentRun: completed, output: completed.output };
  } catch (error) {
    await recordStageError(args.hooks, args.stageCtx, "executor", error);
    const message = error instanceof Error ? error.message : String(error);
    const agentRun = await args.store.createAgentRun({
      sessionId: args.sessionId,
      role: args.role,
      runner: args.runner.name,
      input: args.prompt,
      metadata: {
        workflow_id: PRODUCT_DEV_QA_WORKFLOW_ID,
        stage: args.stageKey,
        prompt_trace_id: args.traceId,
        executor_status: "failed",
      },
    });
    const completed = await args.store.completeAgentRun(agentRun, {
      status: "blocked",
      output: message,
      error: message,
    });
    return { agentRun: completed, output: message, filesChanged: [], commandsRun: [], tokenUsage: emptyTokenUsage() };
  }
}

async function notifyStageError(
  hooks: V2HookManager,
  ctx: V2StageHookContext,
  phase: "before_stage" | "prepare_context" | "before_executor" | "executor" | "after_executor" | "write_artifacts" | "after_stage",
  error: unknown,
): Promise<never> {
  await recordStageError(hooks, ctx, phase, error);
  throw error instanceof Error ? error : new Error(errorMessage(error));
}

async function recordStageError(
  hooks: V2HookManager,
  ctx: V2StageHookContext,
  phase: "before_stage" | "prepare_context" | "before_executor" | "executor" | "after_executor" | "write_artifacts" | "after_stage",
  error: unknown,
): Promise<void> {
  const message = error instanceof Error ? error.message : String(error);
  try {
    await hooks.onStageError({ ...ctx, phase, error: message });
  } catch {
    // Keep the original stage error as the control-flow cause. Hook failure is
    // already written as hook_failed by V2HookManager when persistence works.
  }
}

function durationMs(startedAt: string, completedAt: string): number {
  const started = Date.parse(startedAt);
  const completed = Date.parse(completedAt);
  if (!Number.isFinite(started) || !Number.isFinite(completed) || completed < started) {
    return 0;
  }
  return completed - started;
}

function dateOnly(value: string): string {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    return value.slice(0, 10);
  }
  return new Date(parsed).toISOString().slice(0, 10);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function readInputArtifacts(
  store: RuntimeStore,
  sessionId: string,
  names: string[],
): Promise<{ contents: Array<{ name: string; content: string }>; missing: string[] }> {
  const contents: Array<{ name: string; content: string }> = [];
  const missing: string[] = [];
  for (const name of names) {
    try {
      const item = await store.readArtifactContent(sessionId, name);
      contents.push({ name, content: item.content });
    } catch {
      missing.push(name);
    }
  }
  return { contents, missing };
}

function renderStagePrompt(args: {
  request: string;
  stage: ProductDevQaStagePlan;
  artifactInputs: Array<{ name: string; content: string }>;
  missingInputArtifacts: string[];
  skillInjection: string;
}): string {
  const inputContext = args.stage.includeRequest
    ? `## Request\n${args.request}`
    : [
        "## Input Artifacts",
        args.artifactInputs.length
          ? args.artifactInputs.map((item) => `### ${item.name}\n${item.content.trim()}`).join("\n\n")
          : "No input artifacts.",
      ].join("\n");
  const missingInputs = args.missingInputArtifacts.length
    ? `\n\nMissing input artifacts: ${args.missingInputArtifacts.join(", ")}`
    : "";
  const qaVerdict = args.stage.role === "qa"
    ? "\nFor QA, include `VERDICT: passed` or `VERDICT: failed`."
    : "";
  const sections = [
    [
      "# AGT Stage",
      `Workflow: ${PRODUCT_DEV_QA_WORKFLOW_ID}`,
      `Stage: ${args.stage.currentStage}`,
      `Role: ${args.stage.currentRole}`,
      args.stage.currentStep ? `Step: ${args.stage.currentStep}` : "",
      `Goal: ${args.stage.goal}`,
      `Write access: ${args.stage.canWriteCode}`,
    ].filter(Boolean).join("\n"),
    inputContext + missingInputs,
    args.skillInjection,
    [
      "## Output Contract",
      `Artifacts: ${args.stage.requiredOutputs.join(", ")}`,
      `Evidence: ${args.stage.requiredEvidence.join(", ")}`,
      `Return a concise evidence-backed report.${qaVerdict}`,
    ].join("\n"),
  ];
  return sections.filter(Boolean).join("\n\n");
}

function renderOutputArtifact(args: {
  name: string;
  stage: ProductDevQaStagePlan;
  verdict: StageVerdict;
  output: string;
  filesChanged: string[];
  commandsRun: string[];
}): string {
  if (args.name === "implementation-ambiguities.json") {
    return `${JSON.stringify({
      schema_version: 1,
      stage: args.stage.key,
      verdict: args.verdict,
      ambiguities: [],
      notes: firstLine(args.output),
      raw_output: args.output,
    }, null, 2)}\n`;
  }
  if (args.name === "verification-evidence.json") {
    return `${JSON.stringify({
      schema_version: 1,
      stage: args.stage.key,
      verdict: args.verdict,
      commands_run: args.commandsRun,
      files_changed: args.filesChanged,
      unverified_items: [],
      raw_output: args.output,
    }, null, 2)}\n`;
  }
  return [
    `# ${args.name}`,
    "",
    `Workflow: ${PRODUCT_DEV_QA_WORKFLOW_ID}`,
    `Stage: ${args.stage.currentStage}`,
    `Verdict: ${args.verdict}`,
    "",
    args.output.trim() || `${args.stage.currentStage} produced no textual output.`,
  ].join("\n");
}

function parseQaVerdict(output: string): StageVerdict {
  if (/(?:^|\n)\s*(?:qa[_ -]?verdict|final[_ -]?verdict|verdict)\s*:\s*failed\b/i.test(output)) {
    return "failed";
  }
  return "passed";
}

function nextStageAfterGate(gate: HumanGate): StageKey {
  return gate === "product_check" ? "dev.technical_plan" : "dev.implementation";
}

async function setExecutionStageStatus(
  store: RuntimeStore,
  workflow: ProductDevQaWorkflowRunRecord,
  stage: ProductDevQaStagePlan,
  status: ExecutionWorkflowRecord["steps"][number]["status"],
  patch: Partial<ExecutionWorkflowRecord["steps"][number]>,
): Promise<void> {
  const index = EXECUTION_STAGE_ORDER.indexOf(stage.key);
  await store.updateExecutionWorkflow(workflow.session_id, (execution) => ({
    ...execution,
    status: executionStatusForProductDevQa(workflow),
    current_stage: stage.currentStage,
    steps: execution.steps.map((step, stepIndex) =>
      stepIndex === index
        ? {
            ...step,
            ...patch,
            role: stage.role,
            status,
            started_at: status === "running" ? workflow.updated_at : step.started_at,
          }
        : step,
    ),
    updated_at: workflow.updated_at,
  }));
}

async function setExecutionStatusForWorkflow(
  store: RuntimeStore,
  workflow: ProductDevQaWorkflowRunRecord,
  status: WorkflowStatus,
): Promise<void> {
  const stage = stageFromCurrentStage(workflow.current_stage);
  await store.updateExecutionWorkflow(workflow.session_id, (execution) => ({
    ...execution,
    status,
    current_stage: stage?.currentStage ?? workflow.current_stage,
    updated_at: workflow.updated_at,
  }));
}

async function resetExecutionFromStage(
  store: RuntimeStore,
  workflow: ProductDevQaWorkflowRunRecord,
  from: StageKey,
): Promise<void> {
  const fromIndex = EXECUTION_STAGE_ORDER.indexOf(from);
  await store.updateExecutionWorkflow(workflow.session_id, (execution) => ({
    ...execution,
    status: "in_progress",
    current_stage: STAGES[from].currentStage,
    steps: execution.steps.map((step, index) =>
      index >= fromIndex
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
    updated_at: workflow.updated_at,
  }));
}

async function writeAndSyncWorkflow(
  store: RuntimeStore,
  workflow: ProductDevQaWorkflowRunRecord,
): Promise<void> {
  await store.writeProductDevQaWorkflow(workflow);
  const delivery = buildProductDevQaDeliveryWorkflow(workflow);
  await store.writeDeliveryWorkflow(delivery);
  const session = await store.loadSession(workflow.session_id);
  const updatedSession = {
    ...session,
    workflow_id: PRODUCT_DEV_QA_WORKFLOW_ID,
    delivery_status: delivery.status,
    execution_status: executionStatusForProductDevQa(workflow),
    status: delivery.status,
    current_phase: delivery.current_phase,
    current_stage: workflow.current_stage,
    updated_at: workflow.updated_at,
  };
  await store.writeSession(updatedSession);
  await store.upsertSessionIndex(updatedSession);
}

function buildProductDevQaDeliveryWorkflow(workflow: ProductDevQaWorkflowRunRecord): DeliveryWorkflowRecord {
  const now = workflow.updated_at;
  const phases = (["requirement", "development", "verification", "handoff"] as DeliveryPhase[]).map((phase) => ({
    phase,
    status: phaseStatusForWorkflow(phase, workflow),
    summary: phaseSummaryForWorkflow(phase, workflow),
    blockers: workflow.status === "blocked" && currentPhaseForWorkflow(workflow) === phase
      ? [{
          id: `${phase}:${workflow.current_stage}:blocked`,
          phase,
          source_role: workflow.current_role ?? undefined,
          reason: workflow.blocked_reason || workflow.summary || `${workflow.current_stage} blocked.`,
          status: "open" as const,
          evidence_refs: [],
          created_at: now,
        }]
      : [],
    evidence_refs: [],
    updated_at: now,
    started_at: workflow.started_at,
    completed_at: phaseStatusForWorkflow(phase, workflow) === "passed" ? now : undefined,
  }));
  const blockers = phases.flatMap((phase) => phase.blockers);
  return {
    schema_version: 1,
    session_id: workflow.session_id,
    status: deliveryStatusForProductDevQa(workflow),
    current_phase: currentPhaseForWorkflow(workflow),
    phases,
    blockers,
    evidence_refs: [],
    summary: workflow.summary,
    updated_at: now,
  };
}

function phaseStatusForWorkflow(phase: DeliveryPhase, workflow: ProductDevQaWorkflowRunRecord): DeliveryPhaseStatus {
  if (workflow.status === "done") {
    return "passed";
  }
  if (workflow.status === "blocked" && currentPhaseForWorkflow(workflow) === phase) {
    return "blocked";
  }
  if (workflow.status === "waiting_human" && currentPhaseForWorkflow(workflow) === phase) {
    return "waiting_human";
  }
  if (currentPhaseForWorkflow(workflow) === phase && (workflow.status === "created" || workflow.status === "running")) {
    return "in_progress";
  }
  if (phase === "requirement") {
    return (workflow.stage_attempt_counts.product ?? 0) > 0 ? "passed" : "pending";
  }
  if (phase === "development") {
    return (workflow.stage_attempt_counts["dev.implementation"] ?? 0) > 0 && currentPhaseForWorkflow(workflow) !== "development"
      ? "passed"
      : "pending";
  }
  if (phase === "verification") {
    return "pending";
  }
  return "pending";
}

function phaseSummaryForWorkflow(phase: DeliveryPhase, workflow: ProductDevQaWorkflowRunRecord): string {
  if (workflow.status === "blocked" && currentPhaseForWorkflow(workflow) === phase) {
    return workflow.blocked_reason || workflow.summary;
  }
  if (workflow.status === "waiting_human" && currentPhaseForWorkflow(workflow) === phase) {
    return workflow.summary;
  }
  if (phaseStatusForWorkflow(phase, workflow) === "passed") {
    return `${phase} passed.`;
  }
  if (phaseStatusForWorkflow(phase, workflow) === "in_progress") {
    return workflow.summary;
  }
  return `${phase} pending.`;
}

function currentPhaseForWorkflow(workflow: ProductDevQaWorkflowRunRecord): DeliveryPhase {
  if (workflow.status === "done") {
    return "handoff";
  }
  if (workflow.current_role === "dev") {
    return "development";
  }
  if (workflow.current_role === "qa") {
    return "verification";
  }
  return "requirement";
}

function deliveryStatusForProductDevQa(workflow: ProductDevQaWorkflowRunRecord): WorkflowStatus {
  if (workflow.status === "done") {
    return "done";
  }
  if (workflow.status === "waiting_human") {
    return "waiting_human";
  }
  if (workflow.status === "blocked" || workflow.status === "cancelled") {
    return "blocked";
  }
  return "in_progress";
}

function executionStatusForProductDevQa(workflow: ProductDevQaWorkflowRunRecord): WorkflowStatus {
  return deliveryStatusForProductDevQa(workflow);
}

async function productDevQaRunResult(store: RuntimeStore, sessionId: string): Promise<RunResult> {
  const [session, workflow, delivery] = await Promise.all([
    store.loadSession(sessionId),
    store.loadProductDevQaWorkflow(sessionId),
    store.loadDeliveryWorkflow(sessionId),
  ]);
  const status = deliveryStatusForProductDevQa(workflow);
  return {
    session_id: sessionId,
    status,
    delivery_status: delivery.status,
    execution_status: executionStatusForProductDevQa(workflow),
    state_root: store.stateRoot,
    session_dir: store.sessionDir(sessionId),
    repo_root: session.repo_root,
    current_phase: delivery.current_phase,
    current_stage: workflow.current_stage,
    summary: workflow.summary,
    blocked_reason: workflow.blocked_reason,
  };
}

function stageAttemptDir(
  store: RuntimeStore,
  sessionId: string,
  stage: ProductDevQaStagePlan,
  attemptNumber: number,
): string {
  return path.join(store.stagesDir(sessionId), ...stage.directoryParts, `attempt-${String(attemptNumber).padStart(3, "0")}`);
}

function requiredRequest(value: string | undefined): string {
  const request = value?.trim();
  if (!request) {
    throw new Error("runProductDevQaWorkflow requires request when sessionId is not provided.");
  }
  return request;
}

function firstLine(value: string): string {
  return value.split("\n").find((line) => line.trim())?.trim().slice(0, 240) ?? "";
}
