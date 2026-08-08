import { randomUUID } from "node:crypto";
import { createRunWorkspace, readWorkspaceJson, writeWorkspaceFile, writeWorkspaceJson } from "./workspace.js";
import type {
  GateContext,
  GateKind,
  HumanDecision,
  HumanGate,
  RoleExecutionResult,
  RoleExecutor,
  TeamRunResult,
  TeamRunSnapshot,
  TeamStage,
} from "./types.js";

const STAGES: Array<{ stage: TeamStage; role: string; gate?: GateKind }> = [
  { stage: "requirement_alignment", role: "product_aligner", gate: "alignment" },
  { stage: "technical_plan", role: "product_aligner", gate: "alignment" },
  { stage: "implementation", role: "implementer", gate: "delivery" },
  { stage: "review", role: "code_reviewer" },
  { stage: "verification", role: "verifier" },
];

export type ContextItem = {
  id: string;
  title: string;
  content: string;
  source: string;
  priority?: number;
  contentHash?: string;
  required?: boolean;
};

export type ContextRequest = {
  task: string;
  stage: TeamStage;
  role: string;
  repoRoot: string;
  runId: string;
  workspaceRoot: string;
};

export interface ContextProvider {
  name: string;
  provide(request: ContextRequest): Promise<ContextItem[]>;
}

export type AssembledContext = {
  items: ContextItem[];
  files: string[];
  promptSections: string[];
  sources: Array<{ id: string; source: string; contentHash?: string }>;
};

export interface ContextAssembler {
  assemble(request: ContextRequest, providers: ContextProvider[]): Promise<AssembledContext>;
}

export interface MemoryProvider extends ContextProvider {
  save?(item: ContextItem & { confidence: "confirmed" | "observed" | "inferred" | "deprecated" }): Promise<void>;
}

export interface WorkflowHook {
  beforeStage?(context: ContextRequest): Promise<void>;
  afterStage?(context: ContextRequest & { result: RoleExecutionResult }): Promise<void>;
  beforeGate?(context: GateContext): Promise<void>;
  afterGate?(context: GateContext & { decision: HumanDecision }): Promise<void>;
}

export type PiAgentTeamOptions = {
  repoRoot: string;
  workspaceDir: string;
  executor: RoleExecutor;
  gate: HumanGate;
  runId?: string;
  contextProviders?: ContextProvider[];
  contextAssembler?: ContextAssembler;
  hooks?: WorkflowHook[];
};

export class PiAgentTeam {
  private readonly options: PiAgentTeamOptions;

  constructor(options: PiAgentTeamOptions) {
    this.options = options;
  }

  async run(task: string): Promise<TeamRunResult> {
    const runId = this.options.runId ?? randomUUID();
    return this.execute({ runId, task, status: "running", nextStageIndex: 0, completedStages: [], outputs: {} });
  }

  async resume(runId: string): Promise<TeamRunResult> {
    const workspace = await createRunWorkspace(this.options.workspaceDir, runId);
    const snapshot = await readWorkspaceJson<TeamRunSnapshot>(workspace, "run.json");
    if (snapshot.status !== "waiting_for_human") {
      throw new Error(`Run ${runId} is not waiting for human confirmation`);
    }
    return this.execute(snapshot);
  }

  private async execute(snapshot: TeamRunSnapshot): Promise<TeamRunResult> {
    const workspace = await createRunWorkspace(this.options.workspaceDir, snapshot.runId);
    const outputs = { ...snapshot.outputs };
    const completedStages = [...snapshot.completedStages];
    let nextStageIndex = snapshot.nextStageIndex;
    let previous = completedStages.length > 0
      ? outputs[completedStages[completedStages.length - 1]]?.output ?? snapshot.task
      : snapshot.task;

    await writeWorkspaceFile(workspace, "request.md", `${snapshot.task}\n`);
    await writeWorkspaceJson(workspace, "run.json", { ...snapshot, status: "running" });

    while (nextStageIndex < STAGES.length) {
      const plan = STAGES[nextStageIndex];
      const contextRequest: ContextRequest = {
        task: snapshot.task,
        stage: plan.stage,
        role: plan.role,
        repoRoot: this.options.repoRoot,
        runId: snapshot.runId,
        workspaceRoot: workspace.root,
      };
      for (const hook of this.options.hooks ?? []) await hook.beforeStage?.(contextRequest);
      const context = this.options.contextAssembler
        ? await this.options.contextAssembler.assemble(contextRequest, this.options.contextProviders ?? [])
        : undefined;
      const output = await this.options.executor.run({
        runId: snapshot.runId,
        stage: plan.stage,
        role: plan.role,
        prompt: buildStagePrompt(snapshot.task, plan.stage, previous, context),
        repoRoot: this.options.repoRoot,
        workspaceRoot: workspace.root,
      });
      outputs[plan.stage] = output;
      await writeWorkspaceJson(workspace, `${plan.stage}/result.json`, output);
      for (const hook of this.options.hooks ?? []) await hook.afterStage?.({ ...contextRequest, result: output });

      if (output.status !== "completed") {
        const failed: TeamRunSnapshot = {
          ...snapshot,
          status: output.status === "cancelled" ? "stopped" : "failed",
          outputs,
          completedStages,
          nextStageIndex,
        };
        await writeWorkspaceJson(workspace, "run.json", failed);
        return failed;
      }

      completedStages.push(plan.stage);
      previous = output.output;
      nextStageIndex += 1;

      if (!plan.gate) continue;
      const gateContext: GateContext = {
        runId: snapshot.runId,
        stage: plan.stage,
        role: plan.role,
        kind: plan.gate,
        output,
        workspaceRoot: workspace.root,
      };
      for (const hook of this.options.hooks ?? []) await hook.beforeGate?.(gateContext);
      const decision = await this.options.gate.confirm(gateContext);
      for (const hook of this.options.hooks ?? []) await hook.afterGate?.({ ...gateContext, decision });

      if (decision === "approve") continue;
      if (decision === "retry" || decision === "edit") {
        completedStages.pop();
        nextStageIndex -= 1;
        previous = nextStageIndex > 0
          ? outputs[STAGES[nextStageIndex - 1].stage]?.output ?? snapshot.task
          : snapshot.task;
        continue;
      }

      const paused: TeamRunSnapshot = {
        runId: snapshot.runId,
        task: snapshot.task,
        status: decision === "pause" ? "waiting_for_human" : "stopped",
        nextStageIndex,
        completedStages,
        outputs,
        waitingStage: plan.stage,
        waitingGate: plan.gate,
      };
      await writeWorkspaceJson(workspace, "run.json", paused);
      return paused;
    }

    const completed: TeamRunSnapshot = {
      runId: snapshot.runId,
      task: snapshot.task,
      status: "completed",
      nextStageIndex,
      completedStages,
      outputs,
    };
    await writeWorkspaceJson(workspace, "run.json", completed);
    return completed;
  }
}

function buildStagePrompt(task: string, stage: TeamStage, previous: string, context?: AssembledContext): string {
  const contextText = context?.promptSections.length ? `\n\n## Additional context\n${context.promptSections.join("\n\n")}` : "";
  const instructions: Record<TeamStage, string> = {
    requirement_alignment: "Do requirements alignment only. Do not modify code. Ask at most one decision question at a time and provide a recommendation.",
    technical_plan: "Produce a technical plan only. Do not modify code. Identify decisions, risks, files, tests, and a recommendation.",
    implementation: "Implement only the confirmed requirements and technical plan. Record changed files and self-test evidence.",
    review: "Review the implementation only. Do not modify code. Report Standards and Spec findings separately.",
    verification: "Independently verify the confirmed requirements and implementation. Report passed, failed, or blocked with evidence.",
  };
  return [
    `You are running the ${stage} stage of an agent team workflow.`,
    instructions[stage],
    `Original task: ${task}`,
    `Previous stage handoff: ${previous}`,
    "Use the repository and current run workspace as the source of truth.",
    "Produce a concise, evidence-based result for the next stage.",
    contextText,
  ].join("\n");
}
