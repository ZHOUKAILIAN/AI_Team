export type WorkflowStatus = "in_progress" | "waiting_human" | "blocked" | "done" | string;

export type RuntimeEvent = {
  kind?: string;
  stage?: string;
  state?: string;
  status?: string;
  message?: string;
  at?: string;
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
  blocked_reason: string;
  active_run: unknown;
  artifact_paths: Record<string, string>;
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
  };
  state: Record<string, unknown> & {
    current_state?: string;
    current_stage?: string;
    blocked_reason?: string;
    artifact_paths?: Record<string, string>;
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
  artifacts: Array<{ name: string; path: string; exists: boolean }>;
  events: RuntimeEvent[];
};

export async function fetchConsoleSnapshot(): Promise<ConsoleSnapshot> {
  return fetchJson<ConsoleSnapshot>("/api/console/snapshot");
}

export async function fetchSessionDetail(sessionId: string): Promise<PanelSnapshot> {
  const payload = await fetchJson<{ snapshot: PanelSnapshot }>(`/api/sessions/${encodeURIComponent(sessionId)}`);
  return payload.snapshot;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}`);
  }
  return (await response.json()) as T;
}
