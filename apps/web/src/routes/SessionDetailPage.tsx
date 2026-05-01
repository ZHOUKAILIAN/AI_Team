import { useEffect, useState } from "react";

import { StagePill } from "../components/StagePill";
import { messages, type Language } from "../i18n/messages";
import { fetchSessionDetail, type ConsoleSnapshot, type PanelSnapshot } from "../lib/api";

type Props = {
  snapshot: ConsoleSnapshot;
  projectId: string;
  sessionId: string;
  language: Language;
  onBack: () => void;
};

const flow = ["Intake", "Product", "Dev", "QA", "Acceptance", "WaitForHumanDecision", "Done"];

export function SessionDetailPage({ snapshot, projectId, sessionId, language, onBack }: Props) {
  const t = messages[language];
  const [detail, setDetail] = useState<PanelSnapshot | null>(null);
  const [error, setError] = useState("");
  const project = snapshot.projects.find((item) => item.project_id === projectId);
  const summary = project?.sessions.find((session) => session.session_id === sessionId);

  useEffect(() => {
    fetchSessionDetail(sessionId)
      .then((payload) => {
        setDetail(payload);
        setError("");
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      });
  }, [sessionId]);

  const request = detail?.session.request ?? summary?.request ?? sessionId;
  const currentState = String(detail?.state.current_state ?? summary?.current_state ?? "");
  const currentStage = String(detail?.state.current_stage ?? summary?.current_stage ?? "");

  return (
    <main>
      <nav className="mb-4 flex items-center gap-2 text-sm text-console-muted">
        <button type="button" className="min-h-10 rounded-full border border-console-line bg-console-surface px-3" onClick={onBack}>
          {t.projectWorkbench}
        </button>
        <span>/</span>
        <span className="rounded-full bg-console-ink px-3 py-2 text-console-surface">{t.sessionDetail}</span>
      </nav>

      {error ? <div className="mb-4 rounded-2xl border border-red-200 bg-red-50 p-4 text-console-red">{error}</div> : null}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(340px,.95fr)]">
        <div className="rounded-[22px] border border-console-line bg-console-surface/90 p-5 shadow-console">
          <p className="text-sm text-console-muted">{project?.project_name ?? projectId} · {currentStage}</p>
          <h1 className="mt-3 text-4xl font-black leading-tight md:text-6xl">{request}</h1>
          <div className="mt-5 grid gap-4 rounded-2xl border border-console-line bg-white p-4">
            <h2 className="text-xl font-black">{t.request}</h2>
            <p className="leading-8 text-console-muted">{detail?.session.raw_message || request}</p>
          </div>
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
            <h2 className="font-black text-amber-950">{t.currentAction}</h2>
            <p className="mt-2 leading-7 text-amber-900">{detail?.operator.current_action ?? ""}</p>
            <p className="mt-2 leading-7 text-amber-900">{detail?.operator.next_action ?? ""}</p>
          </div>
        </div>

        <div className="grid content-start gap-4">
          <section className="rounded-[22px] border border-console-line bg-console-surface/90 p-4 shadow-console">
            <h2 className="mb-3 text-xl font-black">{t.flow}</h2>
            <div className="grid gap-2">
              {flow.map((stage, index) => {
                const reached = index <= currentFlowIndex(currentState, currentStage);
                const active = stage === currentState || stage === currentStage;
                return (
                  <div key={stage} className={`grid grid-cols-[2.5rem_minmax(0,1fr)_auto] items-center gap-3 rounded-2xl border p-3 ${active ? "border-console-amber bg-amber-50" : "border-console-line bg-white"}`}>
                    <div className={`grid h-9 w-9 place-items-center rounded-xl font-black ${active ? "bg-console-amber text-white" : reached ? "bg-emerald-100 text-console-green" : "bg-console-canvas text-console-muted"}`}>
                      {index + 1}
                    </div>
                    <div>
                      <strong>{t.stages[stage as keyof typeof t.stages] ?? stage}</strong>
                      <span className="block text-xs text-console-muted">{stage}</span>
                    </div>
                    {active ? <StagePill status="in_progress" label={t.current} /> : null}
                  </div>
                );
              })}
            </div>
          </section>

          <section className="rounded-[22px] border border-console-line bg-console-surface/90 p-4 shadow-console">
            <h2 className="mb-3 text-xl font-black">{t.evidence}</h2>
            <div className="flex flex-wrap gap-2">
              {(detail?.evidence.required ?? []).map((item) => (
                <span key={item} className={`rounded-full px-3 py-2 text-sm ${detail?.evidence.pending.includes(item) ? "bg-amber-100 text-amber-900" : "bg-emerald-100 text-console-green"}`}>
                  {item}
                </span>
              ))}
            </div>
          </section>

          <section className="rounded-[22px] border border-console-line bg-console-surface/90 p-4 shadow-console">
            <h2 className="mb-3 text-xl font-black">{t.artifacts}</h2>
            <div className="grid gap-2">
              {(detail?.artifacts ?? []).map((artifact) => (
                <div key={artifact.name} className="rounded-2xl border border-console-line bg-white p-3">
                  <strong className="block">{artifact.name}</strong>
                  <span className="block break-all text-xs text-console-muted">{artifact.path}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-[22px] border border-console-line bg-console-surface/90 p-4 shadow-console">
            <h2 className="mb-3 text-xl font-black">{t.events}</h2>
            <div className="grid gap-2 text-sm text-console-muted">
              {(detail?.events ?? []).slice(-8).reverse().map((event, index) => (
                <div key={`${event.kind}-${event.at}-${index}`} className="border-l-4 border-console-blue bg-white p-3">
                  <strong className="block text-console-ink">{event.kind}</strong>
                  <span>{event.message}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

function currentFlowIndex(currentState: string, currentStage: string) {
  const exactIndex = flow.indexOf(currentState);
  if (exactIndex >= 0) return exactIndex;
  const stageIndex = flow.indexOf(currentStage);
  if (stageIndex >= 0) return stageIndex;
  if (currentState === "ProductDraft" || currentState === "WaitForCEOApproval") return flow.indexOf("Product");
  if (currentState === "Implementation" || currentState === "CodeReview") return flow.indexOf("Dev");
  if (currentState === "QualityReview") return flow.indexOf("QA");
  return 0;
}
