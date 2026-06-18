export type WorkflowStatus = "in_progress" | "waiting_human" | "blocked" | "done" | string;

export type StatusLayers = {
  requirement_status: string;
  implementation_status: string;
  verification_status: string;
  trace_status: string;
};

export type RuntimeEvent = {
  kind?: string;
  role?: string;
  stage?: string;
  state?: string;
  status?: string;
  message?: string;
  at?: string;
};

export type WorkflowStep = {
  role: string;
  status: string;
  agent_run_id?: string;
  prompt_trace_id?: string;
  artifact_path?: string;
  files_changed?: string[];
  commands_run?: string[];
  summary?: string;
  started_at?: string;
  completed_at?: string;
};

export type PromptTrace = {
  prompt_id: string;
  session_id: string;
  role: string;
  runner?: string;
  source: string;
  path: string;
  sha256: string;
  bytes: number;
  created_at: string;
  metadata?: Record<string, unknown>;
};

export type Artifact = {
  artifact_id?: string;
  session_id?: string;
  role?: string;
  name: string;
  path: string;
  bytes?: number;
  created_at?: string;
  exists?: boolean;
  metadata?: Record<string, unknown>;
};

export type AgentRun = {
  agent_run_id: string;
  role: string;
  status: string;
  runner: string;
  input: string;
  output: string;
  error?: string;
  started_at: string;
  completed_at?: string;
  metadata?: Record<string, unknown>;
};

export type ToolCall = {
  at: string;
  agent_run_id: string;
  role: string;
  kind: string;
  name: string;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  exit_code?: number | null;
  duration_ms?: number;
};

export type WorktreeSummary = {
  worktree_path: string;
  branch: string;
  state_root: string;
  session_count: number;
  active_count: number;
  waiting_human_count: number;
  blocked_count: number;
};

export type SessionSummary = {
  session_id: string;
  project_id: string;
  project_name: string;
  project_root: string;
  worktree_path: string;
  branch: string;
  state_root: string;
  request: string;
  current_state: string;
  current_stage: string;
  workflow_status: WorkflowStatus;
  status_layers?: StatusLayers;
  blocked_reason: string;
  active_run: unknown;
  artifact_paths: Record<string, string>;
  prompt_count: number;
  artifact_count: number;
  tool_call_count: number;
  agent_run_count: number;
  created_at: string;
  updated_at: string;
};

export type ProjectSummary = {
  project_id: string;
  project_name: string;
  project_root: string;
  worktree_count: number;
  session_count: number;
  active_count: number;
  waiting_human_count: number;
  blocked_count: number;
  updated_at: string;
  worktrees: WorktreeSummary[];
  sessions: SessionSummary[];
};

export type ConsoleSnapshot = {
  generated_at: string;
  stats: {
    projects: number;
    worktrees: number;
    sessions: number;
    active: number;
    waiting_human: number;
    blocked: number;
  };
  projects: ProjectSummary[];
};

export type PanelSnapshot = {
  overview: {
    project: string;
    role: string;
    status: string;
    status_layers?: StatusLayers;
    text: string;
    detail: string;
  };
  session: {
    session_id: string;
    request: string;
    raw_message: string;
    created_at: string;
    session_dir: string;
    artifact_dir: string;
    state_root: string;
    repo_root: string;
    project_root: string;
  };
  state: Record<string, unknown> & {
    current_state?: string;
    current_stage?: string;
    workflow_status?: string;
    status_layers?: StatusLayers;
    blocked_reason?: string;
    artifact_paths?: Record<string, string>;
    steps?: WorkflowStep[];
  };
  operator: {
    current_action: string;
    next_action: string;
    blocked_reason: string;
    latest_event: RuntimeEvent | null;
  };
  evidence: {
    required: string[];
    provided: string[];
    pending: string[];
    acceptance_criteria: string[];
    unresolved_items: string[];
  };
  artifacts: Artifact[];
  prompts: PromptTrace[];
  agent_runs: AgentRun[];
  tool_calls: ToolCall[];
  events: RuntimeEvent[];
};

export type TextPayload<T> = T & { content: string };

export async function fetchConsoleSnapshot(): Promise<ConsoleSnapshot> {
  return fetchJson<ConsoleSnapshot>("/api/console/snapshot");
}

export async function fetchSessionDetail(sessionId: string): Promise<PanelSnapshot> {
  const payload = await fetchJson<{ snapshot: PanelSnapshot }>(`/api/sessions/${encodeURIComponent(sessionId)}`);
  return payload.snapshot;
}

export async function fetchPromptContent(sessionId: string, promptId: string): Promise<TextPayload<{ prompt: PromptTrace }>> {
  return fetchJson<TextPayload<{ prompt: PromptTrace }>>(
    `/api/sessions/${encodeURIComponent(sessionId)}/prompts/${encodeURIComponent(promptId)}`
  );
}

export async function fetchArtifactContent(sessionId: string, artifactName: string): Promise<TextPayload<{ artifact: Artifact }>> {
  return fetchJson<TextPayload<{ artifact: Artifact }>>(
    `/api/sessions/${encodeURIComponent(sessionId)}/artifacts/${encodeURIComponent(artifactName)}`
  );
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}`);
  }
  return (await response.json()) as T;
}
