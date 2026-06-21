import Fastify from "fastify";
import fastifyStatic from "@fastify/static";
import websocket from "@fastify/websocket";
import { existsSync } from "node:fs";
import path from "node:path";
import {
  RuntimeStore,
  type AgentRunRecord,
  type ArtifactRecord,
  type DeliveryWorkflowRecord,
  type ExecutionWorkflowRecord,
  PRODUCT_DEV_QA_WORKFLOW_ID,
  type ProductDevQaWorkflowRunRecord,
  type PromptTraceRecord,
  type RuntimeEvent,
  type SessionRecord,
  type ToolCallRecord,
} from "@agent-team-runtime/runtime";

export type CreateServerOptions = {
  stateRoot: string;
  webDist?: string;
};

type HydratedSession = {
  session: SessionRecord;
  deliveryWorkflow: DeliveryWorkflowRecord;
  executionWorkflow: ExecutionWorkflowRecord;
  workflowRun: ProductDevQaWorkflowRunRecord | null;
  events: RuntimeEvent[];
  toolCalls: ToolCallRecord[];
  prompts: PromptTraceRecord[];
  artifacts: ArtifactRecord[];
  agentRuns: AgentRunRecord[];
};

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

  app.get("/api/config", async () => {
    return { config: await store.loadConfig(), state_root: store.stateRoot };
  });

  app.get("/api/session-index", async () => {
    return await store.loadSessionIndex();
  });

  app.get("/api/console/snapshot", async () => {
    return buildConsoleSnapshot(await hydrateSessions(store));
  });

  app.get("/api/projects", async () => {
    return { projects: buildConsoleSnapshot(await hydrateSessions(store)).projects };
  });

  app.get("/api/sessions", async () => {
    return { sessions: await store.listSessions() };
  });

  app.get<{ Params: { sessionId: string } }>("/api/sessions/:sessionId", async (request, reply) => {
    try {
      const hydrated = await hydrateSession(store, request.params.sessionId);
      return {
        session: hydrated.session,
        workflow_run: hydrated.workflowRun,
        delivery_workflow: hydrated.deliveryWorkflow,
        execution_workflow: hydrated.executionWorkflow,
        workflow: hydrated.executionWorkflow,
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

  app.get<{ Params: { sessionId: string } }>("/api/sessions/:sessionId/events", async (request, reply) => {
    try {
      return { events: await store.readEvents(request.params.sessionId) };
    } catch (error) {
      return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
    }
  });

  app.get<{ Params: { sessionId: string } }>("/api/sessions/:sessionId/tool-calls", async (request, reply) => {
    try {
      return { tool_calls: await store.readToolCalls(request.params.sessionId) };
    } catch (error) {
      return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
    }
  });

  app.get<{ Params: { sessionId: string } }>("/api/sessions/:sessionId/prompts", async (request, reply) => {
    try {
      return { prompts: await store.readPromptTraces(request.params.sessionId) };
    } catch (error) {
      return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
    }
  });

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

  app.get<{ Params: { sessionId: string } }>("/api/sessions/:sessionId/artifacts", async (request, reply) => {
    try {
      return { artifacts: await store.readArtifacts(request.params.sessionId) };
    } catch (error) {
      return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
    }
  });

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

  app.get<{ Params: { sessionId: string } }>("/api/sessions/:sessionId/agent-runs", async (request, reply) => {
    try {
      return { agent_runs: await store.listAgentRuns(request.params.sessionId) };
    } catch (error) {
      return reply.status(404).send({ error: error instanceof Error ? error.message : String(error) });
    }
  });

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

  app.get("/ws/runtime", { websocket: true }, async (socket) => {
    socket.send(JSON.stringify({ type: "hello", state_root: store.stateRoot }));
  });

  if (webDist) {
    app.setNotFoundHandler(async (request, reply) => {
      if (request.raw.url?.startsWith("/api/") || request.raw.url?.startsWith("/ws/")) {
        return reply.status(404).send({ error: "Not found" });
      }
      return reply.sendFile("index.html");
    });
  }

  return app;
}

export async function runServer(options: CreateServerOptions & { host: string; port: number }): Promise<string> {
  const app = await createServer(options);
  await app.listen({ host: options.host, port: options.port });
  return `http://${options.host}:${options.port}`;
}

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

async function hydrateSession(store: RuntimeStore, sessionId: string): Promise<HydratedSession> {
  const session = await store.loadSession(sessionId);
  const deliveryWorkflow = await store.loadDeliveryWorkflow(sessionId);
  const executionWorkflow = await store.loadExecutionWorkflow(sessionId);
  const workflowRun = session.workflow_id === PRODUCT_DEV_QA_WORKFLOW_ID
    ? await store.loadProductDevQaWorkflow(sessionId).catch(() => null)
    : null;
  return {
    session,
    deliveryWorkflow,
    executionWorkflow,
    workflowRun,
    events: await store.readEvents(sessionId),
    toolCalls: await store.readToolCalls(sessionId),
    prompts: await store.readPromptTraces(sessionId),
    artifacts: await store.readArtifacts(sessionId),
    agentRuns: await store.listAgentRuns(sessionId),
  };
}

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

function sessionSummary(item: HydratedSession, projectId: string) {
  const session = item.session;
  const delivery = item.deliveryWorkflow;
  const execution = item.executionWorkflow;
  const blocker = delivery.blockers.find((item) => item.status === "open");
  return {
    session_id: session.session_id,
    project_id: projectId,
    project_name: path.basename(session.project_root || session.repo_root),
    project_root: session.project_root || session.repo_root,
    worktree_path: session.repo_root,
    branch: session.worktree?.branch ?? "",
    state_root: session.state_root,
    request: session.request,
    current_state: delivery.status === "done" ? "Done" : delivery.current_phase,
    current_phase: delivery.current_phase,
    current_stage: execution.current_stage,
    workflow_status: delivery.status,
    delivery_status: delivery.status,
    execution_status: execution.status,
    blocked_reason: blocker?.reason ?? execution.blocked_reason,
    active_run: item.agentRuns.find((run) => run.status === "running") ?? null,
    artifact_paths: artifactPaths(execution),
    prompt_count: item.prompts.length,
    artifact_count: item.artifacts.length,
    tool_call_count: item.toolCalls.length,
    agent_run_count: item.agentRuns.length,
    created_at: session.created_at,
    updated_at: session.updated_at,
  };
}

function buildPanelSnapshot(item: HydratedSession) {
  const { session, deliveryWorkflow, executionWorkflow, workflowRun, events, artifacts, prompts, agentRuns, toolCalls } = item;
  const blocker = deliveryWorkflow.blockers.find((item) => item.status === "open");
  return {
    overview: {
      project: path.basename(session.project_root || session.repo_root),
      role: deliveryWorkflow.current_phase,
      status: deliveryWorkflow.status,
      text: deliveryWorkflow.summary || session.request,
      detail: blocker?.reason ?? executionWorkflow.blocked_reason,
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
      current_state: deliveryWorkflow.status === "done" ? "Done" : deliveryWorkflow.current_phase,
      current_phase: deliveryWorkflow.current_phase,
      current_stage: executionWorkflow.current_stage,
      workflow_status: deliveryWorkflow.status,
      delivery_status: deliveryWorkflow.status,
      execution_status: executionWorkflow.status,
      workflow_run: workflowRun,
      blocked_reason: blocker?.reason ?? executionWorkflow.blocked_reason,
      artifact_paths: artifactPaths(executionWorkflow),
      phases: deliveryWorkflow.phases,
      blockers: deliveryWorkflow.blockers,
      steps: executionWorkflow.steps,
    },
    operator: {
      current_action: deliveryWorkflow.summary,
      next_action: deliveryWorkflow.status === "done" ? "" : `Continue ${deliveryWorkflow.current_phase}`,
      blocked_reason: blocker?.reason ?? executionWorkflow.blocked_reason,
      latest_event: events.at(-1) ?? null,
    },
    evidence: {
      required: deliveryWorkflow.evidence_refs,
      provided: deliveryWorkflow.evidence_refs,
      pending: [],
      acceptance_criteria: [],
      unresolved_items: deliveryWorkflow.blockers.map((item) => item.reason),
    },
    artifacts: [
      { name: "session.json", path: path.join(session.state_root, "sessions", session.session_id, "session.json"), exists: true },
      ...(workflowRun ? [{ name: "workflow-run.json", path: path.join(session.state_root, "sessions", session.session_id, "workflow-run.json"), exists: true }] : []),
      { name: "delivery-workflow.json", path: path.join(session.state_root, "sessions", session.session_id, "delivery-workflow.json"), exists: true },
      { name: "execution-workflow.json", path: path.join(session.state_root, "sessions", session.session_id, "execution-workflow.json"), exists: true },
      { name: "tool-calls.jsonl", path: path.join(session.state_root, "sessions", session.session_id, "tool-calls.jsonl"), exists: true },
      ...artifacts.map((artifact) => ({ ...artifact, exists: true })),
    ],
    prompts,
    agent_runs: agentRuns,
    tool_calls: toolCalls,
    events,
  };
}

function artifactPaths(workflow: ExecutionWorkflowRecord): Record<string, string> {
  return Object.fromEntries(
    workflow.steps
      .filter((step) => step.artifact_path)
      .map((step) => [step.role, step.artifact_path]),
  );
}

function projectIdFor(projectRoot: string): string {
  return Buffer.from(projectRoot).toString("base64url").slice(0, 32);
}

function maxDate(left: string, right: string): string {
  return left.localeCompare(right) >= 0 ? left : right;
}

function resolveWebDist(explicit?: string): string | null {
  const candidates = [
    explicit,
    path.resolve(process.cwd(), "apps/web/dist"),
  ].filter(Boolean) as string[];
  return candidates.find((candidate) => existsSync(path.join(candidate, "index.html"))) ?? null;
}
