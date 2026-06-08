import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import {
  type ArtifactRecord,
  ArtifactRecordSchema,
  type AgentRole,
  type AgentRunRecord,
  AgentRunSchema,
  type PromptTraceRecord,
  PromptTraceSchema,
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
  type WorkflowRecord,
  WorkflowSchema,
  nowIso,
} from "./schema.js";
import { createArtifactId, createPromptTraceId, createRunId, createSessionId, sha256Hex } from "./ids.js";

export type CreateSessionOptions = {
  request: string;
  profile: RuntimeProfile;
  repoRoot: string;
  projectRoot?: string;
  stateRoot?: string;
  worktree?: WorktreeRecord;
  source?: SessionRecord["source"];
  migration?: SessionRecord["migration"];
};

// RuntimeStore：封装 .agt 状态目录内所有 session、workflow、trace 和 artifact 的读写。
// RuntimeStore: wraps all reads and writes for sessions, workflows, traces, and artifacts under .agt.
export class RuntimeStore {
  readonly stateRoot: string;

  // 构造 store，并把传入的 stateRoot 固定为绝对路径。
  // Constructs a store and normalizes stateRoot to an absolute path.
  constructor(stateRoot: string) {
    this.stateRoot = path.resolve(stateRoot);
  }

  // 返回指定 session 的根目录路径。
  // Returns the root directory path for a session.
  sessionDir(sessionId: string): string {
    return path.join(this.stateRoot, "sessions", sessionId);
  }

  // 返回指定 session 的 agent run 记录目录。
  // Returns the agent-run record directory for a session.
  agentsDir(sessionId: string): string {
    return path.join(this.sessionDir(sessionId), "agents");
  }

  // 返回指定 session 的 artifact 目录。
  // Returns the artifact directory for a session.
  artifactsDir(sessionId: string): string {
    return path.join(this.sessionDir(sessionId), "artifacts");
  }

  // 返回全局 prompt trace 目录。
  // Returns the global prompt-trace directory.
  promptTracesDir(): string {
    return path.join(this.stateRoot, "prompt_traces");
  }

  // 返回单个 prompt trace 的目录。
  // Returns the directory for one prompt trace.
  promptTraceDir(promptId: string): string {
    return path.join(this.promptTracesDir(), promptId);
  }

  // 返回 runtime 配置文件路径。
  // Returns the runtime config file path.
  configPath(): string {
    return path.join(this.stateRoot, "config.json");
  }

  // 返回跨 worktree session 索引文件路径。
  // Returns the cross-worktree session index file path.
  sessionIndexPath(): string {
    return path.join(this.stateRoot, "session-index.json");
  }

  // 确保 stateRoot 下的核心目录存在。
  // Ensures the core directories under stateRoot exist.
  async ensureLayout(): Promise<void> {
    await mkdir(path.join(this.stateRoot, "sessions"), { recursive: true });
    await mkdir(this.promptTracesDir(), { recursive: true });
  }

  // 创建新 session，并初始化 session.json、workflow.json、事件和索引。
  // Creates a new session and initializes session.json, workflow.json, events, and index entries.
  async createSession(options: CreateSessionOptions): Promise<SessionRecord> {
    await this.ensureLayout();
    const sessionId = createSessionId(options.request);
    const createdAt = nowIso();
    const session: SessionRecord = {
      schema_version: 1,
      session_id: sessionId,
      request: options.request,
      profile: options.profile,
      status: "in_progress",
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
    await this.writeWorkflow({
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

  // 写入 session.json，并通过 schema 校验结构。
  // Writes session.json after validating it with the schema.
  async writeSession(session: SessionRecord): Promise<void> {
    const parsed = SessionSchema.parse(session);
    await mkdir(this.sessionDir(parsed.session_id), { recursive: true });
    await writeJson(path.join(this.sessionDir(parsed.session_id), "session.json"), parsed);
  }

  // 读取并校验指定 session 的 session.json。
  // Reads and validates session.json for a session.
  async loadSession(sessionId: string): Promise<SessionRecord> {
    return SessionSchema.parse(await readJson(path.join(this.sessionDir(sessionId), "session.json")));
  }

  // 写入 workflow.json，并通过 schema 校验状态机记录。
  // Writes workflow.json after validating the workflow state record.
  async writeWorkflow(workflow: WorkflowRecord): Promise<void> {
    const parsed = WorkflowSchema.parse(workflow);
    await writeJson(path.join(this.sessionDir(parsed.session_id), "workflow.json"), parsed);
  }

  // 读取并校验指定 session 的 workflow.json。
  // Reads and validates workflow.json for a session.
  async loadWorkflow(sessionId: string): Promise<WorkflowRecord> {
    return WorkflowSchema.parse(await readJson(path.join(this.sessionDir(sessionId), "workflow.json")));
  }

  // 原子式更新 workflow，并同步 session 摘要和 session-index。
  // Updates workflow state and mirrors the summary into session.json and session-index.
  async updateWorkflow(sessionId: string, updater: (workflow: WorkflowRecord) => WorkflowRecord): Promise<WorkflowRecord> {
    const updated = WorkflowSchema.parse(updater(await this.loadWorkflow(sessionId)));
    await this.writeWorkflow(updated);
    const session = await this.loadSession(sessionId);
    await this.writeSession({
      ...session,
      status: updated.status,
      current_stage: updated.current_stage,
      updated_at: updated.updated_at,
    });
    await this.upsertSessionIndex({
      ...session,
      status: updated.status,
      current_stage: updated.current_stage,
      updated_at: updated.updated_at,
    });
    return updated;
  }

  // 追加一条 runtime event 到 events.jsonl。
  // Appends one runtime event to events.jsonl.
  async appendEvent(event: RuntimeEvent): Promise<void> {
    const parsed = RuntimeEventSchema.parse(event);
    await appendJsonl(path.join(this.sessionDir(parsed.session_id), "events.jsonl"), parsed);
  }

  // 追加一条 tool call 记录到 tool-calls.jsonl。
  // Appends one tool-call record to tool-calls.jsonl.
  async appendToolCall(call: ToolCallRecord): Promise<void> {
    const parsed = ToolCallSchema.parse(call);
    await appendJsonl(path.join(this.sessionDir(parsed.session_id), "tool-calls.jsonl"), parsed);
  }

  // 创建 agent run 记录，并写入 agent_run_started 事件。
  // Creates an agent-run record and writes an agent_run_started event.
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

  // 完成 agent run，并写入 agent_run_completed 事件。
  // Completes an agent run and writes an agent_run_completed event.
  async completeAgentRun(record: AgentRunRecord, patch: Partial<AgentRunRecord>): Promise<AgentRunRecord> {
    const completed = AgentRunSchema.parse({
      ...record,
      ...patch,
      status: patch.status ?? "completed",
      completed_at: patch.completed_at ?? nowIso(),
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

  // 写入单个 agent run 的 JSON 记录。
  // Writes one agent-run JSON record.
  async writeAgentRun(record: AgentRunRecord): Promise<void> {
    const parsed = AgentRunSchema.parse(record);
    await mkdir(this.agentsDir(parsed.session_id), { recursive: true });
    await writeJson(path.join(this.agentsDir(parsed.session_id), `${parsed.agent_run_id}.json`), parsed);
  }

  // 列出所有 session，并按更新时间倒序返回。
  // Lists all sessions sorted by updated_at descending.
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

  // 读取指定 session 的事件流。
  // Reads the event stream for a session.
  async readEvents(sessionId: string): Promise<RuntimeEvent[]> {
    return readJsonl(path.join(this.sessionDir(sessionId), "events.jsonl"), RuntimeEventSchema.parse);
  }

  // 读取指定 session 的 tool call 流。
  // Reads the tool-call stream for a session.
  async readToolCalls(sessionId: string): Promise<ToolCallRecord[]> {
    return readJsonl(path.join(this.sessionDir(sessionId), "tool-calls.jsonl"), ToolCallSchema.parse);
  }

  // 列出指定 session 的所有 agent run。
  // Lists all agent runs for a session.
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

  // 记录一个阶段实际发送给 runner 的 prompt，并更新 prompt trace 索引。
  // Records the actual prompt sent to a runner for a stage and updates the prompt-trace index.
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

  // 读取属于指定 session 的 prompt trace 元数据。
  // Reads prompt-trace metadata that belongs to a session.
  async readPromptTraces(sessionId: string): Promise<PromptTraceRecord[]> {
    const records = await readJsonl(path.join(this.promptTracesDir(), "index.jsonl"), PromptTraceSchema.parse);
    return records.filter((record) => record.session_id === sessionId);
  }

  // 写入阶段产物，并把产物元数据追加到 artifacts/index.jsonl。
  // Writes a stage artifact and appends its metadata to artifacts/index.jsonl.
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

  // 读取指定 session 的 artifact 索引。
  // Reads the artifact index for a session.
  async readArtifacts(sessionId: string): Promise<ArtifactRecord[]> {
    return readJsonl(path.join(this.artifactsDir(sessionId), "index.jsonl"), ArtifactRecordSchema.parse);
  }

  // 读取指定 artifact 的元数据和正文内容。
  // Reads metadata and text content for one artifact.
  async readArtifactContent(sessionId: string, name: string): Promise<{ artifact: ArtifactRecord; content: string }> {
    const artifact = (await this.readArtifacts(sessionId)).find((item) => item.name === name);
    if (!artifact) {
      throw new Error(`Artifact not found: ${name}`);
    }
    return { artifact, content: await readFile(artifact.path, "utf8") };
  }

  // 读取指定 prompt trace 的元数据和 prompt 正文。
  // Reads metadata and prompt text for one prompt trace.
  async readPromptContent(promptId: string): Promise<{ prompt: PromptTraceRecord; content: string }> {
    const prompt = PromptTraceSchema.parse(await readJson(path.join(this.promptTraceDir(promptId), "meta.json")));
    return { prompt, content: await readFile(prompt.path, "utf8") };
  }

  // 读取 runtime 配置；缺省时返回 schema 默认配置。
  // Loads runtime config, returning schema defaults when config is missing.
  async loadConfig(): Promise<RuntimeConfig> {
    if (!existsSync(this.configPath())) {
      return RuntimeConfigSchema.parse({ schema_version: 1 });
    }
    return RuntimeConfigSchema.parse(await readJson(this.configPath()));
  }

  // 写入 runtime 配置，并返回校验后的配置。
  // Writes runtime config and returns the validated config.
  async writeConfig(config: RuntimeConfig): Promise<RuntimeConfig> {
    const parsed = RuntimeConfigSchema.parse(config);
    await writeJson(this.configPath(), parsed);
    return parsed;
  }

  // 合并现有配置和传入配置，确保 config.json 存在。
  // Merges existing config with overrides and ensures config.json exists.
  async ensureConfig(config?: Partial<RuntimeConfig>): Promise<RuntimeConfig> {
    const current = await this.loadConfig();
    return this.writeConfig(RuntimeConfigSchema.parse({ ...current, ...config, schema_version: 1 }));
  }

  // 读取主 session-index；缺省时返回空索引。
  // Loads the root session-index, returning an empty index when missing.
  async loadSessionIndex(): Promise<SessionIndex> {
    if (!existsSync(this.sessionIndexPath())) {
      return { schema_version: 1, sessions: [] };
    }
    return SessionIndexSchema.parse(await readJson(this.sessionIndexPath()));
  }

  // 写入跨 worktree 的 session-index。
  // Writes the cross-worktree session-index.
  async writeSessionIndex(index: SessionIndex): Promise<void> {
    await writeJson(this.sessionIndexPath(), SessionIndexSchema.parse(index));
  }

  // 插入或更新 session-index 中的 session 摘要。
  // Inserts or updates a session summary in session-index.
  async upsertSessionIndex(session: SessionRecord): Promise<void> {
    const index = await this.loadSessionIndex();
    const createdAt = session.created_at;
    const worktree = session.worktree;
    const entry: SessionIndexEntry = {
      session_id: session.session_id,
      request: session.request,
      status: session.status,
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

  // 返回最近更新的 session。
  // Returns the most recently updated session.
  async latestSession(): Promise<SessionRecord | undefined> {
    return (await this.listSessions())[0];
  }
}

// 写入格式化 JSON，并自动创建父目录。
// Writes formatted JSON and creates the parent directory automatically.
export async function writeJson(file: string, value: unknown): Promise<void> {
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, `${JSON.stringify(value, null, 2)}\n`);
}

// 读取 JSON 文件并解析成 unknown。
// Reads and parses a JSON file as unknown.
export async function readJson(file: string): Promise<unknown> {
  return JSON.parse(await readFile(file, "utf8"));
}

// 向 JSONL 文件追加一行结构化记录。
// Appends one structured record to a JSONL file.
async function appendJsonl(file: string, value: unknown): Promise<void> {
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, `${JSON.stringify(value)}\n`, { flag: "a" });
}

// 读取 JSONL 文件，并用传入 parser 校验每一行。
// Reads a JSONL file and validates each line with the provided parser.
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
