import { useEffect, useMemo, useState } from "react";

import { StagePill } from "../components/StagePill";
import { messages, type Language } from "../i18n/messages";
import {
  fetchArtifactContent,
  fetchPromptContent,
  fetchSessionDetail,
  type AgentRun,
  type Artifact,
  type ConsoleSnapshot,
  type PanelSnapshot,
  type PromptTrace,
  type ToolCall,
  type WorkflowStep
} from "../lib/api";

type Props = {
  snapshot: ConsoleSnapshot;
  projectId: string;
  sessionId: string;
  language: Language;
  onBack: () => void;
};

type ContentPreview = {
  title: string;
  content: string;
};

// SessionDetailPage：展示单个 session 的 workflow、prompt、artifact、tool call 和事件明细。
// SessionDetailPage: shows one session's workflow, prompts, artifacts, tool calls, and events.
export function SessionDetailPage({ snapshot, projectId, sessionId, language, onBack }: Props) {
  const t = messages[language];
  const [detail, setDetail] = useState<PanelSnapshot | null>(null);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<ContentPreview | null>(null);
  const project = snapshot.projects.find((item) => item.project_id === projectId);
  const summary = project?.sessions.find((session) => session.session_id === sessionId);

  // 根据 sessionId 拉取详情，并把错误同步到页面状态。
  // Fetches detail by sessionId and mirrors errors into page state.
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
  const steps = useMemo(() => detail?.state.steps ?? [], [detail?.state.steps]);
  const currentStage = String(detail?.state.current_stage ?? summary?.current_stage ?? "");

  // 打开 prompt 预览弹层，显示实际发送给 runner 的 prompt.md。
  // Opens the prompt preview modal with the actual prompt.md sent to the runner.
  const openPrompt = (prompt: PromptTrace) => {
    fetchPromptContent(sessionId, prompt.prompt_id)
      .then((payload) => setPreview({ title: `${prompt.role} / ${prompt.prompt_id}`, content: payload.content }))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  };

  // 打开 artifact 预览弹层，显示阶段产物正文。
  // Opens the artifact preview modal with stage artifact content.
  const openArtifact = (artifact: Artifact) => {
    fetchArtifactContent(sessionId, artifact.name)
      .then((payload) => setPreview({ title: artifact.name, content: payload.content }))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  };

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

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.02fr)_minmax(360px,.98fr)]">
        <div className="grid content-start gap-4">
          <section className="rounded-[22px] border border-console-line bg-console-surface/90 p-5 shadow-console">
            <p className="text-sm text-console-muted">{project?.project_name ?? projectId} · {currentStage}</p>
            <h1 className="mt-3 text-4xl font-black leading-tight md:text-6xl">{request}</h1>
            <div className="mt-5 grid gap-3 rounded-2xl border border-console-line bg-white p-4">
              <h2 className="text-xl font-black">{t.request}</h2>
              <p className="break-words leading-8 text-console-muted">{detail?.session.raw_message || request}</p>
              <div className="grid gap-1 text-xs text-console-muted">
                <span className="break-all">repo: {detail?.session.repo_root ?? summary?.worktree_path ?? ""}</span>
                <span className="break-all">state: {detail?.session.state_root ?? summary?.state_root ?? ""}</span>
              </div>
            </div>
            <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
              <h2 className="font-black text-amber-950">{t.currentAction}</h2>
              <p className="mt-2 leading-7 text-amber-900">{detail?.operator.current_action ?? ""}</p>
              <p className="mt-2 leading-7 text-amber-900">{detail?.operator.next_action ?? ""}</p>
            </div>
          </section>

          <section className="rounded-[22px] border border-console-line bg-console-surface/90 p-4 shadow-console">
            <h2 className="mb-3 text-xl font-black">{t.traceLedger}</h2>
            <div className="grid gap-2">
              {steps.map((step, index) => (
                <StepRow
                  key={`${step.role}-${index}`}
                  step={step}
                  index={index}
                  active={step.role === currentStage}
                  language={language}
                />
              ))}
            </div>
          </section>

          <section className="rounded-[22px] border border-console-line bg-console-surface/90 p-4 shadow-console">
            <h2 className="mb-3 text-xl font-black">{t.agentRuns}</h2>
            <div className="grid gap-2">
              {(detail?.agent_runs ?? []).map((run) => (
                <AgentRunCard key={run.agent_run_id} run={run} language={language} />
              ))}
            </div>
          </section>
        </div>

        <div className="grid content-start gap-4">
          <section className="rounded-[22px] border border-console-line bg-console-surface/90 p-4 shadow-console">
            <h2 className="mb-3 text-xl font-black">{t.prompts}</h2>
            <div className="grid gap-2">
              {(detail?.prompts ?? []).map((prompt) => (
                <button
                  type="button"
                  key={prompt.prompt_id}
                  className="rounded-2xl border border-console-line bg-white p-3 text-left transition hover:-translate-y-0.5 hover:border-console-blue/40"
                  onClick={() => openPrompt(prompt)}
                >
                  <strong className="block">{prompt.role}</strong>
                  <span className="mt-1 block break-all text-xs text-console-muted">{prompt.prompt_id}</span>
                  <span className="mt-2 block text-xs text-console-muted">{prompt.bytes} bytes · {prompt.runner ?? ""}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-[22px] border border-console-line bg-console-surface/90 p-4 shadow-console">
            <h2 className="mb-3 text-xl font-black">{t.toolCalls}</h2>
            <div className="grid gap-2">
              {(detail?.tool_calls ?? []).map((call, index) => (
                <ToolCallCard key={`${call.agent_run_id}-${call.kind}-${call.at}-${index}`} call={call} />
              ))}
            </div>
          </section>

          <section className="rounded-[22px] border border-console-line bg-console-surface/90 p-4 shadow-console">
            <h2 className="mb-3 text-xl font-black">{t.artifacts}</h2>
            <div className="grid gap-2">
              {(detail?.artifacts ?? []).map((artifact) => (
                <button
                  type="button"
                  key={`${artifact.name}-${artifact.path}`}
                  className="rounded-2xl border border-console-line bg-white p-3 text-left transition hover:-translate-y-0.5 hover:border-console-blue/40"
                  onClick={() => artifact.role ? openArtifact(artifact) : setPreview({ title: artifact.name, content: artifact.path })}
                >
                  <strong className="block">{artifact.name}</strong>
                  <span className="mt-1 block break-all text-xs text-console-muted">{artifact.path}</span>
                  {artifact.role ? <span className="mt-2 block text-xs text-console-muted">{artifact.role} · {artifact.bytes ?? 0} bytes</span> : null}
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-[22px] border border-console-line bg-console-surface/90 p-4 shadow-console">
            <h2 className="mb-3 text-xl font-black">{t.events}</h2>
            <div className="grid gap-2 text-sm text-console-muted">
              {(detail?.events ?? []).slice(-10).reverse().map((event, index) => (
                <div key={`${event.kind}-${event.at}-${index}`} className="border-l-4 border-console-blue bg-white p-3">
                  <strong className="block text-console-ink">{event.kind}</strong>
                  <span>{event.role ? `${event.role} · ` : ""}{event.message}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </section>

      {preview ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-console-ink/35 p-4" role="dialog" aria-modal="true">
          <section className="max-h-[86dvh] w-[min(960px,calc(100vw-2rem))] overflow-hidden rounded-[22px] border border-console-line bg-console-surface shadow-console">
            <div className="flex items-center justify-between gap-3 border-b border-console-line p-4">
              <h2 className="truncate text-xl font-black">{preview.title}</h2>
              <button type="button" className="min-h-10 rounded-full bg-console-ink px-4 text-console-surface" onClick={() => setPreview(null)}>
                Close
              </button>
            </div>
            <pre className="max-h-[70dvh] overflow-auto whitespace-pre-wrap break-words bg-white p-4 text-xs leading-6 text-console-ink">
              {preview.content}
            </pre>
          </section>
        </div>
      ) : null}
    </main>
  );
}

// StepRow：渲染 trace ledger 中的一个 workflow step。
// StepRow: renders one workflow step in the trace ledger.
function StepRow({ step, index, active, language }: { step: WorkflowStep; index: number; active: boolean; language: Language }) {
  return (
    <div className={`grid grid-cols-[2.5rem_minmax(0,1fr)_auto] items-start gap-3 rounded-2xl border p-3 ${active ? "border-console-amber bg-amber-50" : "border-console-line bg-white"}`}>
      <div className={`grid h-9 w-9 place-items-center rounded-xl font-black ${active ? "bg-console-amber text-white" : step.status === "completed" ? "bg-emerald-100 text-console-green" : "bg-console-canvas text-console-muted"}`}>
        {index + 1}
      </div>
      <div className="min-w-0">
        <strong>{roleLabel(step.role, language)}</strong>
        <span className="mt-1 block break-all text-xs text-console-muted">{step.role}</span>
        {step.summary ? <p className="mt-2 line-clamp-2 text-sm text-console-muted">{step.summary}</p> : null}
        {step.prompt_trace_id || step.agent_run_id || step.artifact_path ? (
          <div className="mt-2 grid gap-1 text-xs text-console-muted">
            {step.prompt_trace_id ? <span className="break-all">prompt: {step.prompt_trace_id}</span> : null}
            {step.agent_run_id ? <span className="break-all">run: {step.agent_run_id}</span> : null}
            {step.artifact_path ? <span className="break-all">artifact: {step.artifact_path}</span> : null}
          </div>
        ) : null}
      </div>
      <StagePill status={statusForPill(step.status)} label={step.status} />
    </div>
  );
}

// AgentRunCard：渲染一个 agent run 的输入、输出和 metadata。
// AgentRunCard: renders input, output, and metadata for one agent run.
function AgentRunCard({ run, language }: { run: AgentRun; language: Language }) {
  return (
    <details className="rounded-2xl border border-console-line bg-white p-3">
      <summary className="cursor-pointer list-none">
        <strong className="block">{roleLabel(run.role, language)} · {run.runner}</strong>
        <span className="mt-1 block break-all text-xs text-console-muted">{run.agent_run_id} · {run.status}</span>
      </summary>
      <div className="mt-3 grid gap-3 text-xs">
        <TraceBlock label="input" value={run.input} />
        <TraceBlock label="output" value={run.output || run.error || ""} />
        {run.metadata ? <TraceBlock label="metadata" value={JSON.stringify(run.metadata, null, 2)} /> : null}
      </div>
    </details>
  );
}

// ToolCallCard：渲染一个 tool call 的输入和输出。
// ToolCallCard: renders input and output for one tool call.
function ToolCallCard({ call }: { call: ToolCall }) {
  return (
    <details className="rounded-2xl border border-console-line bg-white p-3">
      <summary className="cursor-pointer list-none">
        <strong className="block">{call.kind} · {call.name}</strong>
        <span className="mt-1 block break-all text-xs text-console-muted">{call.role} · {call.agent_run_id}</span>
      </summary>
      <div className="mt-3 grid gap-3 text-xs">
        <TraceBlock label="input" value={JSON.stringify(call.input ?? {}, null, 2)} />
        <TraceBlock label="output" value={JSON.stringify(call.output ?? {}, null, 2)} />
      </div>
    </details>
  );
}

// TraceBlock：以可滚动 pre 区块展示长文本 trace 内容。
// TraceBlock: displays long trace text in a scrollable pre block.
function TraceBlock({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="mb-1 block font-bold uppercase tracking-normal text-console-muted">{label}</span>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-console-canvas p-3 leading-6 text-console-ink">
        {value || "(empty)"}
      </pre>
    </div>
  );
}

// 将 step status 映射到 StagePill 支持的状态类别。
// Maps a step status into the status category supported by StagePill.
function statusForPill(status: string) {
  if (status === "blocked") return "blocked";
  if (status === "completed") return "done";
  return "in_progress";
}

// 根据语言把内部 role 名转换为可读标签。
// Converts an internal role name into a readable label for the selected language.
function roleLabel(role: string, language: Language) {
  const zh: Record<string, string> = {
    planner: "规划",
    repo_scout: "仓库扫描",
    test_scout: "测试扫描",
    writer: "实现",
    verifier: "验证",
    summarizer: "总结",
    route: "路由",
    product_definition: "产品定义",
    project_runtime: "项目运行态",
    technical_design: "技术设计",
    implementation: "实现",
    verification: "验证",
    governance_review: "治理审查",
    acceptance: "验收",
    session_handoff: "接力"
  };
  const en: Record<string, string> = {
    planner: "Planner",
    repo_scout: "Repo Scout",
    test_scout: "Test Scout",
    writer: "Writer",
    verifier: "Verifier",
    summarizer: "Summarizer",
    route: "Route",
    product_definition: "Product Definition",
    project_runtime: "Project Runtime",
    technical_design: "Technical Design",
    implementation: "Implementation",
    verification: "Verification",
    governance_review: "Governance Review",
    acceptance: "Acceptance",
    session_handoff: "Session Handoff"
  };
  return (language === "zh" ? zh : en)[role] ?? role;
}
