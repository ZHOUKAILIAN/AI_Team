export type TeamStage = "requirement_alignment" | "technical_plan" | "implementation" | "review" | "verification";
export type RoleName = string;

export type RoleExecutionStatus = "completed" | "failed" | "cancelled" | "timed_out";

export type RoleExecutionResult = {
  status: RoleExecutionStatus;
  output: string;
  events: unknown[];
  filesChanged: string[];
  commandsRun: string[];
  usage?: Record<string, unknown>;
};

export type RoleExecutionInput = {
  runId: string;
  stage: TeamStage;
  role: RoleName;
  prompt: string;
  repoRoot: string;
  workspaceRoot: string;
  signal?: AbortSignal;
  onEvent?: (event: unknown) => void;
};

export interface RoleExecutor {
  run(input: RoleExecutionInput): Promise<RoleExecutionResult>;
  cancel?(): Promise<void>;
}

export type HumanDecision = "approve" | "edit" | "retry" | "pause" | "stop";
export type GateKind = "alignment" | "delivery";

export type GateContext = {
  runId: string;
  stage: TeamStage;
  role: RoleName;
  kind: GateKind;
  output: RoleExecutionResult;
  workspaceRoot: string;
};

export interface HumanGate {
  confirm(context: GateContext): Promise<HumanDecision>;
}

export type TeamRunStatus = "running" | "waiting_for_human" | "completed" | "failed" | "stopped";

export type TeamRunResult = {
  runId: string;
  status: TeamRunStatus;
  completedStages: TeamStage[];
  outputs: Partial<Record<TeamStage, RoleExecutionResult>>;
  waitingStage?: TeamStage;
  waitingGate?: GateKind;
};

export type TeamRunSnapshot = {
  runId: string;
  task: string;
  status: TeamRunStatus;
  nextStageIndex: number;
  completedStages: TeamStage[];
  outputs: Partial<Record<TeamStage, RoleExecutionResult>>;
  waitingStage?: TeamStage;
  waitingGate?: GateKind;
};
