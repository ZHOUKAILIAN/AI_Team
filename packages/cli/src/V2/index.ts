#!/usr/bin/env node
import { Command } from "commander";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  createTaskWorktree,
  initRuntime,
  isProductDevQaSession,
  PRODUCT_DEV_QA_WORKFLOW_ID,
  recordProductDevQaHumanDecision,
  readSessionStatus,
  runProductDevQaWorkflow,
  RuntimeStore,
  compareTimestamps,
  type RequestSourceRecord,
  type RunResult,
  type RuntimeConfig,
  type SessionStatusSnapshot,
} from "@agent-team-runtime/runtime/V2";
import { runServer } from "@agent-team-runtime/server";

const VERSION = "0.3.0-alpha.2";
const DEFAULT_STATE_DIR = ".agt2";

const program = new Command();

program
  .name("agt2")
  .description("Agent Team Runtime V2 CLI")
  .version(VERSION);

program
  .command("init")
  .option("--repo-root <path>", "repository root", process.cwd())
  .option("--state-root <path>", "state root; defaults to <repo>/.agt2")
  .option("--default-model <model>", "OpenAI model")
  .option("--task-worktree", "enable isolated task worktrees by default")
  .action(async (options: InitOptions) => {
    const repoRoot = path.resolve(options.repoRoot);
    const stateRoot = options.stateRoot ? path.resolve(options.stateRoot) : path.join(repoRoot, DEFAULT_STATE_DIR);
    const config: Partial<RuntimeConfig> = {
      state_root: options.stateRoot ?? DEFAULT_STATE_DIR,
    };
    if (options.defaultModel) {
      config.default_model = options.defaultModel;
    }
    if (options.taskWorktree) {
      config.task_worktree = {
        enabled: true,
        base_ref_candidates: ["origin/test", "origin/main", "test", "main"],
        branch_prefix: "feature/",
        worktree_root: ".worktrees",
        slug_max_length: 40,
      };
    }
    const result = await initRuntime({ repoRoot, stateRoot, config });
    console.log(`state_root: ${result.stateRoot}`);
    console.log(`config_path: ${result.configPath}`);
  });

program
  .command("deliver")
  .argument("[message...]", "task request")
  .description("start a product-dev-qa delivery run with an isolated task worktree by default")
  .option("--repo-root <path>", "repository root", process.cwd())
  .option("--state-root <path>", "state root; defaults to <repo>/.agt2")
  .option("--from <path>", "read request context from a file")
  .option("--from-dir <path>", "read request context from all files under a directory")
  .option("--no-task-worktree", "run in the current repository instead of an isolated task worktree")
  .action(async (messageParts: string[], options: DeliverOptions) => {
    const result = await startProductDevQaDelivery(messageParts, options, true);
    printResult(result);
  });

program
  .command("run")
  .argument("[message...]", "task request")
  .description("alias for deliver; starts product-dev-qa")
  .option("--repo-root <path>", "repository root", process.cwd())
  .option("--state-root <path>", "state root; defaults to <repo>/.agt2")
  .option("--from <path>", "read request context from a file")
  .option("--from-dir <path>", "read request context from all files under a directory")
  .option("--task-worktree", "create an isolated git worktree for this run")
  .option("--no-task-worktree", "disable configured task worktree for this run")
  .action(async (messageParts: string[], options: DeliverOptions) => {
    const result = await startProductDevQaDelivery(messageParts, options, false);
    printResult(result);
  });

program
  .command("decision")
  .argument("<session-id>", "session id")
  .requiredOption("--decision <decision>", "go | no-go")
  .option("--state-root <path>", "state root", path.join(process.cwd(), DEFAULT_STATE_DIR))
  .action(async (sessionId: string, options: DecisionOptions) => {
    const sourceStateRoot = path.resolve(options.stateRoot);
    const target = await resolveSessionTarget(sourceStateRoot, sessionId);
    await assertProductDevQaSession(target);
    const result = await recordProductDevQaHumanDecision({
      stateRoot: target.stateRoot,
      sessionId: target.sessionId,
      decision: parseProductDevQaDecision(options.decision),
    });
    await mirrorSessionIndex(sourceStateRoot, target.stateRoot, result.session_id);
    printResult(result);
  });

program
  .command("approve")
  .argument("[session-id]", "session id; defaults to latest session")
  .description("approve the current product-dev-qa human gate")
  .option("--state-root <path>", "state root", path.join(process.cwd(), DEFAULT_STATE_DIR))
  .action(async (sessionId: string | undefined, options: ApproveOptions) => {
    const result = await approveProductDevQaGate(sessionId, options);
    printResult(result);
  });

program
  .command("status")
  .argument("[session-id]", "session id")
  .option("--state-root <path>", "state root", path.join(process.cwd(), DEFAULT_STATE_DIR))
  .option("--watch", "poll status until the session leaves running/in_progress")
  .option("--interval <seconds>", "poll interval for --watch", "5")
  .option("--stalled-after <seconds>", "mark running agent runs as stalled after this many seconds without heartbeat", "120")
  .option("--json", "print JSON status")
  .action(async (sessionId: string | undefined, options: StatusOptions) => {
    const sourceStateRoot = path.resolve(options.stateRoot);
    const target = sessionId
      ? await resolveSessionTarget(sourceStateRoot, sessionId)
      : await resolveLatestSessionTarget(sourceStateRoot);
    await assertProductDevQaSession(target);
    const store = new RuntimeStore(target.stateRoot);
    const intervalMs = parsePositiveSeconds(options.interval, "--interval") * 1000;
    const stalledAfterMs = parsePositiveSeconds(options.stalledAfter, "--stalled-after") * 1000;
    await printStatusOnce(store, target.sessionId, { ...options, stalledAfterMs });
    if (!options.watch) {
      return;
    }
    while (true) {
      await sleep(intervalMs);
      const snapshot = await printStatusOnce(store, target.sessionId, { ...options, stalledAfterMs });
      if (!isWatchableRuntimeStatus(snapshot.runtime_status)) {
        break;
      }
    }
  });

program
  .command("inspect")
  .argument("<session-id>", "session id")
  .option("--state-root <path>", "state root", path.join(process.cwd(), DEFAULT_STATE_DIR))
  .action(async (sessionId: string, options: { stateRoot: string }) => {
    const target = await resolveSessionTarget(path.resolve(options.stateRoot), sessionId);
    await assertProductDevQaSession(target);
    const store = new RuntimeStore(target.stateRoot);
    const session = await store.loadSession(target.sessionId);
    const deliveryWorkflow = await store.loadDeliveryWorkflow(target.sessionId);
    const executionWorkflow = await store.loadExecutionWorkflow(target.sessionId);
    const productDevQaWorkflow = await store.loadProductDevQaWorkflow(target.sessionId);
    const toolCalls = await store.readToolCalls(target.sessionId);
    const prompts = await store.readPromptTraces(target.sessionId);
    const artifacts = await store.readArtifacts(target.sessionId);
    const agentRuns = await store.listAgentRuns(target.sessionId);
    console.log(JSON.stringify({
      session,
      workflow_run: productDevQaWorkflow,
      delivery_workflow: deliveryWorkflow,
      execution_workflow: executionWorkflow,
      prompts,
      artifacts,
      agent_runs: agentRuns,
      tool_calls: toolCalls,
    }, null, 2));
  });

program
  .command("server")
  .option("--state-root <path>", "state root", path.join(process.cwd(), DEFAULT_STATE_DIR))
  .option("--host <host>", "host", "127.0.0.1")
  .option("--port <port>", "port", "8765")
  .action(async (options: { stateRoot: string; host: string; port: string }) => {
    const url = await runServer({
      stateRoot: path.resolve(options.stateRoot),
      host: options.host,
      port: Number(options.port),
    });
    console.log(`server_url: ${url}`);
  });

program.parseAsync().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});

type InitOptions = {
  repoRoot: string;
  stateRoot?: string;
  defaultModel?: string;
  taskWorktree?: boolean;
};

type DeliverOptions = {
  repoRoot: string;
  stateRoot?: string;
  from?: string;
  fromDir?: string;
  taskWorktree?: boolean;
};

type DecisionOptions = {
  decision: string;
  stateRoot: string;
};

type ApproveOptions = {
  stateRoot: string;
};

type StatusOptions = {
  stateRoot: string;
  watch?: boolean;
  interval: string;
  stalledAfter: string;
  json?: boolean;
};

type SessionTarget = {
  sessionId: string;
  repoRoot: string;
  stateRoot: string;
  workflowId: string;
};

type RequestInput = { request: string; sources: RequestSourceRecord[] };

type SessionMeta = {
  session_id: string;
  request: string;
  workflow_id: string;
  delivery_status: "in_progress" | "waiting_human" | "blocked" | "done";
  execution_status: "in_progress" | "waiting_human" | "blocked" | "done";
  status: "in_progress" | "waiting_human" | "blocked" | "done";
  current_phase: "requirement" | "development" | "verification" | "handoff";
  current_stage: string;
  project_root: string;
  repo_root: string;
  state_root: string;
  created_at: string;
  updated_at: string;
  worktree?: {
    branch?: string;
    base_ref?: string;
    base_commit?: string;
  };
};

type SessionIndexEntry = {
  session_id: string;
  request: string;
  workflow_id: string;
  delivery_status: SessionMeta["delivery_status"];
  execution_status: SessionMeta["execution_status"];
  status: SessionMeta["status"];
  current_phase: SessionMeta["current_phase"];
  current_stage: string;
  project_root: string;
  worktree_path: string;
  state_root: string;
  branch: string;
  base_ref: string;
  base_commit: string;
  updated_at: string;
  created_at: string;
};

function parseProductDevQaDecision(value: string): "go" | "no-go" {
  if (value === "go" || value === "no-go") {
    return value;
  }
  throw new Error(`${PRODUCT_DEV_QA_WORKFLOW_ID} supports only go | no-go decisions.`);
}

async function readRequestInput(
  messageParts: string[],
  options: Pick<DeliverOptions, "from" | "fromDir">,
): Promise<RequestInput> {
  const message = messageParts.join(" ").trim();
  const sourceBlocks: string[] = [];
  const sources: RequestSourceRecord[] = [];
  if (options.from) {
    const resolved = path.resolve(options.from);
    const content = await readFile(resolved, "utf8");
    sourceBlocks.push(renderSourceBlock(resolved, content));
    sources.push(sourceRecord("file", resolved, content));
  }
  if (options.fromDir) {
    const root = path.resolve(options.fromDir);
    const files = await collectRequestFiles(root);
    for (const file of files) {
      const content = await readFile(file, "utf8");
      sourceBlocks.push(renderSourceBlock(path.relative(root, file) || file, content));
      sources.push(sourceRecord("directory_file", file, content));
    }
  }
  return {
    request: [message, ...sourceBlocks].filter(Boolean).join("\n\n"),
    sources,
  };
}

async function collectRequestFiles(root: string): Promise<string[]> {
  const rootStat = await stat(root);
  if (rootStat.isFile()) {
    return [root];
  }
  if (!rootStat.isDirectory()) {
    throw new Error(`--from-dir is not a directory: ${root}`);
  }
  const ignored = new Set([".git", ".agt", ".agt2", "node_modules", "dist", "build"]);
  const files: string[] = [];
  async function visit(dir: string): Promise<void> {
    const entries = await readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (ignored.has(entry.name)) {
        continue;
      }
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        await visit(fullPath);
      } else if (entry.isFile()) {
        files.push(fullPath);
      }
    }
  }
  await visit(root);
  return files.sort();
}

function renderSourceBlock(label: string, content: string): string {
  return [`# Source: ${label}`, "", content.trim()].join("\n");
}

function sourceRecord(type: RequestSourceRecord["type"], filePath: string, content: string): RequestSourceRecord {
  return {
    type,
    path: filePath,
    sha256: createHash("sha256").update(content).digest("hex"),
    bytes: Buffer.byteLength(content, "utf8"),
  };
}

async function resolveSessionTarget(sourceStateRoot: string, requestedSessionId: string): Promise<SessionTarget> {
  const local = await hydrateSessionTarget(sourceStateRoot, requestedSessionId).catch(() => null);
  if (local) {
    return local;
  }

  const index = await readSessionIndex(sourceStateRoot);
  const entry = index.sessions.find((item) => item.session_id === requestedSessionId);
  if (!entry) {
    throw new Error(`Session not found: ${requestedSessionId}`);
  }
  return hydrateSessionTarget(entry.state_root, requestedSessionId, {
    repoRoot: entry.worktree_path,
    workflowId: entry.workflow_id,
  });
}

async function resolveLatestSessionTarget(sourceStateRoot: string): Promise<SessionTarget> {
  const latest = await latestSessionInStateRoot(sourceStateRoot);
  const index = await readSessionIndex(sourceStateRoot);
  const indexed = index.sessions[0];
  if (indexed && (!latest || compareTimestamps(indexed.updated_at, latest.updatedAt) >= 0)) {
    return hydrateSessionTarget(indexed.state_root, indexed.session_id, {
      repoRoot: indexed.worktree_path,
      workflowId: indexed.workflow_id,
    });
  }
  if (latest) {
    return latest;
  }
  throw new Error("No sessions found.");
}

async function latestSessionInStateRoot(stateRoot: string): Promise<(SessionTarget & { updatedAt: string }) | null> {
  const index = await readSessionIndex(stateRoot);
  if (index.sessions.length > 0) {
    const indexed = index.sessions[0]!;
    const target = await hydrateSessionTarget(indexed.state_root, indexed.session_id, {
      repoRoot: indexed.worktree_path,
      workflowId: indexed.workflow_id,
      updatedAt: indexed.updated_at,
    });
    return { ...target, updatedAt: target.updatedAt ?? indexed.updated_at };
  }
  const sessions = await listLocalSessionMetas(stateRoot);
  const candidates = sessions.map((session) => ({
    sessionId: session.session_id,
    repoRoot: session.repo_root,
    stateRoot: session.state_root,
    workflowId: session.workflow_id ?? "",
    updatedAt: session.updated_at,
  }));
  candidates.sort((left, right) => compareTimestamps(right.updatedAt, left.updatedAt));
  return candidates[0] ?? null;
}

async function hydrateSessionTarget(
  stateRoot: string,
  sessionId: string,
  fallback?: { repoRoot?: string; workflowId?: string; updatedAt?: string },
): Promise<SessionTarget & { updatedAt?: string }> {
  const session = await readSessionMeta(stateRoot, sessionId).catch(() => null);
  if (session) {
    return {
      sessionId: session.session_id,
      repoRoot: session.repo_root,
      stateRoot: session.state_root,
      workflowId: session.workflow_id ?? "",
      updatedAt: session.updated_at,
    };
  }

  if (fallback) {
    return {
      sessionId,
      repoRoot: fallback.repoRoot ?? "",
      stateRoot,
      workflowId: fallback.workflowId ?? "",
      updatedAt: fallback.updatedAt,
    };
  }

  throw new Error(`Session not found: ${sessionId}`);
}

async function startProductDevQaDelivery(
  messageParts: string[],
  options: DeliverOptions,
  defaultTaskWorktree: boolean,
): Promise<RunResult> {
  const sourceRepoRoot = path.resolve(options.repoRoot);
  const sourceStateRoot = path.resolve(options.stateRoot ?? path.join(sourceRepoRoot, DEFAULT_STATE_DIR));
  const requestInput = await readRequestInput(messageParts, options);
  const request = requestInput.request;
  if (!request) {
    throw new Error("agt2 deliver requires a request message, --from, or --from-dir.");
  }

  return startProductDevQaRun({
    sourceRepoRoot,
    sourceStateRoot,
    request,
    requestInput,
    taskWorktree: options.taskWorktree,
    defaultTaskWorktree,
  });
}

async function startProductDevQaRun(args: {
  sourceRepoRoot: string;
  sourceStateRoot: string;
  request: string;
  requestInput: RequestInput;
  taskWorktree?: boolean;
  defaultTaskWorktree: boolean;
}): Promise<RunResult> {
  const sourceStore = new RuntimeStore(args.sourceStateRoot);
  const config = await sourceStore.loadConfig();
  const useTaskWorktree = args.taskWorktree ?? (args.defaultTaskWorktree || config.task_worktree.enabled);
  let repoRoot = args.sourceRepoRoot;
  let stateRoot = args.sourceStateRoot;
  let worktree;
  if (useTaskWorktree) {
    const created = await createTaskWorktree({
      projectRoot: args.sourceRepoRoot,
      stateRoot: args.sourceStateRoot,
      request: args.request,
      config,
    });
    repoRoot = created.repoRoot;
    stateRoot = created.stateRoot;
    worktree = created.worktree;
    console.log(`worktree_path: ${repoRoot}`);
    console.log(`branch: ${worktree.branch}`);
  }

  const result = await runProductDevQaWorkflow({
    request: args.request,
    repoRoot,
    projectRoot: args.sourceRepoRoot,
    stateRoot,
    worktree,
    requestSources: args.requestInput.sources,
  });
  if (useTaskWorktree) {
    await mirrorSessionIndex(args.sourceStateRoot, stateRoot, result.session_id);
  }
  return result;
}

async function approveProductDevQaGate(
  sessionId: string | undefined,
  options: ApproveOptions,
): Promise<RunResult> {
  const sourceStateRoot = path.resolve(options.stateRoot);
  const target = sessionId
    ? await resolveSessionTarget(sourceStateRoot, sessionId)
    : await resolveLatestSessionTarget(sourceStateRoot);
  await assertProductDevQaSession(target);
  const result = await recordProductDevQaHumanDecision({
    stateRoot: target.stateRoot,
    sessionId: target.sessionId,
    decision: "go",
  });
  await mirrorSessionIndex(sourceStateRoot, target.stateRoot, result.session_id);
  return result;
}

async function assertProductDevQaSession(target: SessionTarget): Promise<void> {
  const store = new RuntimeStore(target.stateRoot);
  const productDevQa = target.workflowId === PRODUCT_DEV_QA_WORKFLOW_ID
    || await isProductDevQaSession(store, target.sessionId).catch(() => false);
  if (!productDevQa) {
    throw new Error(`agt2 only supports ${PRODUCT_DEV_QA_WORKFLOW_ID} sessions.`);
  }
}

async function mirrorSessionIndex(sourceStateRoot: string, targetStateRoot: string, sessionId: string): Promise<void> {
  const target = await hydrateSessionTarget(targetStateRoot, sessionId);
  const session = await readSessionMeta(target.stateRoot, target.sessionId);
  const index = await readSessionIndex(sourceStateRoot);
  const entry: SessionIndexEntry = {
    session_id: session.session_id,
    request: session.request,
    workflow_id: session.workflow_id ?? "",
    delivery_status: session.delivery_status,
    execution_status: session.execution_status,
    status: session.status,
    current_phase: session.current_phase,
    current_stage: session.current_stage,
    project_root: session.project_root || session.repo_root,
    worktree_path: session.repo_root,
    state_root: session.state_root,
    branch: session.worktree?.branch ?? "",
    base_ref: session.worktree?.base_ref ?? "",
    base_commit: session.worktree?.base_commit ?? "",
    created_at: session.created_at,
    updated_at: session.updated_at,
  };
  const existing = index.sessions.findIndex((item) => item.session_id === session.session_id);
  if (existing >= 0) {
    index.sessions[existing] = { ...index.sessions[existing], ...entry, created_at: index.sessions[existing].created_at };
  } else {
    index.sessions.push(entry);
  }
  index.sessions.sort((left, right) => compareTimestamps(right.updated_at, left.updated_at));
  await writeSessionIndex(sourceStateRoot, index);
}

function printResult(result: RunResult): void {
  console.log(`session_id: ${result.session_id}`);
  console.log(`delivery_status: ${result.delivery_status}`);
  console.log(`current_phase: ${result.current_phase}`);
  console.log(`execution_status: ${result.execution_status}`);
  console.log(`current_stage: ${result.current_stage}`);
  console.log(`repo_root: ${result.repo_root}`);
  console.log(`state_root: ${result.state_root}`);
  console.log(`session_dir: ${result.session_dir}`);
  if (result.blocked_reason) {
    console.log(`blocked_reason: ${result.blocked_reason}`);
  }
  console.log(`summary: ${result.summary}`);
}

async function printStatusOnce(
  store: RuntimeStore,
  sessionId: string,
  options: StatusOptions & { stalledAfterMs: number },
): Promise<SessionStatusSnapshot> {
  const snapshot = await readSessionStatus(store, sessionId, { stalledAfterMs: options.stalledAfterMs });
  if (options.json) {
    console.log(JSON.stringify(snapshot, null, 2));
  } else {
    printStatus(snapshot);
  }
  return snapshot;
}

function printStatus(snapshot: SessionStatusSnapshot): void {
  console.log(`generated_at: ${snapshot.generated_at}`);
  console.log(`session_id: ${snapshot.session_id}`);
  console.log(`delivery_status: ${snapshot.delivery_status}`);
  console.log(`current_phase: ${snapshot.current_phase}`);
  console.log("phases:");
  for (const phase of snapshot.phases) {
    console.log(`  ${phase.phase}: ${phase.status}`);
  }
  if (snapshot.blockers.length > 0) {
    console.log("blockers:");
    for (const blocker of snapshot.blockers) {
      printIndentedValue(`  ${blocker.phase}${blocker.source_role ? `/${blocker.source_role}` : ""}`, blocker.reason, "    ");
    }
  }
  console.log(`execution_status: ${snapshot.execution_status}`);
  console.log(`runtime_status: ${snapshot.runtime_status}`);
  console.log(`current_stage: ${snapshot.current_stage}`);
  console.log(`repo_root: ${snapshot.repo_root}`);
  console.log(`state_root: ${snapshot.state_root}`);
  if (snapshot.active_run) {
    console.log(`active_run_id: ${snapshot.active_run.agent_run_id}`);
    console.log(`active_role: ${snapshot.active_run.role}`);
    console.log(`active_status: ${snapshot.active_run.runtime_status}`);
    console.log(`active_started_at: ${snapshot.active_run.started_at}`);
    console.log(`active_last_heartbeat_at: ${snapshot.active_run.last_heartbeat_at ?? ""}`);
    console.log(`active_heartbeat_count: ${snapshot.active_run.heartbeat_count}`);
    console.log(`active_elapsed: ${formatDuration(snapshot.active_run.elapsed_ms)}`);
    if (snapshot.active_run.heartbeat_age_ms !== undefined) {
      console.log(`active_heartbeat_age: ${formatDuration(snapshot.active_run.heartbeat_age_ms)}`);
    }
  } else if (snapshot.latest_run) {
    console.log(`latest_run_id: ${snapshot.latest_run.agent_run_id}`);
    console.log(`latest_role: ${snapshot.latest_run.role}`);
    console.log(`latest_status: ${snapshot.latest_run.runtime_status}`);
    console.log(`latest_elapsed: ${formatDuration(snapshot.latest_run.elapsed_ms)}`);
    if (snapshot.latest_run.executor_status) {
      console.log(`latest_executor_status: ${snapshot.latest_run.executor_status}`);
    }
    if (snapshot.latest_run.result_parse_status) {
      console.log(`latest_result_parse_status: ${snapshot.latest_run.result_parse_status}`);
    }
    if (snapshot.latest_run.prompt_trace_id) {
      console.log(`latest_prompt_trace_id: ${snapshot.latest_run.prompt_trace_id}`);
    }
  }
  if (snapshot.latest_event) {
    console.log(`latest_event: ${snapshot.latest_event.kind}${snapshot.latest_event.message ? ` - ${snapshot.latest_event.message}` : ""}`);
  }
  if (snapshot.latest_tool_call) {
    console.log(`latest_tool_call: ${snapshot.latest_tool_call.name}`);
  }
  if (snapshot.blocked_reason) {
    printIndentedValue("blocked_reason", snapshot.blocked_reason, "  ");
  }
  console.log(`summary: ${snapshot.summary}`);
}

function printIndentedValue(label: string, value: string, continuationIndent: string): void {
  const lines = value.split("\n");
  console.log(`${label}: ${lines[0] ?? ""}`);
  for (const line of lines.slice(1)) {
    console.log(`${continuationIndent}${line}`);
  }
}

async function readSessionMeta(stateRoot: string, sessionId: string): Promise<SessionMeta> {
  const sessionPath = path.join(stateRoot, "sessions", sessionId, "session.json");
  return JSON.parse(await readFile(sessionPath, "utf8")) as SessionMeta;
}

async function readSessionIndex(stateRoot: string): Promise<{ schema_version: 1; sessions: SessionIndexEntry[] }> {
  const indexPath = path.join(stateRoot, "session-index.json");
  if (!existsSync(indexPath)) {
    return { schema_version: 1, sessions: [] };
  }
  return JSON.parse(await readFile(indexPath, "utf8")) as { schema_version: 1; sessions: SessionIndexEntry[] };
}

async function listLocalSessionMetas(stateRoot: string): Promise<SessionMeta[]> {
  const sessionsDir = path.join(stateRoot, "sessions");
  if (!existsSync(sessionsDir)) {
    return [];
  }
  const entries = await readdir(sessionsDir, { withFileTypes: true });
  const sessions = await Promise.all(
    entries
      .filter((entry) => entry.isDirectory())
      .map((entry) => readSessionMeta(stateRoot, entry.name).catch(() => null)),
  );
  return sessions
    .filter((session): session is SessionMeta => session !== null)
    .sort((left, right) => compareTimestamps(right.updated_at, left.updated_at));
}

async function writeSessionIndex(stateRoot: string, index: { schema_version: 1; sessions: SessionIndexEntry[] }): Promise<void> {
  await mkdir(stateRoot, { recursive: true });
  await writeFile(path.join(stateRoot, "session-index.json"), `${JSON.stringify(index, null, 2)}\n`);
}

function isWatchableRuntimeStatus(status: SessionStatusSnapshot["runtime_status"]): boolean {
  return status === "running" || status === "stalled" || status === "in_progress";
}

function parsePositiveSeconds(value: string, label: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`${label} must be a positive number of seconds.`);
  }
  return parsed;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m${remainder}s`;
}
