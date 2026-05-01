import { useMemo, useState } from "react";

import { StagePill } from "../components/StagePill";
import { messages, type Language } from "../i18n/messages";
import type { ConsoleSnapshot, ProjectSummary } from "../lib/api";

type Props = {
  snapshot: ConsoleSnapshot;
  language: Language;
  searchQuery: string;
  onOpenProject: (projectId: string) => void;
};

type ProjectFilter = "all" | "blocked" | "waiting_human";

export function ProjectMapPage({ snapshot, language, searchQuery, onOpenProject }: Props) {
  const t = messages[language];
  const [selectedId, setSelectedId] = useState("");
  const [filter, setFilter] = useState<ProjectFilter>("all");
  const visibleProjects = useMemo(
    () => snapshot.projects.filter((project) => matchesProject(project, searchQuery) && matchesFilter(project, filter)),
    [filter, searchQuery, snapshot.projects]
  );
  const selected = useMemo(
    () => visibleProjects.find((project) => project.project_id === selectedId) ?? visibleProjects[0],
    [selectedId, visibleProjects]
  );

  return (
    <main className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_390px]">
      <section className="overflow-hidden rounded-[22px] border border-console-line bg-console-surface/85 shadow-console">
        <div className="flex flex-col justify-between gap-4 border-b border-console-line p-5 lg:flex-row">
          <div>
            <h1 className="text-5xl font-black leading-none tracking-normal md:text-7xl">{t.projectMap}</h1>
            <p className="mt-3 max-w-3xl leading-7 text-console-muted">{t.projectMapLead}</p>
          </div>
          <div className="grid min-w-48 gap-2 text-sm text-console-muted">
            <Legend color="bg-console-green" label={t.inProgress} />
            <Legend color="bg-console-amber" label={t.waitingHuman} />
            <Legend color="bg-console-red" label={t.blocked} />
          </div>
        </div>
        <div className="relative min-h-[640px] overflow-hidden bg-[radial-gradient(circle_at_50%_50%,rgba(13,118,110,.08),transparent_28rem)]">
          <div className="absolute left-[12%] top-[11%] h-[360px] w-[560px] -rotate-6 rounded-full border border-dashed border-console-ink/15" />
          <div className="absolute bottom-[12%] right-[8%] h-[280px] w-[440px] rotate-12 rounded-full border border-dashed border-console-ink/15" />
          {visibleProjects.map((project, index) => (
            <ProjectNode
              key={project.project_id}
              project={project}
              index={index}
              language={language}
              active={project.project_id === selected?.project_id}
              onSelect={() => setSelectedId(project.project_id)}
              onOpen={() => onOpenProject(project.project_id)}
            />
          ))}
          {visibleProjects.length === 0 ? (
            <div className="absolute inset-0 grid place-items-center p-6 text-center text-console-muted">
              <span className="rounded-2xl border border-console-line bg-console-surface px-5 py-4 shadow-console">{t.noMatches}</span>
            </div>
          ) : null}
          <div className="absolute bottom-5 left-5 flex flex-wrap gap-2">
            {([
              ["all", t.all],
              ["blocked", t.blocked],
              ["waiting_human", t.waitingHuman]
            ] as const).map(([value, label]) => (
              <button
                key={label}
                type="button"
                className={`min-h-10 rounded-full border px-3 text-sm ${filter === value ? "border-console-ink bg-console-ink text-console-surface" : "border-console-line bg-console-surface/85 text-console-muted"}`}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </section>
      <aside className="rounded-[22px] border border-console-line bg-console-surface/90 shadow-console">
        {selected ? (
          <div>
            <div className="border-b border-console-line p-5">
              <p className="text-xs text-console-muted">{t.projects}</p>
              <h2 className="mt-2 text-3xl font-black leading-tight">{selected.project_name}</h2>
              <p className="mt-3 break-all text-sm leading-6 text-console-muted">{selected.project_root || selected.project_id}</p>
            </div>
            <div className="grid gap-3 p-4">
              <MetricGrid project={selected} language={language} />
              <section className="rounded-2xl border border-console-line bg-white p-4">
                <h3 className="mb-3 font-bold">{t.sessions}</h3>
                <div className="grid gap-2">
                  {selected.sessions.slice(0, 4).map((session) => (
                    <button
                      type="button"
                      key={session.session_id}
                      className="rounded-2xl border border-console-line bg-console-surface p-3 text-left transition hover:-translate-y-0.5 hover:border-console-blue/40"
                      onClick={() => onOpenProject(selected.project_id)}
                    >
                      <strong className="block line-clamp-2 text-sm">{session.request}</strong>
                      <span className="mt-1 block text-xs text-console-muted">{session.current_stage}</span>
                    </button>
                  ))}
                </div>
              </section>
              <button
                type="button"
                className="min-h-12 rounded-2xl bg-console-ink px-4 font-bold text-console-surface"
                onClick={() => onOpenProject(selected.project_id)}
              >
                {t.openWorkbench}
              </button>
            </div>
          </div>
        ) : (
          <p className="p-5 text-console-muted">{t.noSessions}</p>
        )}
      </aside>
    </main>
  );
}

function ProjectNode({
  project,
  index,
  language,
  active,
  onSelect,
  onOpen
}: {
  project: ProjectSummary;
  index: number;
  language: Language;
  active: boolean;
  onSelect: () => void;
  onOpen: () => void;
}) {
  const t = messages[language];
  const positions = [
    "left-[14%] top-[18%]",
    "right-[18%] top-[18%]",
    "left-[38%] bottom-[18%]",
    "right-[10%] bottom-[20%]",
    "left-[8%] bottom-[14%]"
  ];
  const size = project.session_count > 6 ? "h-56 w-56" : project.session_count > 2 ? "h-44 w-44" : "h-36 w-36";
  const risk = project.blocked_count > 0 ? "blocked" : project.waiting_human_count > 0 ? "waiting_human" : "in_progress";
  return (
    <button
      type="button"
      className={`absolute ${positions[index % positions.length]} ${size} rounded-full border bg-console-surface p-4 text-center shadow-console transition hover:-translate-y-1 hover:scale-[1.02] ${active ? "border-console-green ring-4 ring-console-green/15" : "border-console-line"}`}
      onClick={onOpen}
      onFocus={onSelect}
      onMouseEnter={onSelect}
    >
      <span className="block text-lg font-black leading-tight">{project.project_name}</span>
      <span className="mt-2 block text-xs text-console-muted">
        {project.session_count} {t.sessionUnit} · {project.worktree_count} {t.worktreeUnit}
      </span>
      <span className="mt-3 inline-flex">
        <StagePill status={risk} label={projectRiskLabel(project, language)} />
      </span>
    </button>
  );
}

function matchesProject(project: ProjectSummary, searchQuery: string) {
  const query = searchQuery.trim().toLowerCase();
  if (!query) return true;
  const haystack = [
    project.project_name,
    project.project_root,
    ...project.sessions.flatMap((session) => [
      session.request,
      session.current_stage,
      session.current_state,
      session.branch,
      session.workflow_status
    ])
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function matchesFilter(project: ProjectSummary, filter: ProjectFilter) {
  if (filter === "blocked") return project.blocked_count > 0;
  if (filter === "waiting_human") return project.waiting_human_count > 0;
  return true;
}

function projectRiskLabel(project: ProjectSummary, language: Language) {
  const t = messages[language];
  if (project.blocked_count > 0) return `${project.blocked_count} ${t.blocked}`;
  if (project.waiting_human_count > 0) return `${project.waiting_human_count} ${t.waitingHuman}`;
  return `${project.active_count} ${t.active}`;
}

function MetricGrid({ project, language }: { project: ProjectSummary; language: Language }) {
  const t = messages[language];
  return (
    <div className="grid grid-cols-3 gap-2">
      <Metric label={t.worktrees} value={project.worktree_count} />
      <Metric label={t.sessions} value={project.session_count} />
      <Metric label={t.blocked} value={project.blocked_count} />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-console-line bg-white p-3">
      <span className="block text-xs text-console-muted">{label}</span>
      <b className="mt-1 block text-2xl tabular-nums">{value}</b>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`h-2.5 w-2.5 rounded-full ${color}`} />
      <span>{label}</span>
    </div>
  );
}
