import Fastify from "fastify";
import fastifyStatic from "@fastify/static";
import websocket from "@fastify/websocket";
import { existsSync } from "node:fs";
import path from "node:path";
import {
  RuntimeStore,
  type AgentRunRecord,
  type ArtifactRecord,
  type PromptTraceRecord,
  type RuntimeEvent,
  type SessionRecord,
  type ToolCallRecord,
  type WorkflowRecord,
} from "@agent-team-runtime/runtime";

export type CreateServerOptions = {
  stateRoot: string;
  webDist?: string;
};

type HydratedSession = {
  session: SessionRecord;
  workflow: WorkflowRecord;
  events: RuntimeEvent[];
  toolCalls: ToolCallRecord[];
  prompts: PromptTraceRecord[];
  artifacts: ArtifactRecord[];
  agentRuns: AgentRunRecord[];
};

// 创建 Fastify 服务，并注册 session API、websocket 和可选 web 静态资源。
// Creates the Fastify service and registers session APIs, websocket, and optional web assets.
export async function createServer(options: CreateServerOptions) {
  const app = Fastify({ logger: false });
  const store = new RuntimeStore(options.stateRoot);
  await app.register(websocket);

  const webDist = resolveWebDist(options.webDist);
  if (webDist) {
    await app.register(fastifyStatic, {
      root: webDist,
      prefix: "/",
    });
  }

  // 配置接口：返回当前 runtime 配置和 stateRoot。
  // Config endpoint: returns the current runtime config and stateRoot.
  app.get("/api/config", async () => {
    return { config: await store.loadConfig(), state_root: store.stateRoot };
  });

  // session-index 接口：返回跨 worktree 的 session 索引。
  // Session-index endpoint: returns the cross-worktree session index.
  app.get("/api/session-index", async () => {
    return await store.loadSessionIndex();
  });

  // 控制台快照接口：聚合项目、worktree 和 session 概览。
  // Console snapshot endpoint: aggregates project, worktree, and session summaries.
  app.get("/api/console/snapshot", async () => {
    return buildConsoleSnapshot(await hydrateSessions(store));
  });

  // 项目列表接口：返回控制台快照中的 projects 部分。
  // Projects endpoint: returns the projects section from the console snapshot.
  app.get("/api/projects", async () => {
    return { projects: buildConsoleSnapshot(await hydrateSessions(store)).projects };
  });

  // session 列表接口：按更新时间列出当前 stateRoot 下的 session。
  // Sessions endpoint: lists sessions under the current stateRoot by updated time.
  app.get("/api/sessions", async () => {
    return { sessions: await store.listSessions() };
  });

  // session 详情接口：返回 workflow、trace、artifact 和面板快照。
  // Session detail endpoint: returns workflow, traces, artifacts, and panel snapshot.
  app.get<{ Params: { sessionId: string } }>("/api/sessions/:sessionId", async (request, reply) => {
    try {
      const hydrated = await hydrateSession(store, request.params.sessionId);
      return {
        session: hydrated.session,
        workflow: hydrated.workflow,
        prompts: hydrated.prompts,
        artifacts: hydrated.artifacts,
        agent_runs: hydrated.agentRuns,
        tool_calls: hydrated.toolCalls,
        events: hydrated.events,
        snapshot: buildPanelSnapshot(hydrated),
      };
    } catch (error) {
      return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
    }
  });

  // 事件接口：读取指定 session 的 events.jsonl。
  // Events endpoint: reads events.jsonl for one session.
  app.get<{ Params: { sessionId: string } }>("/api/sessions/:sessionId/events", async (request, reply) => {
    try {
      return { events: await store.readEvents(request.params.sessionId) };
    } catch (error) {
      return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
    }
  });

  // tool calls 接口：读取指定 session 的 tool-calls.jsonl。
  // Tool-calls endpoint: reads tool-calls.jsonl for one session.
  app.get<{ Params: { sessionId: string } }>("/api/sessions/:sessionId/tool-calls", async (request, reply) => {
    try {
      return { tool_calls: await store.readToolCalls(request.params.sessionId) };
    } catch (error) {
      return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
    }
  });

  // prompt trace 列表接口：读取指定 session 的 prompt trace 元数据。
  // Prompt-trace list endpoint: reads prompt trace metadata for one session.
  app.get<{ Params: { sessionId: string } }>("/api/sessions/:sessionId/prompts", async (request, reply) => {
    try {
      return { prompts: await store.readPromptTraces(request.params.sessionId) };
    } catch (error) {
      return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
    }
  });

  // prompt 内容接口：读取 prompt.md，并校验 prompt 属于该 session。
  // Prompt content endpoint: reads prompt.md and verifies it belongs to the session.
  app.get<{ Params: { sessionId: string; promptId: string } }>(
    "/api/sessions/:sessionId/prompts/:promptId",
    async (request, reply) => {
      try {
        const payload = await store.readPromptContent(request.params.promptId);
        if (payload.prompt.session_id !== request.params.sessionId) {
          return reply.status(404).send({ error: "Prompt does not belong to this session." });
        }
        return payload;
      } catch (error) {
        return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
      }
    },
  );

  // artifact 列表接口：读取指定 session 的 artifact index。
  // Artifact list endpoint: reads the artifact index for one session.
  app.get<{ Params: { sessionId: string } }>("/api/sessions/:sessionId/artifacts", async (request, reply) => {
    try {
      return { artifacts: await store.readArtifacts(request.params.sessionId) };
    } catch (error) {
      return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
    }
  });

  // artifact 内容接口：读取指定 artifact 的正文。
  // Artifact content endpoint: reads text content for one artifact.
  app.get<{ Params: { sessionId: string; artifactName: string } }>(
    "/api/sessions/:sessionId/artifacts/:artifactName",
    async (request, reply) => {
      try {
        return await store.readArtifactContent(request.params.sessionId, decodeURIComponent(request.params.artifactName));
      } catch (error) {
        return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
      }
    },
  );

  // agent run 列表接口：读取指定 session 的 agents/*.json。
  // Agent-run list endpoint: reads agents/*.json for one session.
  app.get<{ Params: { sessionId: string } }>("/api/sessions/:sessionId/agent-runs", async (request, reply) => {
    try {
      return { agent_runs: await store.listAgentRuns(request.params.sessionId) };
    } catch (error) {
      return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
    }
  });

  // 兼容面板接口：返回指定或最新 session 的 panel snapshot。
  // Compatibility panel endpoint: returns the requested or latest session panel snapshot.
  app.get("/api/session", async (request, reply) => {
    const query = request.query as { session_id?: string };
    const sessionId = query.session_id ?? (await store.listSessions())[0]?.session_id;
    if (!sessionId) {
      return reply.status(404).send({ error: "No workflow session exists yet." });
    }
    try {
      return buildPanelSnapshot(await hydrateSession(store, sessionId));
    } catch (error) {
      return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
    }
  });

  // runtime websocket：发送 hello 消息，让前端知道连接可用。
  // Runtime websocket: sends a hello message so the frontend knows the connection is alive.
  app.get("/ws/runtime", { websocket: true }, async (socket) => {
    socket.send(JSON.stringify({ type: "hello", state_root: store.stateRoot }));
  });

  if (webDist) {
    // SPA fallback：非 API/WS 路径回退到 index.html。
    // SPA fallback: serves index.html for non-API and non-WS paths.
    app.setNotFoundHandler(async (request, reply) => {
      if (request.raw.url?.startsWith("/api/") || request.raw.url?.startsWith("/ws/")) {
        return reply.status(404).send({ error: "Not found" });
      }
      return reply.sendFile("index.html");
    });
  }

  return app;
}

// 启动 Fastify 服务并返回浏览器可访问的 URL。
// Starts the Fastify server and returns the browser URL.
export async function runServer(options: CreateServerOptions & { host: string; port: number }): Promise<string> {
  const app = await createServer(options);
  await app.listen({ host: options.host, port: options.port });
  return `http://${options.host}:${options.port}`;
}

// 读取并组装所有 session，聚合视图会跳过损坏的 session。
// Reads and hydrates all sessions, skipping malformed sessions in aggregate views.
async function hydrateSessions(store: RuntimeStore): Promise<HydratedSession[]> {
  const sessions = await store.listSessions();
  const hydrated: HydratedSession[] = [];
  for (const session of sessions) {
    try {
      hydrated.push(await hydrateSession(store, session.session_id));
    } catch {
      // Skip malformed sessions in the aggregate view; detail endpoint reports the error.
    }
  }
  return hydrated;
}

// 读取单个 session 的所有 trace ledger 组成部分。
// Reads every trace-ledger part for one session.
async function hydrateSession(store: RuntimeStore, sessionId: string): Promise<HydratedSession> {
  const session = await store.loadSession(sessionId);
  const workflow = await store.loadWorkflow(sessionId);
  return {
    session,
    workflow,
    events: await store.readEvents(sessionId),
    toolCalls: await store.readToolCalls(sessionId),
    prompts: await store.readPromptTraces(sessionId),
    artifacts: await store.readArtifacts(sessionId),
    agentRuns: await store.listAgentRuns(sessionId),
  };
}

// 将 hydrated sessions 聚合成项目/worktree/session 的控制台快照。
// Aggregates hydrated sessions into a project/worktree/session console snapshot.
function buildConsoleSnapshot(items: HydratedSession[]) {
  const projects = new Map<string, any>();
  for (const item of items) {
    const projectRoot = item.session.project_root || item.session.repo_root;
    const projectId = projectIdFor(projectRoot);
    const worktreePath = item.session.repo_root;
    const project = projects.get(projectId) ?? {
      project_id: projectId,
      project_name: path.basename(projectRoot) || projectId,
      project_root: projectRoot,
      worktree_count: 0,
      session_count: 0,
      active_count: 0,
      waiting_human_count: 0,
      blocked_count: 0,
      updated_at: item.session.updated_at,
      worktrees: [],
      sessions: [],
    };
    const worktree = ensureWorktreeSummary(project, item.session);
    const summary = sessionSummary(item, projectId);
    project.sessions.push(summary);
    project.session_count += 1;
    project.updated_at = maxDate(project.updated_at, item.session.updated_at);
    worktree.session_count += 1;
    if (summary.workflow_status === "blocked") {
      project.blocked_count += 1;
      worktree.blocked_count += 1;
    } else if (summary.workflow_status === "waiting_human") {
      project.waiting_human_count += 1;
      worktree.waiting_human_count += 1;
    } else if (summary.workflow_status === "in_progress") {
      project.active_count += 1;
      worktree.active_count += 1;
    }
    worktree.updated_at = maxDate(worktree.updated_at, item.session.updated_at);
    projects.set(projectId, project);
    void worktreePath;
  }
  const projectList = [...projects.values()].map((project) => ({
    ...project,
    worktree_count: project.worktrees.length,
    sessions: project.sessions.sort((a: any, b: any) => b.updated_at.localeCompare(a.updated_at)),
  })).sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return {
    generated_at: new Date().toISOString(),
    stats: {
      projects: projectList.length,
      worktrees: projectList.reduce((sum, project) => sum + project.worktree_count, 0),
      sessions: items.length,
      active: projectList.reduce((sum, project) => sum + project.active_count, 0),
      waiting_human: projectList.reduce((sum, project) => sum + project.waiting_human_count, 0),
      blocked: projectList.reduce((sum, project) => sum + project.blocked_count, 0),
    },
    projects: projectList,
  };
}

// 确保项目快照里存在当前 session 对应的 worktree 摘要。
// Ensures the project snapshot has a worktree summary for the current session.
function ensureWorktreeSummary(project: any, session: SessionRecord) {
  let worktree = project.worktrees.find((item: any) => item.worktree_path === session.repo_root);
  if (!worktree) {
    worktree = {
      worktree_path: session.repo_root,
      branch: session.worktree?.branch ?? "",
      state_root: session.state_root,
      session_count: 0,
      active_count: 0,
      waiting_human_count: 0,
      blocked_count: 0,
      updated_at: session.updated_at,
    };
    project.worktrees.push(worktree);
  }
  return worktree;
}

// 将 hydrated session 压缩成控制台列表使用的 session summary。
// Converts a hydrated session into the session summary used by console lists.
function sessionSummary(item: HydratedSession, projectId: string) {
  const session = item.session;
  const workflow = item.workflow;
  return {
    session_id: session.session_id,
    project_id: projectId,
    project_name: path.basename(session.project_root || session.repo_root),
    project_root: session.project_root || session.repo_root,
    worktree_path: session.repo_root,
    branch: session.worktree?.branch ?? "",
    state_root: session.state_root,
    request: session.request,
    current_state: workflow.status === "done" ? "Done" : workflow.current_stage,
    current_stage: workflow.current_stage,
    workflow_status: workflow.status,
    blocked_reason: workflow.blocked_reason,
    active_run: item.agentRuns.find((run) => run.status === "running") ?? null,
    artifact_paths: artifactPaths(workflow),
    prompt_count: item.prompts.length,
    artifact_count: item.artifacts.length,
    tool_call_count: item.toolCalls.length,
    agent_run_count: item.agentRuns.length,
    created_at: session.created_at,
    updated_at: session.updated_at,
  };
}

// 构建 session detail 页面使用的 panel snapshot。
// Builds the panel snapshot consumed by the session detail page.
function buildPanelSnapshot(item: HydratedSession) {
  const { session, workflow, events, artifacts, prompts, agentRuns, toolCalls } = item;
  return {
    overview: {
      project: path.basename(session.project_root || session.repo_root),
      role: workflow.current_stage,
      status: workflow.status,
      text: workflow.summary || session.request,
      detail: workflow.blocked_reason,
    },
    session: {
      session_id: session.session_id,
      request: session.request,
      raw_message: session.request,
      created_at: session.created_at,
      session_dir: path.join(session.state_root, "sessions", session.session_id),
      artifact_dir: path.join(session.state_root, "sessions", session.session_id, "artifacts"),
      state_root: session.state_root,
      repo_root: session.repo_root,
      project_root: session.project_root || session.repo_root,
    },
    state: {
      current_state: workflow.status === "done" ? "Done" : workflow.current_stage,
      current_stage: workflow.current_stage,
      workflow_status: workflow.status,
      blocked_reason: workflow.blocked_reason,
      artifact_paths: artifactPaths(workflow),
      steps: workflow.steps,
    },
    operator: {
      current_action: workflow.summary,
      next_action: workflow.status === "done" ? "" : `Continue ${workflow.current_stage}`,
      blocked_reason: workflow.blocked_reason,
      latest_event: events.at(-1) ?? null,
    },
    evidence: {
      required: workflow.commands_run,
      provided: workflow.commands_run,
      pending: [],
      acceptance_criteria: [],
      unresolved_items: workflow.blocked_reason ? [workflow.blocked_reason] : [],
    },
    artifacts: [
      { name: "session.json", path: path.join(session.state_root, "sessions", session.session_id, "session.json"), exists: true },
      { name: "workflow.json", path: path.join(session.state_root, "sessions", session.session_id, "workflow.json"), exists: true },
      { name: "tool-calls.jsonl", path: path.join(session.state_root, "sessions", session.session_id, "tool-calls.jsonl"), exists: true },
      ...artifacts.map((artifact) => ({ ...artifact, exists: true })),
    ],
    prompts,
    agent_runs: agentRuns,
    tool_calls: toolCalls,
    events,
  };
}

// 从 workflow steps 中提取 role 到 artifact path 的映射。
// Extracts a role-to-artifact-path map from workflow steps.
function artifactPaths(workflow: WorkflowRecord): Record<string, string> {
  return Object.fromEntries(
    workflow.steps
      .filter((step) => step.artifact_path)
      .map((step) => [step.role, step.artifact_path]),
  );
}

// 基于 projectRoot 生成稳定但短的 project id。
// Generates a stable but short project id from projectRoot.
function projectIdFor(projectRoot: string): string {
  return Buffer.from(projectRoot).toString("base64url").slice(0, 32);
}

// 返回两个 ISO 时间字符串中较新的一个。
// Returns the newer of two ISO timestamp strings.
function maxDate(left: string, right: string): string {
  return left.localeCompare(right) >= 0 ? left : right;
}

// 查找可用的 web dist 目录；不存在时只提供 API。
// Finds an available web dist directory and serves API only when none exists.
function resolveWebDist(explicit?: string): string | null {
  const candidates = [
    explicit,
    path.resolve(process.cwd(), "apps/web/dist"),
    path.resolve(process.cwd(), "agent_team/web_dist"),
  ].filter(Boolean) as string[];
  return candidates.find((candidate) => existsSync(path.join(candidate, "index.html"))) ?? null;
}
