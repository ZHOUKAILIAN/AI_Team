#!/usr/bin/env node
import { Command } from "commander";
import path from "node:path";
import { migrateLegacySessions } from "@agent-team-runtime/migrator";
import {
  createTaskWorktree,
  initRuntime,
  recordHumanDecision,
  runWorkflow,
  type AgentRole,
  type RuntimeProfile,
  RuntimeStore,
} from "@agent-team-runtime/runtime";
import { runServer } from "@agent-team-runtime/server";

const program = new Command();

program
  .name("agt")
  .description("Agent Team Runtime JS CLI")
  .version("0.3.0-alpha.0");

// 初始化当前仓库的 runtime 状态目录和配置。
program
  .command("init")
  .description("初始化 .agt 状态目录和配置")
  .option("--repo-root <path>", "repository root", process.cwd())
  .option("--state-root <path>", "state root; defaults to <repo>/.agt")
  .option("--default-profile <profile>", "quick | investigate | full", "quick")
  .option("--default-model <model>", "OpenAI model", "gpt-5.4-mini")
  .option("--task-worktree", "enable isolated task worktrees by default")
  .option("--human-gates", "enable human gates by default")
  .action(async (options: InitOptions) => {
    const repoRoot = path.resolve(options.repoRoot);
    const result = await initRuntime({
      repoRoot,
      stateRoot: options.stateRoot ? path.resolve(options.stateRoot) : undefined,
      config: {
        default_profile: parseProfile(options.defaultProfile),
        default_model: options.defaultModel,
        task_worktree: {
          enabled: Boolean(options.taskWorktree),
          base_ref_candidates: ["origin/test", "origin/main", "test", "main"],
          branch_prefix: "feature/",
          worktree_root: ".worktrees",
          slug_max_length: 40,
        },
        human_gates: Boolean(options.humanGates),
      },
    });
    console.log(`state_root: ${result.stateRoot}`);
    console.log(`config_path: ${result.configPath}`);
  });

// 启动新的 workflow session，或继续已有的未完成 session。
program
  .command("run")
  .description("运行或继续一个 agent workflow")
  .argument("[message...]", "task request")
  .option("--profile <profile>", "quick | investigate | full")
  .option("--repo-root <path>", "repository root", process.cwd())
  .option("--state-root <path>", "state root; defaults to <repo>/.agt")
  .option("--session-id <session-id>", "existing session to continue")
  .option("--continue", "continue latest unfinished session from session-index.json")
  .option("--task-worktree", "create an isolated git worktree for this run")
  .option("--no-task-worktree", "disable configured task worktree for this run")
  .option("--human-gates", "stop full profile at ProductDefinition, TechnicalDesign, and final handoff gates")
  .action(async (messageParts: string[], options: RunOptions) => {
    const sourceRepoRoot = path.resolve(options.repoRoot);
    const sourceStateRoot = path.resolve(options.stateRoot ?? path.join(sourceRepoRoot, ".agt"));
    const sourceStore = new RuntimeStore(sourceStateRoot);
    const config = await sourceStore.loadConfig();
    const request = messageParts.join(" ").trim();

    if (options.continue || options.sessionId) {
      const target = await resolveContinuation(sourceStore, options.sessionId);
      const result = await runWorkflow({
        repoRoot: target.repoRoot,
        stateRoot: target.stateRoot,
        sessionId: target.sessionId,
        humanGates: Boolean(options.humanGates || config.human_gates),
      });
      await mirrorSessionIndex(sourceStore, target.stateRoot, result.session_id);
      printResult(result);
      return;
    }

    if (!request) {
      throw new Error("agt run requires a request message.");
    }

    // 当命令行显式要求，或配置默认开启时，为本次任务创建隔离 worktree。
    const useTaskWorktree = options.taskWorktree || (config.task_worktree.enabled && options.taskWorktree !== false);
    let repoRoot = sourceRepoRoot;
    let stateRoot = sourceStateRoot;
    let worktree;
    if (useTaskWorktree) {
      const created = await createTaskWorktree({
        projectRoot: sourceRepoRoot,
        stateRoot: sourceStateRoot,
        request,
        config,
      });
      repoRoot = created.repoRoot;
      stateRoot = created.stateRoot;
      worktree = created.worktree;
      console.log(`worktree_path: ${repoRoot}`);
      console.log(`branch: ${worktree.branch}`);
    }

    const result = await runWorkflow({
      request,
      profile: options.profile ? parseProfile(options.profile) : config.default_profile,
      repoRoot,
      projectRoot: sourceRepoRoot,
      stateRoot,
      worktree,
      humanGates: Boolean(options.humanGates || config.human_gates),
    });
    if (useTaskWorktree) {
      await mirrorSessionIndex(sourceStore, stateRoot, result.session_id);
    }
    printResult(result);
  });

// 记录人工关卡决策，并在 rework 时重置目标阶段之后的状态。
program
  .command("decision")
  .description("记录 session 的 go、no-go 或 rework 决策")
  .argument("<session-id>", "session id")
  .requiredOption("--decision <decision>", "go | no-go | rework")
  .option("--target-role <role>", "role to reset to when --decision rework")
  .option("--state-root <path>", "state root", path.join(process.cwd(), ".agt"))
  .action(async (sessionId: string, options: DecisionOptions) => {
    const sourceStore = new RuntimeStore(path.resolve(options.stateRoot));
    const target = await resolveSessionStore(sourceStore, sessionId);
    const result = await recordHumanDecision({
      stateRoot: target.stateRoot,
      sessionId: target.sessionId,
      decision: parseDecision(options.decision),
      targetRole: options.targetRole ? parseAgentRole(options.targetRole) : undefined,
    });
    await mirrorSessionIndex(sourceStore, target.stateRoot, result.session_id);
    printResult(result);
  });

// 打印最新 session 或指定 session 的 workflow 概览状态。
program
  .command("status")
  .description("查看 workflow 状态")
  .argument("[session-id]", "session id")
  .option("--state-root <path>", "state root", path.join(process.cwd(), ".agt"))
  .action(async (sessionId: string | undefined, options: { stateRoot: string }) => {
    const store = new RuntimeStore(path.resolve(options.stateRoot));
    const target = sessionId
      ? await resolveSessionStore(store, sessionId)
      : await resolveLatestSessionStore(store);
    const targetStore = new RuntimeStore(target.stateRoot);
    const session = await targetStore.loadSession(target.sessionId);
    if (!session) {
      throw new Error("No sessions found.");
    }
    const workflow = await targetStore.loadWorkflow(session.session_id);
    console.log(`session_id: ${session.session_id}`);
    console.log(`profile: ${session.profile}`);
    console.log(`status: ${workflow.status}`);
    console.log(`current_stage: ${workflow.current_stage}`);
    console.log(`repo_root: ${session.repo_root}`);
    console.log(`state_root: ${session.state_root}`);
    console.log(`summary: ${workflow.summary}`);
    if (workflow.blocked_reason) {
      console.log(`blocked_reason: ${workflow.blocked_reason}`);
    }
  });

// 以 JSON 输出一个 session 的 trace ledger，方便调试或复盘。
program
  .command("inspect")
  .description("查看 session 的 workflow、prompt、artifact、agent run 和 tool call")
  .argument("<session-id>", "session id")
  .option("--state-root <path>", "state root", path.join(process.cwd(), ".agt"))
  .action(async (sessionId: string, options: { stateRoot: string }) => {
    const sourceStore = new RuntimeStore(path.resolve(options.stateRoot));
    const target = await resolveSessionStore(sourceStore, sessionId);
    const store = new RuntimeStore(target.stateRoot);
    const session = await store.loadSession(target.sessionId);
    const workflow = await store.loadWorkflow(target.sessionId);
    const toolCalls = await store.readToolCalls(target.sessionId);
    const prompts = await store.readPromptTraces(target.sessionId);
    const artifacts = await store.readArtifacts(target.sessionId);
    const agentRuns = await store.listAgentRuns(target.sessionId);
    console.log(JSON.stringify({ session, workflow, prompts, artifacts, agent_runs: agentRuns, tool_calls: toolCalls }, null, 2));
  });

// 将旧 Python/Codex runtime 的 session 迁移到新的 .agt session schema。
program
  .command("migrate")
  .description("迁移旧 runtime session")
  .requiredOption("--from <path>", "legacy .agt or .agent-team root")
  .option("--state-root <path>", "target state root", path.join(process.cwd(), ".agt"))
  .option("--dry-run", "scan without writing")
  .option("--apply", "write migrated sessions")
  .action(async (options: { from: string; stateRoot: string; dryRun?: boolean; apply?: boolean }) => {
    if (!options.dryRun && !options.apply) {
      throw new Error("Use --dry-run or --apply.");
    }
    const report = await migrateLegacySessions({
      sourceRoot: path.resolve(options.from),
      targetStateRoot: path.resolve(options.stateRoot),
      apply: Boolean(options.apply),
    });
    console.log(JSON.stringify(report, null, 2));
  });

// 启动本地 API 和 web 控制台，用于读取 session 状态和 trace 产物。
program
  .command("server")
  .description("启动 session API 和 web 控制台")
  .option("--state-root <path>", "state root", path.join(process.cwd(), ".agt"))
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
  defaultProfile: string;
  defaultModel: string;
  taskWorktree?: boolean;
  humanGates?: boolean;
};

type RunOptions = {
  profile?: string;
  repoRoot: string;
  stateRoot?: string;
  sessionId?: string;
  continue?: boolean;
  taskWorktree?: boolean;
  humanGates?: boolean;
};

type DecisionOptions = {
  decision: string;
  targetRole?: string;
  stateRoot: string;
};

function parseProfile(value: string): RuntimeProfile {
  if (value === "quick" || value === "investigate" || value === "full") {
    return value;
  }
  throw new Error(`Unsupported profile: ${value}`);
}

function parseDecision(value: string): "go" | "no-go" | "rework" {
  if (value === "go" || value === "no-go" || value === "rework") {
    return value;
  }
  throw new Error(`Unsupported decision: ${value}`);
}

function parseAgentRole(value: string): AgentRole {
  const allowed = new Set<AgentRole>([
    "planner",
    "repo_scout",
    "test_scout",
    "writer",
    "verifier",
    "summarizer",
    "route",
    "product_definition",
    "project_runtime",
    "technical_design",
    "implementation",
    "verification",
    "governance_review",
    "acceptance",
    "session_handoff",
    "migration",
  ]);
  if (allowed.has(value as AgentRole)) {
    return value as AgentRole;
  }
  throw new Error(`Unsupported role: ${value}`);
}

async function resolveContinuation(store: RuntimeStore, requestedSessionId?: string): Promise<{
  sessionId: string;
  repoRoot: string;
  stateRoot: string;
}> {
  if (requestedSessionId) {
    return resolveSessionStore(store, requestedSessionId);
  }
  const index = await store.loadSessionIndex();
  const entry = index.sessions.find((item) => item.status === "in_progress" || item.status === "waiting_human");
  if (entry) {
    return { sessionId: entry.session_id, repoRoot: entry.worktree_path, stateRoot: entry.state_root };
  }
  const latest = await store.latestSession();
  if (!latest) {
    throw new Error("No unfinished session found.");
  }
  return { sessionId: latest.session_id, repoRoot: latest.repo_root, stateRoot: latest.state_root };
}

async function resolveSessionStore(store: RuntimeStore, requestedSessionId: string): Promise<{
  sessionId: string;
  repoRoot: string;
  stateRoot: string;
}> {
  try {
    const session = await store.loadSession(requestedSessionId);
    return { sessionId: session.session_id, repoRoot: session.repo_root, stateRoot: session.state_root };
  } catch {
    const index = await store.loadSessionIndex();
    const entry = index.sessions.find((item) => item.session_id === requestedSessionId);
    if (!entry) {
      throw new Error(`Session not found: ${requestedSessionId}`);
    }
    const targetStore = new RuntimeStore(entry.state_root);
    const session = await targetStore.loadSession(requestedSessionId);
    return { sessionId: session.session_id, repoRoot: session.repo_root, stateRoot: session.state_root };
  }
}

async function resolveLatestSessionStore(store: RuntimeStore): Promise<{
  sessionId: string;
  repoRoot: string;
  stateRoot: string;
}> {
  const latest = await store.latestSession();
  const index = await store.loadSessionIndex();
  const indexed = index.sessions[0];
  if (indexed && (!latest || indexed.updated_at.localeCompare(latest.updated_at) >= 0)) {
    return { sessionId: indexed.session_id, repoRoot: indexed.worktree_path, stateRoot: indexed.state_root };
  }
  if (latest) {
    return { sessionId: latest.session_id, repoRoot: latest.repo_root, stateRoot: latest.state_root };
  }
  throw new Error("No sessions found.");
}

async function mirrorSessionIndex(sourceStore: RuntimeStore, targetStateRoot: string, sessionId: string): Promise<void> {
  const targetStore = new RuntimeStore(targetStateRoot);
  const session = await targetStore.loadSession(sessionId);
  await sourceStore.upsertSessionIndex(session);
}

function printResult(result: Awaited<ReturnType<typeof runWorkflow>>): void {
  console.log(`session_id: ${result.session_id}`);
  console.log(`profile: ${result.profile}`);
  console.log(`status: ${result.status}`);
  console.log(`current_stage: ${result.current_stage}`);
  console.log(`repo_root: ${result.repo_root}`);
  console.log(`state_root: ${result.state_root}`);
  console.log(`session_dir: ${result.session_dir}`);
  if (result.blocked_reason) {
    console.log(`blocked_reason: ${result.blocked_reason}`);
  }
  console.log(`summary: ${result.summary}`);
}
