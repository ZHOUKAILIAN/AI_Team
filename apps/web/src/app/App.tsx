import { Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { LanguageSwitch } from "../components/LanguageSwitch";
import { SocketIndicator } from "../components/SocketIndicator";
import { messages, type Language } from "../i18n/messages";
import { fetchConsoleSnapshot, type ConsoleSnapshot } from "../lib/api";
import { useRuntimeSocket } from "../lib/socket";
import { ProjectMapPage } from "../routes/ProjectMapPage";
import { ProjectWorkbenchPage } from "../routes/ProjectWorkbenchPage";
import { SessionDetailPage } from "../routes/SessionDetailPage";

type RouteState =
  | { name: "projects" }
  | { name: "project"; projectId: string }
  | { name: "session"; projectId: string; sessionId: string };

const defaultSnapshot: ConsoleSnapshot = {
  generated_at: "",
  stats: { projects: 0, worktrees: 0, sessions: 0, active: 0, waiting_human: 0, blocked: 0 },
  projects: []
};

export function App() {
  const [language, setLanguage] = useState<Language>(() => readLanguage());
  const [route, setRoute] = useState<RouteState>(() => parseRoute(window.location.pathname));
  const [snapshot, setSnapshot] = useState<ConsoleSnapshot>(defaultSnapshot);
  const [searchQuery, setSearchQuery] = useState("");
  const [error, setError] = useState("");
  const t = messages[language];

  const reloadSnapshot = useCallback(() => {
    fetchConsoleSnapshot()
      .then((payload) => {
        setSnapshot(payload);
        setError("");
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      });
  }, []);

  const socketState = useRuntimeSocket(reloadSnapshot);

  useEffect(() => {
    reloadSnapshot();
  }, [reloadSnapshot]);

  useEffect(() => {
    window.localStorage.setItem("agent-team-console-language", language);
  }, [language]);

  useEffect(() => {
    const onPopState = () => setRoute(parseRoute(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const socketLabel = useMemo(() => {
    if (socketState === "connected") return t.connected;
    if (socketState === "connecting") return t.connecting;
    if (socketState === "fallback") return t.fallback;
    return t.disconnected;
  }, [socketState, t]);

  const navigate = (nextRoute: RouteState) => {
    const path = routeToPath(nextRoute);
    window.history.pushState(null, "", path);
    setRoute(nextRoute);
  };

  return (
    <div className="min-h-dvh bg-console-canvas bg-[linear-gradient(90deg,rgba(22,32,38,.045)_1px,transparent_1px),linear-gradient(0deg,rgba(22,32,38,.045)_1px,transparent_1px)] bg-[size:30px_30px] text-console-ink">
      <div className="mx-auto w-[min(1440px,calc(100vw-28px))] py-4 pb-28 lg:pb-8">
        <header className="sticky top-3 z-30 mb-4 flex flex-col gap-3 rounded-2xl border border-console-line/80 bg-console-surface/90 p-3 shadow-console backdrop-blur lg:flex-row lg:items-center lg:justify-between">
          <button
            type="button"
            className="flex min-h-12 min-w-0 items-center gap-3 rounded-xl text-left"
            onClick={() => navigate({ name: "projects" })}
          >
            <span className="relative h-11 w-11 shrink-0 rounded-2xl bg-[conic-gradient(from_160deg,#0d766e,#255f86,#c3861a,#0d766e)] shadow-lg after:absolute after:inset-3 after:rounded-full after:border-2 after:border-white/80" />
            <span className="min-w-0">
              <span className="block truncate font-black leading-tight">{t.brand}</span>
              <span className="block truncate text-xs text-console-muted">{t.brandSub}</span>
            </span>
          </button>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
            <label className="relative block min-w-[220px] sm:w-80">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-console-muted" aria-hidden="true" />
              <input
                className="min-h-11 w-full rounded-2xl border border-console-line bg-console-surface py-2 pl-10 pr-3 text-sm"
                placeholder={t.search}
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </label>
            <SocketIndicator state={socketState} label={socketLabel} />
            <LanguageSwitch language={language} onChange={setLanguage} />
          </div>
        </header>

        {error ? (
          <div className="mb-4 rounded-2xl border border-red-200 bg-red-50 p-4 text-console-red">{error}</div>
        ) : null}

        {route.name === "projects" ? (
          <ProjectMapPage
            snapshot={snapshot}
            language={language}
            searchQuery={searchQuery}
            onOpenProject={(projectId) => navigate({ name: "project", projectId })}
          />
        ) : null}
        {route.name === "project" ? (
          <ProjectWorkbenchPage
            snapshot={snapshot}
            projectId={route.projectId}
            language={language}
            searchQuery={searchQuery}
            onBack={() => navigate({ name: "projects" })}
            onOpenSession={(sessionId) => navigate({ name: "session", projectId: route.projectId, sessionId })}
          />
        ) : null}
        {route.name === "session" ? (
          <SessionDetailPage
            snapshot={snapshot}
            projectId={route.projectId}
            sessionId={route.sessionId}
            language={language}
            onBack={() => navigate({ name: "project", projectId: route.projectId })}
          />
        ) : null}
      </div>

      <nav className="fixed bottom-3 left-3 right-3 z-40 grid grid-cols-3 gap-2 rounded-2xl border border-console-line bg-console-surface/95 p-2 shadow-console backdrop-blur lg:hidden" aria-label="Mobile navigation">
        <button className={mobileNavClass(route.name === "projects")} type="button" onClick={() => navigate({ name: "projects" })}>
          {t.projects}
        </button>
        <button
          className={mobileNavClass(route.name === "project")}
          type="button"
          onClick={() => navigate({ name: "project", projectId: snapshot.projects[0]?.project_id ?? "missing" })}
        >
          {t.projectWorkbench}
        </button>
        <button className={mobileNavClass(route.name === "session")} type="button">
          {t.sessionDetail}
        </button>
      </nav>
    </div>
  );
}

function readLanguage(): Language {
  const value = window.localStorage.getItem("agent-team-console-language");
  return value === "en" ? "en" : "zh";
}

function parseRoute(pathname: string): RouteState {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "projects" && parts[1] && parts[2] === "sessions" && parts[3]) {
    return { name: "session", projectId: parts[1], sessionId: parts[3] };
  }
  if (parts[0] === "projects" && parts[1]) {
    return { name: "project", projectId: parts[1] };
  }
  return { name: "projects" };
}

function routeToPath(route: RouteState): string {
  if (route.name === "project") return `/projects/${route.projectId}`;
  if (route.name === "session") return `/projects/${route.projectId}/sessions/${route.sessionId}`;
  return "/projects";
}

function mobileNavClass(active: boolean) {
  return [
    "min-h-11 rounded-xl px-2 text-sm font-semibold",
    active ? "bg-console-ink text-console-surface" : "text-console-muted"
  ].join(" ");
}
