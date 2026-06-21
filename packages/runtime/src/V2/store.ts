import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import {
  type ArtifactRecord,
  ArtifactRecordSchema,
  type AgentRole,
  type AgentRunRecord,
  AgentRunSchema,
  type DeliveryWorkflowRecord,
  DeliveryWorkflowSchema,
  type ExecutionWorkflowRecord,
  ExecutionWorkflowSchema,
  type ProductDevQaWorkflowRunRecord,
  ProductDevQaWorkflowRunSchema,
  type PromptTraceRecord,
  PromptTraceSchema,
  type RequestSourceRecord,
  type RuntimeEvent,
  RuntimeEventSchema,
  type RuntimeConfig,
  RuntimeConfigSchema,
  type RuntimeProfile,
  type SessionIndex,
  type SessionIndexEntry,
  SessionIndexSchema,
  type SessionRecord,
  SessionSchema,
  type ToolCallRecord,
  ToolCallSchema,
  type WorktreeRecord,
  nowIso,
} from "./schema.js";
import { createArtifactId, createPromptTraceId, createRunId, createSessionId, sha256Hex } from "./ids.js";
import { createInitialDeliveryWorkflow, projectDeliveryWorkflow } from "./delivery-projector.js";

export type CreateSessionOptions = {
  request: string;
  profile: RuntimeProfile;
  repoRoot: string;
  projectRoot?: string;
  stateRoot?: string;
  workflowId?: string;
  worktree?: WorktreeRecord;
  requestSources?: RequestSourceRecord[];
  source?: SessionRecord["source"];
  migration?: SessionRecord["migration"];
};

export class RuntimeStore {
  readonly stateRoot: string;

  constructor(stateRoot: string) {
    this.stateRoot = path.resolve(stateRoot);
  }

  sessionDir(sessionId: string): string {
    return path.join(this.stateRoot, "sessions", sessionId);
  }

  agentsDir(sessionId: string): string {
    return path.join(this.sessionDir(sessionId), "agents");
  }

  artifactsDir(sessionId: string): string {
    return path.join(this.sessionDir(sessionId), "artifacts");
  }

  stagesDir(sessionId: string): string {
    return path.join(this.sessionDir(sessionId), "stages");
  }

  promptTracesDir(): string {
    return path.join(this.stateRoot, "prompt_traces");
  }

  promptTraceDir(promptId: string): string {
    return path.join(this.promptTracesDir(), promptId);
  }

  configPath(): string {
    return path.join(this.stateRoot, "config.json");
  }

  sessionIndexPath(): string {
    return path.join(this.stateRoot, "session-index.json");
  }

  async ensureLayout(): Promise<void> {
    await mkdir(path.join(this.stateRoot, "sessions"), { recursive: true });
    await mkdir(this.promptTracesDir(), { recursive: true });
  }

  async createSession(options: CreateSessionOptions): Promise<SessionRecord> {
    await this.ensureLayout();
    const sessionId = createSessionId(options.request);
    const createdAt = nowIso();
    const session: SessionRecord = {
      schema_version: 1,
      session_id: sessionId,
      request: options.request,
      request_sources: options.requestSources ?? [],
      workflow_id: options.workflowId ?? "",
      profile: options.profile,
      delivery_status: "in_progress",
      execution_status: "in_progress",
      status: "in_progress",
      current_phase: "requirement",
      project_root: path.resolve(options.projectRoot ?? options.repoRoot),
      repo_root: path.resolve(options.repoRoot),
      state_root: this.stateRoot,
      created_at: createdAt,
      updated_at: createdAt,
      current_stage: "created",
      source: options.source ?? "new",
      prompt_trace_ids: [],
      worktree: options.worktree,
      migration: options.migration,
    };
    await mkdir(this.agentsDir(sessionId), { recursive: true });
    await mkdir(this.artifactsDir(sessionId), { recursive: true });
    await this.writeSession(session);
    await this.writeExecutionWorkflow({
      schema_version: 1,
      session_id: sessionId,
      profile: options.profile,
      status: "in_progress",
      current_stage: "created",
      steps: [],
      summary: "",
      blocked_reason: "",
      files_changed: [],
      commands_run: [],
      updated_at: createdAt,
    });
    await this.writeDeliveryWorkflow(createInitialDeliveryWorkflow(sessionId, createdAt));
    await this.appendEvent({
      at: createdAt,
      session_id: sessionId,
      kind: "session_created",
      status: "in_progress",
      message: `Created ${options.profile} session.`,
      details: { repo_root: session.repo_root, project_root: session.project_root },
    });
    await this.upsertSessionIndex(session);
    return session;
  }

  async writeSession(session: SessionRecord): Promise<void> {
    const parsed = SessionSchema.parse(session);
    await mkdir(this.sessionDir(parsed.session_id), { recursive: true });
    await writeJson(path.join(this.sessionDir(parsed.session_id), "session.json"), parsed);
  }

  async loadSession(sessionId: string): Promise<SessionRecord> {
    return SessionSchema.parse(await readJson(path.join(this.sessionDir(sessionId), "session.json")));
  }

  async writeExecutionWorkflow(workflow: ExecutionWorkflowRecord): Promise<void> {
    const parsed = ExecutionWorkflowSchema.parse(workflow);
    await writeJson(path.join(this.sessionDir(parsed.session_id), "execution-workflow.json"), parsed);
  }

  async loadExecutionWorkflow(sessionId: string): Promise<ExecutionWorkflowRecord> {
    return ExecutionWorkflowSchema.parse(await readJson(path.join(this.sessionDir(sessionId), "execution-workflow.json")));
  }

  async writeProductDevQaWorkflow(workflow: ProductDevQaWorkflowRunRecord): Promise<void> {
    const parsed = ProductDevQaWorkflowRunSchema.parse(workflow);
    await writeJson(path.join(this.sessionDir(parsed.session_id), "workflow-run.json"), parsed);
  }

  async loadProductDevQaWorkflow(sessionId: string): Promise<ProductDevQaWorkflowRunRecord> {
    return ProductDevQaWorkflowRunSchema.parse(await readJson(path.join(this.sessionDir(sessionId), "workflow-run.json")));
  }

  async updateExecutionWorkflow(
    sessionId: string,
    updater: (workflow: ExecutionWorkflowRecord) => ExecutionWorkflowRecord,
  ): Promise<ExecutionWorkflowRecord> {
    const updated = ExecutionWorkflowSchema.parse(updater(await this.loadExecutionWorkflow(sessionId)));
    await this.writeExecutionWorkflow(updated);
    const previousDelivery = await this.loadDeliveryWorkflow(sessionId).catch(() => undefined);
    const delivery = projectDeliveryWorkflow(updated, previousDelivery);
    await this.writeDeliveryWorkflow(delivery);
    const session = await this.loadSession(sessionId);
    const updatedSession = {
      ...session,
      delivery_status: delivery.status,
      execution_status: updated.status,
      status: delivery.status,
      current_phase: delivery.current_phase,
      current_stage: updated.current_stage,
      updated_at: updated.updated_at,
    };
    await this.writeSession(updatedSession);
    await this.upsertSessionIndex(updatedSession);
    return updated;
  }

  async writeDeliveryWorkflow(workflow: DeliveryWorkflowRecord): Promise<void> {
    const parsed = DeliveryWorkflowSchema.parse(workflow);
    await writeJson(path.join(this.sessionDir(parsed.session_id), "delivery-workflow.json"), parsed);
  }

  async loadDeliveryWorkflow(sessionId: string): Promise<DeliveryWorkflowRecord> {
    return DeliveryWorkflowSchema.parse(await readJson(path.join(this.sessionDir(sessionId), "delivery-workflow.json")));
  }

  async appendEvent(event: RuntimeEvent): Promise<void> {
    const parsed = RuntimeEventSchema.parse(event);
    await appendJsonl(path.join(this.sessionDir(parsed.session_id), "events.jsonl"), parsed);
  }

  async appendToolCall(call: ToolCallRecord): Promise<void> {
    const parsed = ToolCallSchema.parse(call);
    await appendJsonl(path.join(this.sessionDir(parsed.session_id), "tool-calls.jsonl"), parsed);
  }

  async createAgentRun(args: {
    sessionId: string;
    role: AgentRole;
    runner: AgentRunRecord["runner"];
    input: string;
    metadata?: Record<string, unknown>;
  }): Promise<AgentRunRecord> {
    const record: AgentRunRecord = {
      schema_version: 1,
      session_id: args.sessionId,
      agent_run_id: createRunId(args.role),
      role: args.role,
      status: "running",
      runner: args.runner,
      input: args.input,
      output: "",
      started_at: nowIso(),
      last_heartbeat_at: undefined,
      heartbeat_count: 0,
      error: "",
      metadata: args.metadata ?? {},
    };
    await this.writeAgentRun(record);
    await this.appendEvent({
      at: record.started_at,
      session_id: args.sessionId,
      kind: "agent_run_started",
      role: args.role,
      status: "running",
      message: `${args.role} started.`,
      details: { agent_run_id: record.agent_run_id, runner: record.runner },
    });
    return record;
  }

  async completeAgentRun(record: AgentRunRecord, patch: Partial<AgentRunRecord>): Promise<AgentRunRecord> {
    const current = await this.readAgentRun(record.session_id, record.agent_run_id).catch(() => record);
    const completedAt = patch.completed_at ?? nowIso();
    const completed = AgentRunSchema.parse({
      ...current,
      ...patch,
      status: patch.status ?? "completed",
      completed_at: completedAt,
      last_heartbeat_at: patch.last_heartbeat_at ?? current.last_heartbeat_at ?? completedAt,
      heartbeat_count: patch.heartbeat_count ?? current.heartbeat_count,
      metadata: {
        ...current.metadata,
        ...patch.metadata,
      },
    });
    await this.writeAgentRun(completed);
    await this.appendEvent({
      at: completed.completed_at ?? nowIso(),
      session_id: completed.session_id,
      kind: "agent_run_completed",
      role: completed.role,
      status: completed.status,
      message: `${completed.role} ${completed.status}.`,
      details: { agent_run_id: completed.agent_run_id, error: completed.error },
    });
    return completed;
  }

  async heartbeatAgentRun(
    record: AgentRunRecord,
    details: Record<string, unknown> = {},
  ): Promise<AgentRunRecord> {
    const existing = await this.readAgentRun(record.session_id, record.agent_run_id).catch(() => record);
    if (existing.status !== "running") {
      return existing;
    }
    const heartbeatAt = nowIso();
    const updated = AgentRunSchema.parse({
      ...existing,
      last_heartbeat_at: heartbeatAt,
      heartbeat_count: existing.heartbeat_count + 1,
      metadata: {
        ...existing.metadata,
        last_heartbeat_at: heartbeatAt,
      },
    });
    await this.writeAgentRun(updated);
    await this.updateExecutionWorkflow(updated.session_id, (workflow) => ({
      ...workflow,
      updated_at: heartbeatAt,
    }));
    await this.appendEvent({
      at: heartbeatAt,
      session_id: updated.session_id,
      kind: "agent_run_heartbeat",
      role: updated.role,
      status: "running",
      message: `${updated.role} still running.`,
      details: { agent_run_id: updated.agent_run_id, heartbeat_count: updated.heartbeat_count, ...details },
    });
    return updated;
  }

  async writeAgentRun(record: AgentRunRecord): Promise<void> {
    const parsed = AgentRunSchema.parse(record);
    await mkdir(this.agentsDir(parsed.session_id), { recursive: true });
    await writeJson(path.join(this.agentsDir(parsed.session_id), `${parsed.agent_run_id}.json`), parsed);
  }

  async readAgentRun(sessionId: string, agentRunId: string): Promise<AgentRunRecord> {
    return AgentRunSchema.parse(await readJson(path.join(this.agentsDir(sessionId), `${agentRunId}.json`)));
  }

  async listSessions(): Promise<SessionRecord[]> {
    await this.ensureLayout();
    const root = path.join(this.stateRoot, "sessions");
    const entries = await readdir(root, { withFileTypes: true });
    const sessions: SessionRecord[] = [];
    for (const entry of entries) {
      if (!entry.isDirectory()) {
        continue;
      }
      const file = path.join(root, entry.name, "session.json");
      if (!existsSync(file)) {
        continue;
      }
      sessions.push(SessionSchema.parse(await readJson(file)));
    }
    return sessions.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }

  async readEvents(sessionId: string): Promise<RuntimeEvent[]> {
    return readJsonl(path.join(this.sessionDir(sessionId), "events.jsonl"), RuntimeEventSchema.parse);
  }

  async readToolCalls(sessionId: string): Promise<ToolCallRecord[]> {
    return readJsonl(path.join(this.sessionDir(sessionId), "tool-calls.jsonl"), ToolCallSchema.parse);
  }

  async listAgentRuns(sessionId: string): Promise<AgentRunRecord[]> {
    const root = this.agentsDir(sessionId);
    if (!existsSync(root)) {
      return [];
    }
    const entries = await readdir(root, { withFileTypes: true });
    const runs: AgentRunRecord[] = [];
    for (const entry of entries) {
      if (!entry.isFile() || !entry.name.endsWith(".json")) {
        continue;
      }
      runs.push(AgentRunSchema.parse(await readJson(path.join(root, entry.name))));
    }
    return runs.sort((a, b) => a.started_at.localeCompare(b.started_at));
  }

  async recordPromptTrace(args: {
    sessionId: string;
    role: AgentRole;
    prompt: string;
    source: string;
    runner?: AgentRunRecord["runner"];
    metadata?: Record<string, unknown>;
  }): Promise<PromptTraceRecord> {
    await this.ensureLayout();
    const createdAt = nowIso();
    const promptId = createPromptTraceId(args.role, args.prompt);
    const dir = this.promptTraceDir(promptId);
    const promptPath = path.join(dir, "prompt.md");
    await mkdir(dir, { recursive: true });
    await writeFile(promptPath, args.prompt);
    const record = PromptTraceSchema.parse({
      schema_version: 1,
      prompt_id: promptId,
      session_id: args.sessionId,
      role: args.role,
      kind: "stage",
      runner: args.runner,
      source: args.source,
      path: promptPath,
      sha256: sha256Hex(args.prompt),
      bytes: Buffer.byteLength(args.prompt, "utf8"),
      created_at: createdAt,
      metadata: args.metadata ?? {},
    });
    await writeJson(path.join(dir, "meta.json"), record);
    await appendJsonl(path.join(this.promptTracesDir(), "index.jsonl"), record);
    const session = await this.loadSession(args.sessionId);
    await this.writeSession({
      ...session,
      prompt_trace_ids: [...new Set([...session.prompt_trace_ids, promptId])],
      updated_at: createdAt,
    });
    await this.appendEvent({
      at: createdAt,
      session_id: args.sessionId,
      kind: "prompt_trace_recorded",
      role: args.role,
      status: "recorded",
      message: `${args.role} prompt trace recorded.`,
      details: { prompt_id: promptId, path: promptPath },
    });
    return record;
  }

  async readPromptTraces(sessionId: string): Promise<PromptTraceRecord[]> {
    const records = await readJsonl(path.join(this.promptTracesDir(), "index.jsonl"), PromptTraceSchema.parse);
    return records.filter((record) => record.session_id === sessionId);
  }

  async writeArtifact(args: {
    sessionId: string;
    role: AgentRole;
    name: string;
    content: string;
    metadata?: Record<string, unknown>;
  }): Promise<ArtifactRecord> {
    const createdAt = nowIso();
    const safeName = path.basename(args.name);
    const filePath = path.join(this.artifactsDir(args.sessionId), safeName);
    await mkdir(path.dirname(filePath), { recursive: true });
    await writeFile(filePath, args.content);
    const record = ArtifactRecordSchema.parse({
      schema_version: 1,
      artifact_id: createArtifactId(args.role, safeName),
      session_id: args.sessionId,
      role: args.role,
      name: safeName,
      path: filePath,
      bytes: Buffer.byteLength(args.content, "utf8"),
      created_at: createdAt,
      metadata: args.metadata ?? {},
    });
    await appendJsonl(path.join(this.artifactsDir(args.sessionId), "index.jsonl"), record);
    await this.appendEvent({
      at: createdAt,
      session_id: args.sessionId,
      kind: "artifact_written",
      role: args.role,
      status: "written",
      message: `${args.role} wrote ${safeName}.`,
      details: { artifact_id: record.artifact_id, path: filePath },
    });
    return record;
  }

  async readArtifacts(sessionId: string): Promise<ArtifactRecord[]> {
    return readJsonl(path.join(this.artifactsDir(sessionId), "index.jsonl"), ArtifactRecordSchema.parse);
  }

  async readArtifactContent(sessionId: string, name: string): Promise<{ artifact: ArtifactRecord; content: string }> {
    const artifact = (await this.readArtifacts(sessionId)).find((item) => item.name === name);
    if (!artifact) {
      throw new Error(`Artifact not found: ${name}`);
    }
    return { artifact, content: await readFile(artifact.path, "utf8") };
  }

  async readPromptContent(promptId: string): Promise<{ prompt: PromptTraceRecord; content: string }> {
    const prompt = PromptTraceSchema.parse(await readJson(path.join(this.promptTraceDir(promptId), "meta.json")));
    return { prompt, content: await readFile(prompt.path, "utf8") };
  }

  async loadConfig(): Promise<RuntimeConfig> {
    if (!existsSync(this.configPath())) {
      return RuntimeConfigSchema.parse({ schema_version: 1 });
    }
    return RuntimeConfigSchema.parse(await readJson(this.configPath()));
  }

  async writeConfig(config: RuntimeConfig): Promise<RuntimeConfig> {
    const parsed = RuntimeConfigSchema.parse(config);
    await writeJson(this.configPath(), parsed);
    return parsed;
  }

  async ensureConfig(config?: Partial<RuntimeConfig>): Promise<RuntimeConfig> {
    const current = await this.loadConfig();
    return this.writeConfig(RuntimeConfigSchema.parse({ ...current, ...config, schema_version: 1 }));
  }

  async loadSessionIndex(): Promise<SessionIndex> {
    if (!existsSync(this.sessionIndexPath())) {
      return { schema_version: 1, sessions: [] };
    }
    return SessionIndexSchema.parse(await readJson(this.sessionIndexPath()));
  }

  async writeSessionIndex(index: SessionIndex): Promise<void> {
    await writeJson(this.sessionIndexPath(), SessionIndexSchema.parse(index));
  }

  async upsertSessionIndex(session: SessionRecord): Promise<void> {
    const index = await this.loadSessionIndex();
    const createdAt = session.created_at;
    const worktree = session.worktree;
    const entry: SessionIndexEntry = {
      session_id: session.session_id,
      request: session.request,
      workflow_id: session.workflow_id ?? "",
      delivery_status: session.delivery_status,
      execution_status: session.execution_status,
      status: session.status,
      current_phase: session.current_phase,
      current_stage: session.current_stage,
      profile: session.profile,
      project_root: session.project_root || session.repo_root,
      worktree_path: session.repo_root,
      state_root: session.state_root,
      branch: worktree?.branch ?? "",
      base_ref: worktree?.base_ref ?? "",
      base_commit: worktree?.base_commit ?? "",
      created_at: createdAt,
      updated_at: session.updated_at,
    };
    const existing = index.sessions.findIndex((item) => item.session_id === session.session_id);
    if (existing >= 0) {
      index.sessions[existing] = { ...index.sessions[existing], ...entry, created_at: index.sessions[existing].created_at };
    } else {
      index.sessions.push(entry);
    }
    index.sessions.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    await this.writeSessionIndex(index);
  }

  async latestSession(): Promise<SessionRecord | undefined> {
    return (await this.listSessions())[0];
  }
}

export async function writeJson(file: string, value: unknown): Promise<void> {
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, `${JSON.stringify(value, null, 2)}\n`);
}

export async function readJson(file: string): Promise<unknown> {
  return JSON.parse(await readFile(file, "utf8"));
}

async function appendJsonl(file: string, value: unknown): Promise<void> {
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, `${JSON.stringify(value)}\n`, { flag: "a" });
}

async function readJsonl<T>(file: string, parser: (value: unknown) => T): Promise<T[]> {
  if (!existsSync(file)) {
    return [];
  }
  const text = await readFile(file, "utf8");
  return text
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => parser(JSON.parse(line)));
}
