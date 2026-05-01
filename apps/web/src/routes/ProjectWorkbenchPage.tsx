import { StagePill } from "../components/StagePill";
import { messages, type Language } from "../i18n/messages";
import type { ConsoleSnapshot, ProjectSummary, SessionSummary } from "../lib/api";
import { useState } from "react";

type Props = {
  snapshot: ConsoleSnapshot;
  projectId: string;
  language: Language;
  searchQuery: string;
  onBack: () => void;
  onOpenSession: (sessionId: string) => void;
};

const laneStages = ["Intake", "Product", "Dev", "QA", "Acceptance"];
type SessionFilter = "all" | "waiting_human" | "blocked" | "in_progress";

export function ProjectWorkbenchPage({ snapshot, projectId, language, searchQuery, onBack, onOpenSession }: Props) {
  const t = messages[language];
  const [filter, setFilter] = useState<SessionFilter>("all");
  const project = snapshot.projects.find((item) => item.project_id === projectId) ?? snapshot.projects[0];

  if (!project) {
    return <EmptyState message={t.noSessions} onBack={onBack} label={t.backToProjects} />;
  }

  return (
    <main>
      <nav className="mb-4 flex items-center gap-2 text-sm text-console-muted">
        <button type="button" className="min-h-10 rounded-full border border-console-line bg-console-surface px-3" onClick={onBack}>
          {t.backToProjects}
        </button>
        <span>/</span>
        <span className="rounded-full bg-console-ink px-3 py-2 text-console-surface">{project.project_name}</span>
      </nav>

      <section className="mb-4 grid gap-4 rounded-[22px] border border-console-line bg-console-surface/90 p-5 shadow-console lg:grid-cols-[minmax(0,1fr)_460px]">
        <div>
          <h1 className="text-5xl font-black leading-none md:text-7xl">{t.projectWorkbench}</h1>
          <p className="mt-3 max-w-3xl leading-7 text-console-muted">{t.workbenchLead}</p>
        </div>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          <Metric label={t.worktrees} value={project.worktree_count} />
          <Metric label={t.sessions} value={project.session_count} />
          <Metric label={t.active} value={project.active_count} />
          <Metric label={t.waitingHuman} value={project.waiting_human_count} />
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_390px]">
        <div className="overflow-hidden rounded-[22px] border border-console-line bg-console-surface/90 shadow-console">
          <div className="flex flex-col justify-between gap-3 border-b border-console-line p-4 lg:flex-row lg:items-center">
            <h2 className="text-2xl font-black">{t.sessions}</h2>
            <div className="flex flex-wrap gap-2">
              {([
                ["all", t.all],
                ["waiting_human", t.needsHuman],
                ["blocked", t.blocked],
                ["in_progress", t.inProgress]
              ] as const).map(([value, label]) => (
                <button
                  key={label}
                  type="button"
                  className={`min-h-10 rounded-full border px-3 text-sm ${filter === value ? "border-console-ink bg-console-ink text-console-surface" : "border-console-line bg-white text-console-muted"}`}
                  onClick={() => setFilter(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-3 overflow-x-auto p-4 lg:grid-cols-5">
            {laneStages.map((stage) => (
              <StageLane
                key={stage}
                stage={stage}
                project={project}
                language={language}
                searchQuery={searchQuery}
                filter={filter}
                onOpenSession={onOpenSession}
              />
            ))}
          </div>
        </div>
        <aside className="grid content-start gap-3 rounded-[22px] border border-console-line bg-console-surface/90 p-4 shadow-console">
          <section className="rounded-2xl border border-console-line bg-white p-4">
            <h3 className="mb-3 font-bold">{t.currentAction}</h3>
            <p className="rounded-2xl border border-amber-200 bg-amber-50 p-3 leading-7 text-amber-900">
              {currentAction(project, language)}
            </p>
          </section>
          <section className="rounded-2xl border border-console-line bg-white p-4">
            <h3 className="mb-3 font-bold">{t.worktreeContext}</h3>
            <div className="grid gap-2">
              {project.worktrees.map((worktree) => (
                <div key={worktree.state_root} className="rounded-2xl border border-console-line bg-console-surface p-3 text-sm">
                  <strong className="block break-all">{worktree.branch || worktree.worktree_path || worktree.state_root}</strong>
                  <span className="mt-1 block text-console-muted">
                    {worktree.session_count} {t.sessions} · {worktree.active_count} {t.active}
                  </span>
                </div>
              ))}
            </div>
          </section>
          <section className="rounded-2xl border border-console-line bg-white p-4">
            <h3 className="mb-3 font-bold">{t.recentEvents}</h3>
            <div className="grid gap-2 text-sm text-console-muted">
              {project.sessions.slice(0, 4).map((session) => (
                <div key={session.session_id} className="border-l-4 border-console-blue bg-console-canvas p-2">
                  {session.current_stage} · {session.request}
                </div>
              ))}
            </div>
          </section>
        </aside>
      </section>
    </main>
  );
}

function StageLane({
  stage,
  project,
  language,
  searchQuery,
  filter,
  onOpenSession
}: {
  stage: string;
  project: ProjectSummary;
  language: Language;
  searchQuery: string;
  filter: SessionFilter;
  onOpenSession: (sessionId: string) => void;
}) {
  const t = messages[language];
  const sessions = project.sessions.filter(
    (session) =>
      normalizedStage(session.current_stage, session.current_state) === stage &&
      matchesSession(session, searchQuery) &&
      matchesSessionFilter(session, filter)
  );
  return (
    <section className="min-w-52 rounded-2xl border border-console-line bg-console-canvas p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <strong>{t.stages[stage as keyof typeof t.stages] ?? stage}</strong>
        <span className="rounded-full border border-console-line bg-white px-2 py-1 text-xs text-console-muted">{sessions.length}</span>
      </div>
      <div className="grid gap-2">
        {sessions.map((session) => (
          <SessionCard key={session.session_id} session={session} language={language} onOpen={() => onOpenSession(session.session_id)} />
        ))}
      </div>
    </section>
  );
}

function matchesSession(session: SessionSummary, searchQuery: string) {
  const query = searchQuery.trim().toLowerCase();
  if (!query) return true;
  return [
    session.request,
    session.current_stage,
    session.current_state,
    session.branch,
    session.workflow_status,
    session.blocked_reason
  ]
    .join(" ")
    .toLowerCase()
    .includes(query);
}

function matchesSessionFilter(session: SessionSummary, filter: SessionFilter) {
  if (filter === "all") return true;
  return session.workflow_status === filter;
}

function SessionCard({ session, language, onOpen }: { session: SessionSummary; language: Language; onOpen: () => void }) {
  const t = messages[language];
  return (
    <button type="button" className="rounded-2xl border border-console-line bg-white p-3 text-left transition hover:-translate-y-1 hover:border-console-blue/40 hover:shadow-lg" onClick={onOpen}>
      <strong className="block line-clamp-3 text-sm leading-5">{session.request}</strong>
      <span className="mt-2 block text-xs text-console-muted">{session.current_state}</span>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-console-canvas">
        <span className="block h-full rounded-full bg-gradient-to-r from-console-green via-console-blue to-console-amber" style={{ width: progressFor(session) }} />
      </div>
      <span className="mt-3 inline-flex">
        <StagePill status={session.workflow_status} label={statusLabel(session.workflow_status, t)} />
      </span>
    </button>
  );
}

function normalizedStage(stage: string, state: string) {
  if (state === "Done") return "Acceptance";
  if (state === "WaitForHumanDecision") return "Acceptance";
  if (state === "WaitForCEOApproval") return "Product";
  if (["Intake", "Product", "Dev", "QA", "Acceptance"].includes(stage)) return stage;
  if (["Intake", "ProductDraft"].includes(state)) return "Intake";
  return "Dev";
}

function statusLabel(status: string, t: typeof messages.zh | typeof messages.en) {
  if (status === "blocked") return t.blocked;
  if (status === "waiting_human") return t.waitingHuman;
  if (status === "done") return t.done;
  return t.inProgress;
}

function progressFor(session: SessionSummary) {
  const stage = normalizedStage(session.current_stage, session.current_state);
  const index = laneStages.indexOf(stage);
  return `${Math.max(18, (index + 1) * 18)}%`;
}

function currentAction(project: ProjectSummary, language: Language) {
  const blocked = project.sessions.find((session) => session.workflow_status === "blocked");
  if (blocked) return language === "zh" ? `先处理阻塞：${blocked.blocked_reason || blocked.request}` : `Resolve blocker first: ${blocked.blocked_reason || blocked.request}`;
  const waiting = project.sessions.find((session) => session.workflow_status === "waiting_human");
  if (waiting) return language === "zh" ? `等待人工决策：${waiting.request}` : `Waiting for human decision: ${waiting.request}`;
  const active = project.sessions.find((session) => session.workflow_status === "in_progress");
  if (active) return language === "zh" ? `继续推进：${active.current_stage} / ${active.request}` : `Continue: ${active.current_stage} / ${active.request}`;
  return language === "zh" ? "当前项目暂无待处理动作。" : "No current action for this project.";
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-console-line bg-white p-3">
      <span className="block text-xs text-console-muted">{label}</span>
      <b className="mt-1 block text-2xl tabular-nums">{value}</b>
    </div>
  );
}

function EmptyState({ message, onBack, label }: { message: string; onBack: () => void; label: string }) {
  return (
    <div className="rounded-[22px] border border-console-line bg-console-surface p-8 shadow-console">
      <p className="text-console-muted">{message}</p>
      <button type="button" className="mt-4 min-h-12 rounded-2xl bg-console-ink px-4 font-bold text-console-surface" onClick={onBack}>
        {label}
      </button>
    </div>
  );
}
