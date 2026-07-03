import { Agent, run, setTracingDisabled } from "@openai/agents";
import { SandboxAgent } from "@openai/agents/sandbox";
import { Capabilities, skills as sdkSkills } from "@openai/agents/sandbox";
import { localDir } from "@openai/agents/sandbox";
import { UnixLocalSandboxClient } from "@openai/agents/sandbox/local";
import { existsSync } from "node:fs";
import { mkdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import { execa } from "execa";
import {
  type AgentRole,
  type AgentRunRecord,
  type TokenUsage,
  TokenUsageSchema,
  type ToolCallRecord,
  nowIso,
} from "./schema.js";
import {
  applyOpenAIExecutorEnv,
  hasOpenAIExecutorConfig,
  resolveOpenAIExecutorConfig,
} from "./openai-config.js";
import { RuntimeStore } from "./store.js";
import { emptyTokenUsage, summarizeOpenAIUsage } from "./usage.js";

export type AgentTask = {
  sessionId: string;
  role: AgentRole;
  repoRoot: string;
  prompt: string;
  skills?: AgentTaskSkill[];
  writeAllowed?: boolean;
  maxTurns?: number;
};

export type AgentTaskSkill = {
  name: string;
  description: string;
  content: string;
  path: string;
  content_sha256: string;
  required: boolean;
};

export type AgentTaskResult = {
  agentRun: AgentRunRecord;
  output: string;
  filesChanged: string[];
  commandsRun: string[];
  tokenUsage: TokenUsage;
};

export type CodexExecSkillDelivery = "codex_home" | "prompt_inline" | "sdk_skill";

export type CodexExecSkillManifestEntry = {
  name: string;
  description: string;
  path: string;
  content_sha256: string;
  required: boolean;
  installed_path: string;
};

export type CodexExecHome = {
  runRoot: string;
  codexHome: string;
  skillsDir: string;
  manifestPath: string;
  skills: CodexExecSkillManifestEntry[];
  sharedCodexHome: string;
};

export type AgentRunner = {
  name: AgentRunRecord["runner"];
  runTask(task: AgentTask): Promise<AgentTaskResult>;
};

export type AgentExecutorPreference = "auto" | "openai_sandbox" | "codex_exec" | "local_fallback";

export type AgentFailureClassification = {
  failureKind: string;
  failureMessage: string;
  retryable: boolean;
};

export function buildAgentRunner(store: RuntimeStore): AgentRunner {
  const preference = resolveAgentExecutorPreference();
  if (preference === "codex_exec") {
    return new CodexExecRunner(store);
  }
  if (preference === "local_fallback") {
    return new LocalFallbackRunner(store);
  }
  if (preference === "openai_sandbox") {
    return hasOpenAIExecutorConfig(resolveOpenAIExecutorConfig())
      ? new OpenAISandboxRunner(store)
      : new LocalFallbackRunner(store);
  }
  if (hasOpenAIExecutorConfig(resolveOpenAIExecutorConfig())) {
    return new OpenAISandboxRunner(store);
  }
  return new LocalFallbackRunner(store);
}

export function resolveAgentExecutorPreference(env: NodeJS.ProcessEnv = process.env): AgentExecutorPreference {
  const raw = (env.AGT_EXECUTOR ?? env.AGT_V2_EXECUTOR ?? "").trim();
  if (!raw) {
    return "auto";
  }
  if (raw === "codex" || raw === "codex-exec") {
    return "codex_exec";
  }
  if (raw === "openai" || raw === "openai-sdk") {
    return "openai_sandbox";
  }
  if (raw === "fallback" || raw === "local") {
    return "local_fallback";
  }
  if (["auto", "openai_sandbox", "codex_exec", "local_fallback"].includes(raw)) {
    return raw as AgentExecutorPreference;
  }
  throw new Error(`Unsupported AGT executor: ${raw}`);
}

export class OpenAISandboxRunner implements AgentRunner {
  readonly name = "openai_sandbox" as const;

  constructor(private readonly store: RuntimeStore) {}

  async runTask(task: AgentTask): Promise<AgentTaskResult> {
    const config = await this.store.loadConfig();
    const openAIConfig = resolveOpenAIExecutorConfig({ runtimeDefaultModel: config.default_model });
    applyOpenAIExecutorEnv(openAIConfig);
    const model = openAIConfig.model ?? config.default_model;
    const maxTurns = task.maxTurns ?? config.executor.default_max_turns;
    setTracingDisabled(false);
    const agentRun = await this.store.createAgentRun({
      sessionId: task.sessionId,
      role: task.role,
      runner: this.name,
      input: task.prompt,
      metadata: {
        write_allowed: Boolean(task.writeAllowed),
        model,
        max_turns: maxTurns,
        skills: taskSkillMetadata(task.skills),
        openai_config_sources: {
          api_key: openAIConfig.apiKeySource,
          base_url: openAIConfig.baseUrlSource,
          model: openAIConfig.modelSource,
        },
      },
    });
    const heartbeat = startAgentRunHeartbeat(this.store, agentRun, config.monitoring.heartbeat_interval_ms);
    const started = Date.now();
    const toolCallsBefore = await this.snapshotGit(task.repoRoot);
    try {
      const agent = this.createAgent(task, model);
      const sandboxClient = new UnixLocalSandboxClient();
      const result = await run(agent, task.prompt, {
        maxTurns,
        sandbox: {
          client: sandboxClient,
          manifest: {
            root: "/workspace",
            entries: {
              workspace: localDir({
                src: task.repoRoot,
                permissions: sandboxWorkspacePermissions(task.writeAllowed),
              }),
            },
          },
        },
      });
      const output = stringifyFinalOutput(result.finalOutput);
      const filesChanged = await this.changedFiles(task.repoRoot, toolCallsBefore);
      const commandsRun = commandsFromRunItems(result.newItems);
      const tokenUsage = summarizeOpenAIUsage(result.rawResponses);
      await this.recordSdkToolCalls(task, agentRun, result.newItems);
      const sdkTrace = await this.store.writeArtifact({
        sessionId: task.sessionId,
        role: task.role,
        name: `${agentRun.agent_run_id}-sdk-trace.json`,
        content: JSON.stringify(summarizeOpenAIResult(result), null, 2),
        metadata: { agent_run_id: agentRun.agent_run_id, kind: "sdk_trace" },
      });
      await heartbeat.stop();
      const completed = await this.store.completeAgentRun(agentRun, {
        status: "completed",
        output,
        metadata: {
          ...agentRun.metadata,
          raw_response_count: result.rawResponses.length,
          new_item_count: result.newItems.length,
          last_response_id: result.lastResponseId ?? "",
          sdk_trace_artifact_path: sdkTrace.path,
          token_usage: tokenUsage,
          executor_duration_ms: Date.now() - started,
        },
      });
      await this.recordRuntimeToolCall(task, completed, {
        name: "openai_sandbox_run",
        started,
        output: {
          final_output: output,
          changed_files: filesChanged,
          commands_run: commandsRun,
          sdk_trace_artifact_path: sdkTrace.path,
          raw_response_count: result.rawResponses.length,
          new_item_count: result.newItems.length,
          token_usage: tokenUsage,
        },
      });
      return { agentRun: completed, output, filesChanged, commandsRun, tokenUsage };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const failure = classifyExecutorFailure(message);
      await heartbeat.stop();
      const tokenUsage = emptyTokenUsage();
      const completed = await this.store.completeAgentRun(agentRun, {
        status: "failed",
        error: message,
        output: "",
        metadata: {
          ...failureMetadata(failure),
          token_usage: tokenUsage,
          executor_duration_ms: Date.now() - started,
        },
      });
      await this.recordRuntimeToolCall(task, completed, {
        name: "openai_sandbox_error",
        started,
        output: { error: message, failure_kind: failure.failureKind, retryable: failure.retryable, token_usage: tokenUsage },
      });
      return { agentRun: completed, output: message, filesChanged: [], commandsRun: [], tokenUsage };
    } finally {
      await heartbeat.stop();
    }
  }

  private createAgent(task: AgentTask, model: string): Agent | SandboxAgent {
    const instructions = [
      `You are the ${task.role} agent in Agent Team Runtime.`,
      "Work only inside /workspace.",
      task.writeAllowed
        ? "You may edit files when needed and must keep changes scoped."
        : "You are read-only. Do not edit files or run commands that mutate the repository.",
      "Return a concise report with evidence: files inspected, commands run, changes made, risks.",
      "Do not include secrets or private credentials in output.",
    ].join("\n");

    return new SandboxAgent({
      name: `agt_${task.role}`,
      instructions,
      capabilities: sandboxCapabilities(task),
      model,
    });
  }

  private async recordSdkToolCalls(task: AgentTask, agentRun: AgentRunRecord, items: unknown[]): Promise<void> {
    for (const item of items) {
      const json = serializeRunItem(item);
      const raw = safeRecord(safeRecord(json).rawItem ?? json);
      const rawType = String(raw.type ?? safeRecord(json).type ?? "run_item");
      if (!isToolLikeRunItem(rawType)) {
        continue;
      }
      await this.store.appendToolCall({
        at: nowIso(),
        session_id: task.sessionId,
        agent_run_id: agentRun.agent_run_id,
        role: task.role,
        kind: kindForRunItem(rawType),
        name: nameForRunItem(rawType, raw),
        input: inputForRunItem(rawType, raw),
        output: outputForRunItem(rawType, raw),
        exit_code: exitCodeForRunItem(rawType, raw),
      });
    }
  }

  private async recordRuntimeToolCall(
    task: AgentTask,
    agentRun: AgentRunRecord,
    args: { name: string; started: number; output: Record<string, unknown> },
  ): Promise<void> {
    const call: ToolCallRecord = {
      at: nowIso(),
      session_id: task.sessionId,
      agent_run_id: agentRun.agent_run_id,
      role: task.role,
      kind: "agent_run",
      name: args.name,
      input: { write_allowed: Boolean(task.writeAllowed), max_turns: task.maxTurns, skills: taskSkillMetadata(task.skills) },
      output: args.output,
      duration_ms: Date.now() - args.started,
    };
    await this.store.appendToolCall(call);
  }

  private async snapshotGit(repoRoot: string): Promise<string> {
    try {
      const result = await execa("git", ["diff", "--name-only"], { cwd: repoRoot });
      return result.stdout;
    } catch {
      return "";
    }
  }

  private async changedFiles(repoRoot: string, before: string): Promise<string[]> {
    try {
      const result = await execa("git", ["diff", "--name-only"], { cwd: repoRoot });
      const beforeSet = new Set(before.split("\n").filter(Boolean));
      return result.stdout
        .split("\n")
        .filter(Boolean)
        .filter((file) => !beforeSet.has(file));
    } catch {
      return [];
    }
  }
}

export function sandboxWorkspacePermissions(_writeAllowed?: boolean): number {
  // The OpenAI local sandbox owns a copied temp workspace and must be able to
  // clean it up even for read-only AGT stages. Code write policy is enforced by
  // writeAllowed in the stage contract and audited through git diff tracking.
  return 0o755;
}

export class CodexExecRunner implements AgentRunner {
  readonly name = "codex_exec" as const;

  constructor(private readonly store: RuntimeStore) {}

  async runTask(task: AgentTask): Promise<AgentTaskResult> {
    const config = await this.store.loadConfig();
    const prompt = buildCodexExecPrompt(task);
    const model = codexModelOverride();
    const agentRun = await this.store.createAgentRun({
      sessionId: task.sessionId,
      role: task.role,
      runner: this.name,
      input: prompt,
      metadata: {
        write_allowed: Boolean(task.writeAllowed),
        model: model ?? "",
        model_source: model ? "env" : "codex_config",
        max_turns: task.maxTurns ?? config.executor.default_max_turns,
        skills: taskSkillMetadata(task.skills, "codex_home"),
      },
    });
    const heartbeat = startAgentRunHeartbeat(this.store, agentRun, config.monitoring.heartbeat_interval_ms);
    const started = Date.now();
    const before = await snapshotGitDiffNames(task.repoRoot);
    try {
      const codexHome = await prepareCodexExecHome(this.store, agentRun, task);
      const result = await execa(codexBinary(), codexExecArgs(task, model), {
        cwd: task.repoRoot,
        input: prompt,
        env: {
          ...process.env,
          CODEX_HOME: codexHome.codexHome,
        },
        reject: false,
        maxBuffer: 1000 * 1000 * 100,
      });
      const events = parseCodexExecJsonl(result.stdout);
      const commandsRun = commandsFromCodexExecEvents(events);
      const filesChanged = await changedGitDiffNames(task.repoRoot, before);
      const tokenUsage = summarizeCodexExecUsage(events);
      const finalMessage = finalMessageFromCodexExecEvents(events);
      const failure = result.exitCode === 0
        ? null
        : failureFromCodexExecEvents(events, result.stderr, finalMessage || result.stdout);
      const output = result.exitCode === 0
        ? finalMessage || result.stderr || result.stdout || ""
        : failure?.failureMessage || result.stderr || finalMessage || result.stdout || "";
      const eventsArtifact = await this.store.writeArtifact({
        sessionId: task.sessionId,
        role: task.role,
        name: `${agentRun.agent_run_id}-codex-exec-events.jsonl`,
        content: normalizeCodexExecEventsArtifact(result.stdout, result.stderr),
        metadata: { agent_run_id: agentRun.agent_run_id, kind: "codex_exec_events" },
      });
      const promptArtifact = await this.store.writeArtifact({
        sessionId: task.sessionId,
        role: task.role,
        name: `${agentRun.agent_run_id}-codex-exec-prompt.md`,
        content: prompt,
        metadata: { agent_run_id: agentRun.agent_run_id, kind: "codex_exec_prompt" },
      });
      await this.recordCodexToolCalls(task, agentRun, events);
      await heartbeat.stop();
      const completed = await this.store.completeAgentRun(agentRun, {
        status: result.exitCode === 0 ? "completed" : "failed",
        output,
        error: result.exitCode === 0 ? "" : output,
        metadata: {
          ...agentRun.metadata,
          ...(failure ? failureMetadata(failure) : {}),
          executor_status: result.exitCode === 0 ? "completed" : "failed",
          exit_code: result.exitCode ?? 0,
          stderr: redactLargeString(result.stderr),
          stdout_event_count: events.length,
          codex_exec_events_artifact_path: eventsArtifact.path,
          codex_exec_prompt_artifact_path: promptArtifact.path,
          codex_home: codexHome.codexHome,
          codex_skill_manifest_path: codexHome.manifestPath,
          token_usage: tokenUsage,
          executor_duration_ms: Date.now() - started,
        },
      });
      await this.recordRuntimeToolCall(task, completed, {
        name: result.exitCode === 0 ? "codex_exec_run" : "codex_exec_error",
        started,
        output: {
          final_output: output,
          changed_files: filesChanged,
          commands_run: commandsRun,
          exit_code: result.exitCode ?? 0,
          stderr: redactLargeString(result.stderr),
          stdout_event_count: events.length,
          failure_kind: failure?.failureKind ?? "",
          failure_message: failure?.failureMessage ?? "",
          retryable: failure?.retryable ?? false,
          codex_exec_events_artifact_path: eventsArtifact.path,
          codex_exec_prompt_artifact_path: promptArtifact.path,
          codex_home: codexHome.codexHome,
          codex_skill_manifest_path: codexHome.manifestPath,
          token_usage: tokenUsage,
        },
      });
      return { agentRun: completed, output, filesChanged, commandsRun, tokenUsage };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const failure = classifyExecutorFailure(message);
      await heartbeat.stop();
      const tokenUsage = emptyTokenUsage();
      const completed = await this.store.completeAgentRun(agentRun, {
        status: "failed",
        error: message,
        output: message,
        metadata: {
          ...failureMetadata(failure),
          token_usage: tokenUsage,
          executor_duration_ms: Date.now() - started,
        },
      });
      await this.recordRuntimeToolCall(task, completed, {
        name: "codex_exec_error",
        started,
        output: { error: message, failure_kind: failure.failureKind, retryable: failure.retryable, token_usage: tokenUsage },
      });
      return { agentRun: completed, output: message, filesChanged: [], commandsRun: [], tokenUsage };
    } finally {
      await heartbeat.stop();
    }
  }

  private async recordCodexToolCalls(task: AgentTask, agentRun: AgentRunRecord, events: unknown[]): Promise<void> {
    for (const event of events) {
      const record = safeRecord(event);
      const item = safeRecord(record.item);
      if (item.type !== "command_execution") {
        continue;
      }
      const command = stringValue(item.command) || "command_execution";
      await this.store.appendToolCall({
        at: nowIso(),
        session_id: task.sessionId,
        agent_run_id: agentRun.agent_run_id,
        role: task.role,
        kind: "shell",
        name: "codex_command_execution",
        input: { command, event_type: record.type ?? "" },
        output: { status: item.status ?? "", event_type: record.type ?? "" },
        duration_ms: undefined,
      });
    }
  }

  private async recordRuntimeToolCall(
    task: AgentTask,
    agentRun: AgentRunRecord,
    args: { name: string; started: number; output: Record<string, unknown> },
  ): Promise<void> {
    await this.store.appendToolCall({
      at: nowIso(),
      session_id: task.sessionId,
      agent_run_id: agentRun.agent_run_id,
      role: task.role,
      kind: "agent_run",
      name: args.name,
      input: { write_allowed: Boolean(task.writeAllowed), max_turns: task.maxTurns, skills: taskSkillMetadata(task.skills, "codex_home") },
      output: args.output,
      duration_ms: Date.now() - args.started,
    });
  }
}

export class LocalFallbackRunner implements AgentRunner {
  readonly name = "local_fallback" as const;

  constructor(private readonly store: RuntimeStore) {}

  async runTask(task: AgentTask): Promise<AgentTaskResult> {
    const agentRun = await this.store.createAgentRun({
      sessionId: task.sessionId,
      role: task.role,
      runner: this.name,
      input: task.prompt,
      metadata: {
        reason: "OPENAI_API_KEY/OPENAI_BASE_URL not set; using deterministic local runner.",
        skills: taskSkillMetadata(task.skills),
      },
    });
    const config = await this.store.loadConfig();
    const heartbeat = startAgentRunHeartbeat(this.store, agentRun, config.monitoring.heartbeat_interval_ms);
    const started = Date.now();
    try {
      const git = await runGitStatus(task.repoRoot);
      const output = [
        `${task.role} local fallback completed.`,
        `Write allowed: ${Boolean(task.writeAllowed)}`,
        git.summary,
      ].join("\n");
      await this.store.appendToolCall({
        at: nowIso(),
        session_id: task.sessionId,
        agent_run_id: agentRun.agent_run_id,
        role: task.role,
        kind: "shell",
        name: "git_status",
        input: { command: "git status --short" },
        output: { stdout: git.stdout, stderr: git.stderr },
        exit_code: git.exitCode,
        duration_ms: Date.now() - started,
      });
      await heartbeat.stop();
      const tokenUsage = emptyTokenUsage();
      const completed = await this.store.completeAgentRun(agentRun, {
        status: "completed",
        output,
        metadata: {
          token_usage: tokenUsage,
          executor_duration_ms: Date.now() - started,
        },
      });
      return {
        agentRun: completed,
        output,
        filesChanged: git.changedFiles,
        commandsRun: ["git status --short"],
        tokenUsage,
      };
    } finally {
      await heartbeat.stop();
    }
  }
}

function sandboxCapabilities(task: AgentTask) {
  const capabilities = Capabilities.default();
  const routedSkills = task.skills?.filter((skill) => skill.content.trim()) ?? [];
  if (routedSkills.length > 0) {
    capabilities.push(sdkSkills({
      skillsPath: ".agt2/skills",
      skills: routedSkills.map((skill) => ({
        name: skill.name,
        description: skill.description || "No description provided.",
        content: skill.content,
      })),
    }));
  }
  return capabilities;
}

function taskSkillMetadata(
  skills: AgentTaskSkill[] | undefined,
  delivery: CodexExecSkillDelivery = "sdk_skill",
): Array<Record<string, unknown>> {
  return (skills ?? []).map((skill) => ({
    name: skill.name,
    description: skill.description,
    path: skill.path,
    content_sha256: skill.content_sha256,
    required: skill.required,
    delivery,
  }));
}

function codexBinary(): string {
  return process.env.AGT_CODEX_BIN?.trim() || "codex";
}

function codexModelOverride(): string | undefined {
  return process.env.AGT_CODEX_MODEL?.trim()
    || process.env.AGT_OPENAI_MODEL?.trim()
    || process.env.OPENAI_MODEL?.trim()
    || undefined;
}

function codexExecArgs(task: AgentTask, model: string | undefined): string[] {
  const args = [
    "exec",
    "--json",
    "--color",
    "never",
    "--sandbox",
    task.writeAllowed ? "workspace-write" : "read-only",
    "--cd",
    task.repoRoot,
  ];
  if (model) {
    args.push("--model", model);
  }
  if (process.env.AGT_CODEX_SKIP_GIT_REPO_CHECK === "1") {
    args.push("--skip-git-repo-check");
  }
  args.push("-");
  return args;
}

export function buildCodexExecPrompt(task: AgentTask): string {
  const skills = task.skills?.filter((skill) => skill.content.trim()) ?? [];
  if (skills.length === 0) {
    return task.prompt;
  }
  const skillSections = skills.map((skill) => [
    `- ${skill.name}`,
    `  Description: ${skill.description || "No description provided."}`,
    `  Required: ${skill.required ? "yes" : "no"}`,
    `  Source path: ${skill.path}`,
    `  Content SHA256: ${skill.content_sha256}`,
  ].join("\n"));
  return [
    task.prompt,
    "",
    "# AGT-Routed Skills",
    "",
    "The following skills were selected by AGT for this stage and installed into this run's isolated CODEX_HOME. Treat them as the active stage skills. Do not invoke unrelated local skills unless the stage prompt explicitly asks for them.",
    "",
    ...skillSections,
  ].join("\n");
}

export async function prepareCodexExecHome(
  store: RuntimeStore,
  agentRun: AgentRunRecord,
  task: AgentTask,
  env: NodeJS.ProcessEnv = process.env,
): Promise<CodexExecHome> {
  const sharedCodexHome = resolveSharedCodexHome(env);
  const runRoot = path.join(store.stateRoot, "runs", agentRun.agent_run_id);
  const codexHome = path.join(runRoot, "codex-home");
  const skillsDir = path.join(codexHome, "skills");
  const manifestPath = path.join(runRoot, "skill-manifest.json");

  await mkdir(codexHome, { recursive: true });
  await ensureDirSymlink(path.join(sharedCodexHome, "sessions"), path.join(codexHome, "sessions"));
  await ensureFileSymlink(path.join(sharedCodexHome, "auth.json"), path.join(codexHome, "auth.json"));
  await syncCodexConfigFile(path.join(sharedCodexHome, "config.json"), path.join(codexHome, "config.json"));
  await syncCodexConfigFile(path.join(sharedCodexHome, "instructions.md"), path.join(codexHome, "instructions.md"));
  await syncCodexConfigFile(path.join(sharedCodexHome, "config.toml"), path.join(codexHome, "config.toml"), stripSkillsConfigEntries);

  await rm(skillsDir, { recursive: true, force: true });
  await mkdir(skillsDir, { recursive: true });
  const manifestSkills = await writeCodexExecSkills(skillsDir, task.skills ?? []);
  const manifest = {
    schema_version: 1,
    agent_run_id: agentRun.agent_run_id,
    session_id: task.sessionId,
    role: task.role,
    delivery: "codex_home",
    codex_home: codexHome,
    skills_dir: skillsDir,
    shared_codex_home: sharedCodexHome,
    allow_user_skills: false,
    stripped_config_sections: ["[[skills.config]]"],
    skills: manifestSkills,
  };
  await mkdir(runRoot, { recursive: true });
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return { runRoot, codexHome, skillsDir, manifestPath, skills: manifestSkills, sharedCodexHome };
}

export function stripSkillsConfigEntries(content: string): string {
  if (!content.includes("[[skills.config]]")) {
    return content;
  }
  const lines = content.split("\n");
  const out: string[] = [];
  let inSkillsConfig = false;
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("[")) {
      if (trimmed === "[[skills.config]]") {
        inSkillsConfig = true;
        continue;
      }
      inSkillsConfig = false;
      out.push(line);
      continue;
    }
    if (!inSkillsConfig) {
      out.push(line);
    }
  }
  const stripped = out.join("\n").replace(/\n+$/, "");
  return stripped ? `${stripped}\n` : "";
}

function resolveSharedCodexHome(env: NodeJS.ProcessEnv): string {
  return path.resolve(
    env.AGT_CODEX_SHARED_HOME?.trim()
      || env.CODEX_HOME?.trim()
      || path.join(homedir(), ".codex"),
  );
}

async function ensureDirSymlink(src: string, dst: string): Promise<void> {
  await mkdir(src, { recursive: true });
  await replaceSymlink(src, dst, "dir");
}

async function ensureFileSymlink(src: string, dst: string): Promise<void> {
  if (!existsSync(src)) {
    await rm(dst, { force: true });
    return;
  }
  await replaceSymlink(src, dst, "file");
}

async function replaceSymlink(src: string, dst: string, type: "dir" | "file"): Promise<void> {
  await mkdir(path.dirname(dst), { recursive: true });
  await rm(dst, { recursive: true, force: true });
  try {
    await symlink(src, dst, type);
  } catch {
    if (type === "file") {
      const content = await readFile(src);
      await writeFile(dst, content);
    } else {
      await mkdir(dst, { recursive: true });
    }
  }
}

async function syncCodexConfigFile(
  src: string,
  dst: string,
  transform: (content: string) => string = (content) => content,
): Promise<void> {
  if (!existsSync(src)) {
    await rm(dst, { force: true });
    return;
  }
  const content = await readFile(src, "utf8");
  await mkdir(path.dirname(dst), { recursive: true });
  await writeFile(dst, transform(content), "utf8");
}

async function writeCodexExecSkills(skillsDir: string, skills: AgentTaskSkill[]): Promise<CodexExecSkillManifestEntry[]> {
  const used = new Map<string, number>();
  const entries: CodexExecSkillManifestEntry[] = [];
  for (const skill of skills.filter((candidate) => candidate.content.trim())) {
    const baseName = sanitizeSkillDirName(skill.name);
    const count = used.get(baseName) ?? 0;
    used.set(baseName, count + 1);
    const dirName = count === 0 ? baseName : `${baseName}-${count + 1}`;
    const installDir = path.join(skillsDir, dirName);
    const installedPath = path.join(installDir, "SKILL.md");
    await mkdir(installDir, { recursive: true });
    await writeFile(installedPath, skill.content.trimEnd() + "\n", "utf8");
    entries.push({
      name: skill.name,
      description: skill.description,
      path: skill.path,
      content_sha256: skill.content_sha256,
      required: skill.required,
      installed_path: installedPath,
    });
  }
  return entries;
}

function sanitizeSkillDirName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    || "skill";
}

export function parseCodexExecJsonl(stdout: string): unknown[] {
  return stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line) as unknown;
      } catch (error) {
        return {
          type: "parse_error",
          raw: line,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    });
}

export function commandsFromCodexExecEvents(events: unknown[]): string[] {
  const commands = events
    .map((event) => stringValue(safeRecord(safeRecord(event).item).command))
    .filter(Boolean);
  return [...new Set(commands)];
}

export function finalMessageFromCodexExecEvents(events: unknown[]): string {
  for (const event of [...events].reverse()) {
    const record = safeRecord(event);
    const item = safeRecord(record.item);
    if (record.type === "item.completed" && item.type === "agent_message") {
      const text = stringValue(item.text);
      if (text) {
        return text;
      }
    }
  }
  return "";
}

export function failureFromCodexExecEvents(
  events: unknown[],
  stderr = "",
  fallback = "",
): AgentFailureClassification {
  const turnFailed = [...events].reverse().find((event) => safeRecord(event).type === "turn.failed");
  const turnFailedMessage = messageFromCodexFailureEvent(turnFailed);
  if (turnFailedMessage) {
    return classifyExecutorFailure(turnFailedMessage);
  }

  const errorEvent = [...events].reverse().find((event) => safeRecord(event).type === "error");
  const errorMessage = messageFromCodexFailureEvent(errorEvent);
  if (errorMessage) {
    return classifyExecutorFailure(errorMessage);
  }

  const itemError = [...events].reverse().find((event) => {
    const record = safeRecord(event);
    const item = safeRecord(record.item);
    return record.type === "item.completed" && item.type === "error";
  });
  const itemErrorMessage = messageFromCodexFailureEvent(itemError);
  return classifyExecutorFailure(itemErrorMessage || stderr || fallback || "codex exec failed.");
}

export function summarizeCodexExecUsage(events: unknown[]): TokenUsage {
  const usages = events
    .map((event) => safeRecord(safeRecord(event).usage))
    .filter((usage) => Object.keys(usage).length > 0);
  if (usages.length === 0) {
    return emptyTokenUsage();
  }
  const inputTokens = sumCodexUsageNumber(usages, ["input_tokens", "inputTokens", "prompt_tokens", "promptTokens"]);
  const outputTokens = sumCodexUsageNumber(usages, ["output_tokens", "outputTokens", "completion_tokens", "completionTokens"]);
  const explicitTotal = sumCodexUsageNumber(usages, ["total_tokens", "totalTokens"]);
  const reasoningTokens = sumCodexUsageNumber(usages, [
    "reasoning_tokens",
    "reasoningTokens",
    "reasoning_output_tokens",
    "reasoningOutputTokens",
  ]);
  return TokenUsageSchema.parse({
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    total_tokens: explicitTotal || inputTokens + outputTokens,
    reasoning_tokens: reasoningTokens,
    raw: usages,
  });
}

export function classifyExecutorFailure(message: string): AgentFailureClassification {
  const failureMessage = message.trim() || "Executor failed.";
  const retryable = isRetryableExecutorFailure(failureMessage);
  return {
    failureKind: retryable ? "executor_transient" : "executor_failed",
    failureMessage,
    retryable,
  };
}

export function agentRunFailureMetadata(agentRun: AgentRunRecord): AgentFailureClassification | null {
  const failureKind = stringValue(agentRun.metadata.failure_kind);
  const failureMessage = stringValue(agentRun.metadata.failure_message) || agentRun.error || agentRun.output;
  if (!failureKind && !failureMessage) {
    return null;
  }
  return {
    failureKind: failureKind || "executor_failed",
    failureMessage,
    retryable: agentRun.metadata.retryable === true,
  };
}

function messageFromCodexFailureEvent(event: unknown): string {
  const record = safeRecord(event);
  const item = safeRecord(record.item);
  const error = safeRecord(record.error);
  return stringValue(error.message)
    || stringValue(record.message)
    || stringValue(record.text)
    || stringValue(item.message)
    || stringValue(item.text);
}

function isRetryableExecutorFailure(message: string): boolean {
  return [
    /stream disconnected/i,
    /disconnected before completion/i,
    /error sending request/i,
    /\bECONNRESET\b/i,
    /\bETIMEDOUT\b/i,
    /\bEAI_AGAIN\b/i,
    /\bENOTFOUND\b/i,
    /socket hang up/i,
    /network error/i,
    /fetch failed/i,
    /\b429\b/,
    /\b502\b/,
    /\b503\b/,
    /\b504\b/,
    /temporarily unavailable/i,
  ].some((pattern) => pattern.test(message));
}

function failureMetadata(failure: AgentFailureClassification): Record<string, unknown> {
  return {
    failure_kind: failure.failureKind,
    failure_message: failure.failureMessage,
    retryable: failure.retryable,
  };
}

function sumCodexUsageNumber(usages: Array<Record<string, unknown>>, keys: string[]): number {
  return usages.reduce((total, usage) => {
    for (const key of keys) {
      const value = usage[key];
      if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
        return total + Math.trunc(value);
      }
    }
    return total;
  }, 0);
}

function normalizeCodexExecEventsArtifact(stdout: string, stderr: string): string {
  const lines = stdout.trim() ? stdout.trim().split(/\r?\n/) : [];
  if (stderr.trim()) {
    lines.push(JSON.stringify({ type: "stderr", text: stderr }));
  }
  return lines.length ? `${lines.join("\n")}\n` : "";
}

async function snapshotGitDiffNames(repoRoot: string): Promise<string> {
  try {
    const result = await execa("git", ["diff", "--name-only"], { cwd: repoRoot });
    return result.stdout;
  } catch {
    return "";
  }
}

async function changedGitDiffNames(repoRoot: string, before: string): Promise<string[]> {
  try {
    const result = await execa("git", ["diff", "--name-only"], { cwd: repoRoot });
    const beforeSet = new Set(before.split("\n").filter(Boolean));
    return result.stdout
      .split("\n")
      .filter(Boolean)
      .filter((file) => !beforeSet.has(file));
  } catch {
    return [];
  }
}

function startAgentRunHeartbeat(store: RuntimeStore, agentRun: AgentRunRecord, intervalMs: number): { stop: () => Promise<void> } {
  let stopped = false;
  let pending = Promise.resolve();
  const beat = (details: Record<string, unknown> = {}) => {
    if (stopped) {
      return;
    }
    pending = pending.then(() => store.heartbeatAgentRun(agentRun, details)).then(
      () => undefined,
      () => {
        // Heartbeat is observability only; do not fail the executor because status persistence hiccuped.
      },
    );
  };
  const interval = setInterval(() => {
    beat();
  }, intervalMs);
  interval.unref?.();
  beat({ reason: "started" });
  return {
    stop: async () => {
      stopped = true;
      clearInterval(interval);
      await pending;
    },
  };
}

async function runGitStatus(repoRoot: string): Promise<{
  stdout: string;
  stderr: string;
  exitCode: number;
  changedFiles: string[];
  summary: string;
}> {
  try {
    const result = await execa("git", ["status", "--short"], { cwd: repoRoot, reject: false });
    const changedFiles = result.stdout
      .split("\n")
      .map((line) => line.trim().split(/\s+/).at(-1) ?? "")
      .filter(Boolean);
    return {
      stdout: result.stdout,
      stderr: result.stderr,
      exitCode: result.exitCode ?? 0,
      changedFiles,
      summary: changedFiles.length ? `Changed files: ${changedFiles.join(", ")}` : "No changed files.",
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { stdout: "", stderr: message, exitCode: 1, changedFiles: [], summary: message };
  }
}

function stringifyFinalOutput(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (value === undefined || value === null) {
    return "";
  }
  return JSON.stringify(value, null, 2);
}

function serializeRunItem(value: unknown): Record<string, unknown> {
  const withToJson = value as { toJSON?: () => unknown };
  return safeRecord(typeof withToJson?.toJSON === "function" ? withToJson.toJSON() : value);
}

function summarizeOpenAIResult(result: {
  finalOutput?: unknown;
  lastResponseId?: string;
  rawResponses: unknown[];
  newItems: unknown[];
}): Record<string, unknown> {
  return {
    final_output: result.finalOutput,
    last_response_id: result.lastResponseId ?? "",
    raw_response_count: result.rawResponses.length,
    new_item_count: result.newItems.length,
    raw_responses: result.rawResponses.map((response, index) => summarizeRawResponse(response, index)),
    new_items: result.newItems.map((item, index) => summarizeRunItem(item, index)),
  };
}

function summarizeRawResponse(value: unknown, index: number): Record<string, unknown> {
  const response = safeRecord(value);
  return {
    index,
    id: stringValue(response.id),
    model: stringValue(response.model),
    usage: safeRecord(response.usage),
    output_count: Array.isArray(response.output) ? response.output.length : undefined,
    keys: Object.keys(response).sort(),
  };
}

function summarizeRunItem(value: unknown, index: number): Record<string, unknown> {
  const json = serializeRunItem(value);
  const raw = safeRecord(json.rawItem ?? json);
  const rawType = String(raw.type ?? json.type ?? "run_item");
  return {
    index,
    item_type: stringValue(json.type) || "run_item",
    raw_type: rawType,
    name: nameForRunItem(rawType, raw),
    call_id: stringValue(raw.callId ?? raw.call_id),
    status: stringValue(raw.status),
    input: redactLargeStrings(inputForRunItem(rawType, raw)),
    output: redactLargeStrings(outputForRunItem(rawType, raw)),
  };
}

function commandsFromRunItems(items: unknown[]): string[] {
  const commands: string[] = [];
  for (const item of items) {
    const raw = safeRecord(safeRecord(serializeRunItem(item)).rawItem ?? serializeRunItem(item));
    if (raw.type !== "shell_call") {
      continue;
    }
    const action = safeRecord(raw.action);
    if (Array.isArray(action.commands)) {
      commands.push(...action.commands.filter((command): command is string => typeof command === "string"));
    }
  }
  return [...new Set(commands)];
}

function isToolLikeRunItem(rawType: string): boolean {
  return [
    "hosted_tool_call",
    "function_call",
    "function_call_result",
    "shell_call",
    "shell_call_output",
    "apply_patch_call",
    "apply_patch_call_output",
    "tool_search_call",
    "tool_search_output",
  ].includes(rawType);
}

function kindForRunItem(rawType: string): ToolCallRecord["kind"] {
  if (rawType.startsWith("shell_call")) {
    return "shell";
  }
  if (rawType.startsWith("apply_patch_call")) {
    return "apply_patch";
  }
  return "runtime";
}

function nameForRunItem(rawType: string, raw: Record<string, unknown>): string {
  if (typeof raw.name === "string" && raw.name) {
    return raw.name;
  }
  if (rawType === "shell_call" || rawType === "shell_call_output") {
    return "shell";
  }
  if (rawType === "apply_patch_call" || rawType === "apply_patch_call_output") {
    return "apply_patch";
  }
  return rawType;
}

function inputForRunItem(rawType: string, raw: Record<string, unknown>): Record<string, unknown> {
  if (rawType === "shell_call") {
    return safeRecord(raw.action);
  }
  if (rawType === "apply_patch_call") {
    return safeRecord(raw.operation);
  }
  if (rawType === "function_call") {
    return { arguments: raw.arguments ?? "" };
  }
  if (rawType === "tool_search_call") {
    return { arguments: raw.arguments ?? "" };
  }
  return { call_id: raw.callId ?? raw.call_id ?? "", raw_type: rawType };
}

function outputForRunItem(rawType: string, raw: Record<string, unknown>): Record<string, unknown> {
  if (rawType === "shell_call_output") {
    return { output: raw.output ?? [] };
  }
  if (rawType === "apply_patch_call_output") {
    return { status: raw.status ?? "", output: raw.output ?? "" };
  }
  if (rawType === "function_call_result") {
    return { output: raw.output ?? "", status: raw.status ?? "" };
  }
  if (rawType === "tool_search_output") {
    return { tools: raw.tools ?? [], status: raw.status ?? "" };
  }
  return {};
}

function exitCodeForRunItem(rawType: string, raw: Record<string, unknown>): number | null | undefined {
  if (rawType !== "shell_call_output" || !Array.isArray(raw.output)) {
    return undefined;
  }
  for (const output of raw.output) {
    const outcome = safeRecord(safeRecord(output).outcome);
    if (outcome.type === "exit") {
      return typeof outcome.exitCode === "number" ? outcome.exitCode : null;
    }
  }
  return undefined;
}

function safeRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function redactLargeStrings(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      typeof item === "string" && item.length > 4000 ? `${item.slice(0, 4000)}...<truncated>` : item,
    ]),
  );
}

function redactLargeString(value: string): string {
  return value.length > 4000 ? `${value.slice(0, 4000)}...<truncated>` : value;
}
