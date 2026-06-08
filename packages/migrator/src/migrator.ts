import { existsSync } from "node:fs";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  RuntimeStore,
  type AgentRole,
  type RuntimeProfile,
  type RuntimeEvent,
  type SessionRecord,
  readJson,
  writeJson,
  nowIso,
} from "@agent-team-runtime/runtime";

export type MigrationOptions = {
  sourceRoot: string;
  targetStateRoot: string;
  apply: boolean;
};

export type MigrationItem = {
  source_session_id: string;
  source_dir: string;
  target_session_id: string;
  status: "complete" | "partial" | "skipped";
  reason: string;
};

export type MigrationReport = {
  source_root: string;
  target_state_root: string;
  dry_run: boolean;
  scanned: number;
  migrated: number;
  partial: number;
  skipped: number;
  items: MigrationItem[];
};

export async function migrateLegacySessions(options: MigrationOptions): Promise<MigrationReport> {
  const sourceRoot = path.resolve(options.sourceRoot);
  const targetStateRoot = path.resolve(options.targetStateRoot);
  const legacySessionDirs = await findLegacySessionDirs(sourceRoot);
  const report: MigrationReport = {
    source_root: sourceRoot,
    target_state_root: targetStateRoot,
    dry_run: !options.apply,
    scanned: legacySessionDirs.length,
    migrated: 0,
    partial: 0,
    skipped: 0,
    items: [],
  };

  const store = new RuntimeStore(targetStateRoot);
  if (options.apply) {
    await store.ensureLayout();
  }

  for (const sourceDir of legacySessionDirs) {
    const item = await migrateOne({ sourceRoot, sourceDir, store, apply: options.apply });
    report.items.push(item);
    if (item.status === "complete") {
      report.migrated += 1;
    } else if (item.status === "partial") {
      report.partial += 1;
    } else {
      report.skipped += 1;
    }
  }
  return report;
}

async function migrateOne(args: {
  sourceRoot: string;
  sourceDir: string;
  store: RuntimeStore;
  apply: boolean;
}): Promise<MigrationItem> {
  const sessionJson = path.join(args.sourceDir, "session.json");
  const summaryJson = path.join(args.sourceDir, "workflow_summary.json");
  if (!existsSync(sessionJson) && !existsSync(summaryJson)) {
    return {
      source_session_id: path.basename(args.sourceDir),
      source_dir: args.sourceDir,
      target_session_id: "",
      status: "skipped",
      reason: "Missing session.json and workflow_summary.json.",
    };
  }

  const legacySession = existsSync(sessionJson) ? safeObject(await readJson(sessionJson)) : {};
  const legacySummary = existsSync(summaryJson) ? safeObject(await readJson(summaryJson)) : {};
  const sourceSessionId = String(
    legacySession.session_id ?? legacySummary.session_id ?? path.basename(args.sourceDir),
  );
  const request = String(
    legacySession.request ?? legacySession.raw_message ?? legacySummary.request ?? `Migrated session ${sourceSessionId}`,
  );
  const status = mapStatus(String(legacySummary.current_state ?? ""));
  const targetSessionId = `migrated-${sourceSessionId}`;
  const partialReasons: string[] = [];

  if (!existsSync(sessionJson)) partialReasons.push("missing session.json");
  if (!existsSync(summaryJson)) partialReasons.push("missing workflow_summary.json");

  if (args.apply) {
    const targetDir = args.store.sessionDir(targetSessionId);
    await mkdir(path.join(targetDir, "agents"), { recursive: true });
    await mkdir(path.join(targetDir, "artifacts"), { recursive: true });
    const now = nowIso();
    const session: SessionRecord = {
      schema_version: 1,
      session_id: targetSessionId,
      request,
      profile: "full",
      status,
      project_root: String(legacySession.project_root ?? legacySession.repo_root ?? legacySession.worktree_path ?? args.sourceRoot),
      repo_root: String(legacySession.repo_root ?? legacySession.worktree_path ?? args.sourceRoot),
      state_root: args.store.stateRoot,
      created_at: String(legacySession.created_at ?? now),
      updated_at: String(legacySession.updated_at ?? legacySummary.updated_at ?? now),
      current_stage: String(legacySummary.current_stage ?? legacySummary.current_state ?? "migrated"),
      source: "migrated",
      prompt_trace_ids: [],
      migration: {
        source_root: args.sourceRoot,
        source_session_id: sourceSessionId,
        status: partialReasons.length ? "partial" : "complete",
      },
    };
    await args.store.writeSession(session);
    await args.store.writeWorkflow({
      schema_version: 1,
      session_id: targetSessionId,
      profile: "full" satisfies RuntimeProfile,
      status,
      current_stage: session.current_stage,
      steps: legacySteps(legacySummary),
      summary: String(legacySummary.summary ?? legacySummary.blocked_reason ?? ""),
      blocked_reason: String(legacySummary.blocked_reason ?? ""),
      files_changed: [],
      commands_run: [],
      updated_at: session.updated_at,
    });
    await writeJson(path.join(targetDir, "migration.json"), {
      source_root: args.sourceRoot,
      source_session_id: sourceSessionId,
      source_dir: args.sourceDir,
      status: partialReasons.length ? "partial" : "complete",
      partial_reasons: partialReasons,
      legacy: {
        session: legacySession,
        workflow_summary: legacySummary,
      },
    });
    await copyLegacyEvents(args.sourceDir, targetSessionId, args.store);
    await copyLegacyArtifacts(args.sourceDir, targetSessionId, args.store);
  }

  return {
    source_session_id: sourceSessionId,
    source_dir: args.sourceDir,
    target_session_id: targetSessionId,
    status: partialReasons.length ? "partial" : "complete",
    reason: partialReasons.join(", "),
  };
}

async function findLegacySessionDirs(sourceRoot: string): Promise<string[]> {
  const candidates = [
    path.join(sourceRoot, "_runtime", "sessions"),
    path.join(sourceRoot, ".agt", "_runtime", "sessions"),
    path.join(sourceRoot, ".agent-team", "_runtime", "sessions"),
  ];
  const dirs: string[] = [];
  for (const candidate of candidates) {
    if (!existsSync(candidate)) {
      continue;
    }
    for (const entry of await readdir(candidate, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        dirs.push(path.join(candidate, entry.name));
      }
    }
  }
  return [...new Set(dirs)].sort();
}

function legacySteps(summary: Record<string, unknown>) {
  const statuses = safeObject(summary.stage_statuses);
  return Object.entries(statuses).map(([role, status]) => ({
    role: normalizeLegacyRole(role),
    status: normalizeStepStatus(String(status)),
    prompt_trace_id: "",
    artifact_path: "",
    files_changed: [],
    commands_run: [],
    summary: "",
  }));
}

async function copyLegacyEvents(sourceDir: string, targetSessionId: string, store: RuntimeStore): Promise<void> {
  const sourceEvents = path.join(sourceDir, "events.jsonl");
  if (!existsSync(sourceEvents)) {
    return;
  }
  const text = await readFile(sourceEvents, "utf8");
  for (const line of text.split("\n")) {
    if (!line.trim()) {
      continue;
    }
    const legacy = safeObject(JSON.parse(line));
    const event: RuntimeEvent = {
      at: String(legacy.at ?? nowIso()),
      session_id: targetSessionId,
      kind: String(legacy.kind ?? "legacy_event"),
      role: normalizeLegacyRole(String(legacy.stage ?? legacy.role ?? "migration")),
      status: legacy.status === undefined ? undefined : String(legacy.status),
      message: String(legacy.message ?? ""),
      details: { legacy },
    };
    await store.appendEvent(event);
  }
}

async function copyLegacyArtifacts(sourceDir: string, targetSessionId: string, store: RuntimeStore): Promise<void> {
  for (const name of ["session.json", "workflow_summary.json"]) {
    const source = path.join(sourceDir, name);
    if (existsSync(source)) {
      await store.writeArtifact({
        sessionId: targetSessionId,
        role: "migration",
        name: `legacy-${name}`,
        content: await readFile(source, "utf8"),
        metadata: { source_path: source },
      });
    }
  }
  await store.writeArtifact({
    sessionId: targetSessionId,
    role: "migration",
    name: "legacy-source.txt",
    content: `${sourceDir}\n`,
  });
}

function mapStatus(currentState: string): "in_progress" | "waiting_human" | "blocked" | "done" {
  if (currentState === "Done") return "done";
  if (currentState.startsWith("WaitFor")) return "waiting_human";
  if (currentState === "Blocked") return "blocked";
  return "in_progress";
}

function normalizeStepStatus(status: string): "pending" | "running" | "completed" | "blocked" | "skipped" {
  if (["completed", "passed", "recommended_go", "approved"].includes(status)) return "completed";
  if (["blocked", "failed"].includes(status)) return "blocked";
  if (status === "skipped") return "skipped";
  return "pending";
}

function normalizeLegacyRole(value: string): AgentRole {
  const normalized = value.toLowerCase().replace(/[-_\s]/g, "");
  const map: Record<string, AgentRole> = {
    route: "route",
    productdefinition: "product_definition",
    product: "product_definition",
    projectruntime: "project_runtime",
    technicaldesign: "technical_design",
    implementation: "implementation",
    dev: "implementation",
    verification: "verification",
    qa: "verification",
    governancereview: "governance_review",
    acceptance: "acceptance",
    sessionhandoff: "session_handoff",
    migration: "migration",
  };
  return map[normalized] ?? "migration";
}

function safeObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
