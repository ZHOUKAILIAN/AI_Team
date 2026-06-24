import {
  type AgentRole,
  type AgentRunRecord,
  type MetricRecord,
  type ProductDevQaWorkflowRunRecord,
  type TokenUsage,
  nowReadableDateTime,
} from "./schema.js";
import { RuntimeStore } from "./store.js";
import { emptyTokenUsage } from "./usage.js";

export type V2StageHookContext = {
  sessionId: string;
  workflowId: string;
  workflowRunId: string;
  stage: string;
  role: AgentRole;
  attempt: number;
  repoRoot: string;
  projectRoot: string;
  stateRoot: string;
  stageStartedAt: string;
  inputArtifacts: string[];
  requiredOutputs: string[];
  requiredEvidence: string[];
};

export type V2ExecutorHookContext = V2StageHookContext & {
  executorStartedAt: string;
  runner: AgentRunRecord["runner"];
  maxTurns: number;
  writeAllowed: boolean;
  promptTraceId: string;
  promptPath: string;
  contextPacketPath: string;
  skillRouting: Record<string, unknown>;
};

export type V2ExecutorResultContext = V2ExecutorHookContext & {
  executorCompletedAt: string;
  executorDurationMs: number;
  agentRunId: string;
  executorStatus: AgentRunRecord["status"];
  filesChanged: string[];
  commandsRun: string[];
  tokenUsage: TokenUsage;
};

export type V2StageResultContext = V2ExecutorResultContext & {
  stageCompletedAt: string;
  stageDurationMs: number;
  verdict: "passed" | "failed" | "blocked";
  summary: string;
  reason: string;
  artifactNames: string[];
  artifactPaths: string[];
  nextStatus: ProductDevQaWorkflowRunRecord["status"];
  nextStage: string;
};

export type V2StageErrorContext = V2StageHookContext & {
  phase:
    | "before_stage"
    | "prepare_context"
    | "before_executor"
    | "executor"
    | "after_executor"
    | "write_artifacts"
    | "after_stage";
  error: string;
};

export type V2RuntimeHook = {
  name: string;
  required?: boolean;
  beforeStage?(ctx: V2StageHookContext): Promise<void>;
  beforeExecutor?(ctx: V2ExecutorHookContext): Promise<void>;
  afterExecutor?(ctx: V2ExecutorResultContext): Promise<void>;
  afterStage?(ctx: V2StageResultContext): Promise<void>;
  onStageError?(ctx: V2StageErrorContext): Promise<void>;
};

type HookPhase = "before_stage" | "before_executor" | "after_executor" | "after_stage" | "on_stage_error";

export class V2HookManager {
  constructor(
    private readonly store: RuntimeStore,
    private readonly hooks: V2RuntimeHook[],
  ) {}

  beforeStage(ctx: V2StageHookContext): Promise<void> {
    return this.invoke("before_stage", ctx, (hook) => hook.beforeStage?.(ctx));
  }

  beforeExecutor(ctx: V2ExecutorHookContext): Promise<void> {
    return this.invoke("before_executor", ctx, (hook) => hook.beforeExecutor?.(ctx));
  }

  afterExecutor(ctx: V2ExecutorResultContext): Promise<void> {
    return this.invoke("after_executor", ctx, (hook) => hook.afterExecutor?.(ctx));
  }

  afterStage(ctx: V2StageResultContext): Promise<void> {
    return this.invoke("after_stage", ctx, (hook) => hook.afterStage?.(ctx));
  }

  onStageError(ctx: V2StageErrorContext): Promise<void> {
    return this.invoke("on_stage_error", ctx, (hook) => hook.onStageError?.(ctx));
  }

  private async invoke(
    phase: HookPhase,
    ctx: V2StageHookContext,
    runHook: (hook: V2RuntimeHook) => Promise<void> | undefined,
  ): Promise<void> {
    for (const hook of this.hooks) {
      try {
        await runHook(hook);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        await this.recordHookFailure(hook, phase, ctx, message);
        if (hook.required) {
          throw new Error(`Required V2 hook ${hook.name} failed at ${phase}: ${message}`);
        }
      }
    }
  }

  private async recordHookFailure(
    hook: V2RuntimeHook,
    phase: HookPhase,
    ctx: V2StageHookContext,
    error: string,
  ): Promise<void> {
    try {
      await this.store.appendEvent({
        at: nowReadableDateTime(),
        session_id: ctx.sessionId,
        kind: "hook_failed",
        role: ctx.role,
        status: hook.required ? "required_failed" : "optional_failed",
        message: `${hook.name} failed at ${phase}.`,
        details: {
          hook: hook.name,
          phase,
          workflow_id: ctx.workflowId,
          workflow_run_id: ctx.workflowRunId,
          stage: ctx.stage,
          attempt: ctx.attempt,
          required: Boolean(hook.required),
          error,
        },
      });
    } catch {
      // A hook failure should preserve the original hook error. If even the
      // failure event cannot be persisted, required hooks still throw above.
    }
  }
}

export function createDefaultV2HookManager(store: RuntimeStore): V2HookManager {
  return new V2HookManager(store, [
    new AuditEventHook(store),
    new StageMetricsHook(store),
  ]);
}

class AuditEventHook implements V2RuntimeHook {
  readonly name = "audit_event";
  readonly required = true;

  constructor(private readonly store: RuntimeStore) {}

  async beforeStage(ctx: V2StageHookContext): Promise<void> {
    await this.store.appendEvent({
      at: ctx.stageStartedAt,
      session_id: ctx.sessionId,
      kind: "stage_started",
      role: ctx.role,
      status: "running",
      message: `${ctx.stage} attempt ${ctx.attempt} started.`,
      details: commonDetails(ctx),
    });
  }

  async beforeExecutor(ctx: V2ExecutorHookContext): Promise<void> {
    await this.store.appendEvent({
      at: ctx.executorStartedAt,
      session_id: ctx.sessionId,
      kind: "executor_started",
      role: ctx.role,
      status: "running",
      message: `${ctx.stage} executor started.`,
      details: {
        ...commonDetails(ctx),
        runner: ctx.runner,
        max_turns: ctx.maxTurns,
        write_allowed: ctx.writeAllowed,
        prompt_trace_id: ctx.promptTraceId,
        prompt_path: ctx.promptPath,
        context_packet_path: ctx.contextPacketPath,
      },
    });
  }

  async afterExecutor(ctx: V2ExecutorResultContext): Promise<void> {
    await this.store.appendEvent({
      at: ctx.executorCompletedAt,
      session_id: ctx.sessionId,
      kind: "executor_completed",
      role: ctx.role,
      status: ctx.executorStatus,
      message: `${ctx.stage} executor ${ctx.executorStatus}.`,
      details: {
        ...commonDetails(ctx),
        runner: ctx.runner,
        agent_run_id: ctx.agentRunId,
        executor_duration_ms: ctx.executorDurationMs,
        files_changed_count: ctx.filesChanged.length,
        commands_run_count: ctx.commandsRun.length,
        token_usage: ctx.tokenUsage,
      },
    });
  }

  async afterStage(ctx: V2StageResultContext): Promise<void> {
    await this.store.appendEvent({
      at: ctx.stageCompletedAt,
      session_id: ctx.sessionId,
      kind: "stage_completed",
      role: ctx.role,
      status: ctx.verdict,
      message: `${ctx.stage} ${ctx.verdict}.`,
      details: {
        ...commonDetails(ctx),
        stage_duration_ms: ctx.stageDurationMs,
        artifacts: ctx.artifactNames,
        next_status: ctx.nextStatus,
        next_stage: ctx.nextStage,
      },
    });
  }

  async onStageError(ctx: V2StageErrorContext): Promise<void> {
    await this.store.appendEvent({
      at: nowReadableDateTime(),
      session_id: ctx.sessionId,
      kind: "stage_error",
      role: ctx.role,
      status: "error",
      message: `${ctx.stage} failed at ${ctx.phase}.`,
      details: {
        ...commonDetails(ctx),
        phase: ctx.phase,
        error: ctx.error,
      },
    });
  }
}

class StageMetricsHook implements V2RuntimeHook {
  readonly name = "stage_metrics";
  readonly required = false;

  constructor(private readonly store: RuntimeStore) {}

  async afterStage(ctx: V2StageResultContext): Promise<void> {
    const metric: MetricRecord = {
      schema_version: 1,
      at: ctx.stageCompletedAt,
      session_id: ctx.sessionId,
      workflow_id: ctx.workflowId,
      workflow_run_id: ctx.workflowRunId,
      kind: "stage.completed",
      stage: ctx.stage,
      role: ctx.role,
      attempt: ctx.attempt,
      stage_started_at: ctx.stageStartedAt,
      stage_completed_at: ctx.stageCompletedAt,
      stage_duration_ms: ctx.stageDurationMs,
      executor_duration_ms: ctx.executorDurationMs,
      runner: ctx.runner,
      agent_run_id: ctx.agentRunId,
      executor_status: ctx.executorStatus,
      verdict: ctx.verdict,
      files_changed_count: ctx.filesChanged.length,
      commands_run_count: ctx.commandsRun.length,
      artifacts_count: ctx.artifactNames.length,
      token_usage: ctx.tokenUsage ?? emptyTokenUsage(),
      details: {
        next_status: ctx.nextStatus,
        next_stage: ctx.nextStage,
        summary: ctx.summary,
        reason: ctx.reason,
      },
    };
    await this.store.appendMetric(metric);
  }
}

function commonDetails(ctx: V2StageHookContext): Record<string, unknown> {
  return {
    workflow_id: ctx.workflowId,
    workflow_run_id: ctx.workflowRunId,
    stage: ctx.stage,
    attempt: ctx.attempt,
  };
}
