import { Agent, run, setTracingDisabled } from "@openai/agents";
import { SandboxAgent } from "@openai/agents/sandbox";
import { Capabilities, filesystem, skills as sdkSkills } from "@openai/agents/sandbox";
import { localDir } from "@openai/agents/sandbox";
import { UnixLocalSandboxClient } from "@openai/agents/sandbox/local";
import { existsSync } from "node:fs";
import { cp, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { execa } from "execa";
import {
  type AgentRole,
  type AgentRunRecord,
  type TokenUsage,
  TokenUsageSchema,
  type ToolCallRecord,
  nowReadableDateTime,
} from "./schema.js";
import {
  applyOpenAIExecutorEnv,
  hasOpenAIExecutorConfig,
  resolveOpenAIExecutorConfig,
  shouldEnableOpenAISandboxApplyPatch,
  shouldEnableOpenAITracing,
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
  /** Concrete workflow stage key, used for per-stage skill folder isolation (e.g. "dev.implementation"). */
  stage?: string;
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

export type AgentRunner = {
  name: AgentRunRecord["runner"];
  runTask(task: AgentTask): Promise<AgentTaskResult>;
};

export type AgentExecutorPreference = "auto" | "openai_sandbox" | "codex_exec" | "pi_exec" | "local_fallback";

export function buildAgentRunner(store: RuntimeStore): AgentRunner {
  const preference = resolveAgentExecutorPreference();
  if (preference === "codex_exec") {
    return new CodexExecRunner(store);
  }
  if (preference === "pi_exec") {
    return new PiExecRunner(store);
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
  if (raw === "pi" || raw === "pi-exec") {
    return "pi_exec";
  }
  if (raw === "openai" || raw === "openai-sdk") {
    return "openai_sandbox";
  }
  if (raw === "fallback" || raw === "local") {
    return "local_fallback";
  }
  if (["auto", "openai_sandbox", "codex_exec", "pi_exec", "local_fallback"].includes(raw)) {
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
    const sdkTracingEnabled = shouldEnableOpenAITracing(openAIConfig);
    const sdkApplyPatchEnabled = shouldEnableOpenAISandboxApplyPatch(openAIConfig);
    setTracingDisabled(!sdkTracingEnabled);
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
        sdk_tracing_enabled: sdkTracingEnabled,
        sdk_apply_patch_enabled: sdkApplyPatchEnabled,
      },
    });
    const heartbeat = startAgentRunHeartbeat(this.store, agentRun, config.monitoring.heartbeat_interval_ms);
    const started = Date.now();
    const toolCallsBefore = await this.snapshotGit(task.repoRoot);
    try {
      const agent = this.createAgent(task, model, { enableApplyPatchTool: sdkApplyPatchEnabled });
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
      await heartbeat.stop();
      const tokenUsage = emptyTokenUsage();
      const completed = await this.store.completeAgentRun(agentRun, {
        status: "failed",
        error: message,
        output: "",
        metadata: {
          token_usage: tokenUsage,
          executor_duration_ms: Date.now() - started,
        },
      });
      await this.recordRuntimeToolCall(task, completed, {
        name: "openai_sandbox_error",
        started,
        output: { error: message, token_usage: tokenUsage },
      });
      return { agentRun: completed, output: message, filesChanged: [], commandsRun: [], tokenUsage };
    } finally {
      await heartbeat.stop();
    }
  }

  private createAgent(
    task: AgentTask,
    model: string,
    options: { enableApplyPatchTool: boolean },
  ): Agent | SandboxAgent {
    const instructions = [
      `You are the ${task.role} agent in Agent Team Runtime.`,
      "Work only inside /workspace.",
      task.writeAllowed
        ? "You may edit files when needed and must keep changes scoped."
        : "You are read-only. Do not edit files or run commands that mutate the repository.",
      options.enableApplyPatchTool || !task.writeAllowed
        ? ""
        : "The apply_patch tool is unavailable on this executor; use shell commands for required file edits.",
      "Return a concise report with evidence: files inspected, commands run, changes made, risks.",
      "Do not include secrets or private credentials in output.",
    ].filter(Boolean).join("\n");

    return new SandboxAgent({
      name: `agt_${task.role}`,
      instructions,
      capabilities: sandboxCapabilities(task, { enableApplyPatchTool: options.enableApplyPatchTool }),
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
        at: nowReadableDateTime(),
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
      at: nowReadableDateTime(),
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
        skills: taskSkillMetadata(task.skills, "prompt_inline"),
      },
    });
    const heartbeat = startAgentRunHeartbeat(this.store, agentRun, config.monitoring.heartbeat_interval_ms);
    const started = Date.now();
    const before = await snapshotGitDiffNames(task.repoRoot);
    try {
      const args = codexExecArgs(task, model);
      const result = await execa(codexBinary(), args, {
        cwd: task.repoRoot,
        input: prompt,
        reject: false,
        maxBuffer: 1000 * 1000 * 100,
      });
      const events = parseCodexExecJsonl(result.stdout);
      const commandsRun = commandsFromCodexExecEvents(events);
      const filesChanged = await changedGitDiffNames(task.repoRoot, before);
      const tokenUsage = summarizeCodexExecUsage(events);
      const output = finalMessageFromCodexExecEvents(events) || result.stderr || result.stdout || "";
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
        error: result.exitCode === 0 ? "" : result.stderr || output,
        metadata: {
          ...agentRun.metadata,
          executor_status: result.exitCode === 0 ? "completed" : "failed",
          exit_code: result.exitCode ?? 0,
          stderr: redactLargeString(result.stderr),
          stdout_event_count: events.length,
          codex_exec_events_artifact_path: eventsArtifact.path,
          codex_exec_prompt_artifact_path: promptArtifact.path,
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
          codex_exec_events_artifact_path: eventsArtifact.path,
          codex_exec_prompt_artifact_path: promptArtifact.path,
          token_usage: tokenUsage,
        },
      });
      return { agentRun: completed, output, filesChanged, commandsRun, tokenUsage };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await heartbeat.stop();
      const tokenUsage = emptyTokenUsage();
      const completed = await this.store.completeAgentRun(agentRun, {
        status: "failed",
        error: message,
        output: message,
        metadata: {
          token_usage: tokenUsage,
          executor_duration_ms: Date.now() - started,
        },
      });
      await this.recordRuntimeToolCall(task, completed, {
        name: "codex_exec_error",
        started,
        output: { error: message, token_usage: tokenUsage },
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
        at: nowReadableDateTime(),
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
      at: nowReadableDateTime(),
      session_id: task.sessionId,
      agent_run_id: agentRun.agent_run_id,
      role: task.role,
      kind: "agent_run",
      name: args.name,
      input: { write_allowed: Boolean(task.writeAllowed), max_turns: task.maxTurns, skills: taskSkillMetadata(task.skills, "prompt_inline") },
      output: args.output,
      duration_ms: Date.now() - args.started,
    });
  }
}

export class PiExecRunner implements AgentRunner {
  readonly name = "pi_exec" as const;

  constructor(private readonly store: RuntimeStore) {}

  async runTask(task: AgentTask): Promise<AgentTaskResult> {
    const config = await this.store.loadConfig();
    const model = piModelOverride();
    const provider = piProviderOverride();
    const thinking = piThinkingOverride();
    const skillsRoot = resolvePiSkillsRoot(this.store.stateRoot);
    const materialized = await materializePiSkills(task, skillsRoot);
    const prompt = buildPiExecPrompt(task, materialized);
    const agentRun = await this.store.createAgentRun({
      sessionId: task.sessionId,
      role: task.role,
      runner: this.name,
      input: prompt,
      metadata: {
        write_allowed: Boolean(task.writeAllowed),
        write_policy: "prompt_audit",
        model: model ?? "",
        model_source: model ? "env" : "pi_default",
        provider: provider ?? "",
        thinking: thinking ?? "",
        max_turns: task.maxTurns ?? config.executor.default_max_turns,
        max_turns_enforced: false,
        skills: taskSkillMetadata(task.skills, "pi_skill_folder"),
        skill_folders: materialized.index,
      },
    });
    const heartbeat = startAgentRunHeartbeat(this.store, agentRun, config.monitoring.heartbeat_interval_ms);
    const started = Date.now();
    const before = await snapshotGitDiffNames(task.repoRoot);
    try {
      const args = piExecArgs(task, { model, provider, thinking, skillDirs: materialized.skillDirs });
      const timeoutMs = piTimeoutMs();
      const result = await execa(piBinary(), args, {
        cwd: task.repoRoot,
        input: prompt,
        reject: false,
        maxBuffer: 1000 * 1000 * 100,
        timeout: timeoutMs,
      });
      const events = parsePiExecJsonl(result.stdout);
      const commandsRun = commandsFromPiExecEvents(events);
      const filesChanged = await changedGitDiffNames(task.repoRoot, before);
      const tokenUsage = summarizePiExecUsage(events);
      const output = finalMessageFromPiExecEvents(events) || result.stderr || result.stdout || "";
      const failureMessage = piExecFailureMessage(result, timeoutMs);
      const eventsArtifact = await this.store.writeArtifact({
        sessionId: task.sessionId,
        role: task.role,
        name: `${agentRun.agent_run_id}-pi-exec-events.jsonl`,
        content: normalizePiExecEventsArtifact(result.stdout, result.stderr),
        metadata: { agent_run_id: agentRun.agent_run_id, kind: "pi_exec_events" },
      });
      const promptArtifact = await this.store.writeArtifact({
        sessionId: task.sessionId,
        role: task.role,
        name: `${agentRun.agent_run_id}-pi-exec-prompt.md`,
        content: prompt,
        metadata: { agent_run_id: agentRun.agent_run_id, kind: "pi_exec_prompt" },
      });
      const skillsArtifact = await this.store.writeArtifact({
        sessionId: task.sessionId,
        role: task.role,
        name: `${agentRun.agent_run_id}-pi-skills.json`,
        content: JSON.stringify({ skill_folders: materialized.index }, null, 2),
        metadata: { agent_run_id: agentRun.agent_run_id, kind: "pi_skills_index" },
      });
      await this.recordPiToolCalls(task, agentRun, events);
      await heartbeat.stop();
      const completed = await this.store.completeAgentRun(agentRun, {
        status: result.exitCode === 0 ? "completed" : "failed",
        output,
        error: result.exitCode === 0 ? "" : failureMessage || result.stderr || output,
        metadata: {
          ...agentRun.metadata,
          executor_status: result.exitCode === 0 ? "completed" : "failed",
          exit_code: result.exitCode ?? 0,
          signal: result.signal ?? "",
          timed_out: Boolean(result.timedOut),
          timeout_ms: timeoutMs,
          stderr: redactLargeString(result.stderr),
          stdout_event_count: events.length,
          pi_exec_events_artifact_path: eventsArtifact.path,
          pi_exec_prompt_artifact_path: promptArtifact.path,
          pi_skills_artifact_path: skillsArtifact.path,
          token_usage: tokenUsage,
          executor_duration_ms: Date.now() - started,
        },
      });
      await this.recordRuntimeToolCall(task, completed, {
        name: result.exitCode === 0 ? "pi_exec_run" : "pi_exec_error",
        started,
        output: {
          final_output: output,
          changed_files: filesChanged,
          commands_run: commandsRun,
          exit_code: result.exitCode ?? 0,
          signal: result.signal ?? "",
          timed_out: Boolean(result.timedOut),
          timeout_ms: timeoutMs,
          stderr: redactLargeString(result.stderr),
          stdout_event_count: events.length,
          pi_exec_events_artifact_path: eventsArtifact.path,
          pi_exec_prompt_artifact_path: promptArtifact.path,
          pi_skills_artifact_path: skillsArtifact.path,
          token_usage: tokenUsage,
        },
      });
      return { agentRun: completed, output, filesChanged, commandsRun, tokenUsage };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await heartbeat.stop();
      const tokenUsage = emptyTokenUsage();
      const completed = await this.store.completeAgentRun(agentRun, {
        status: "failed",
        error: message,
        output: message,
        metadata: {
          token_usage: tokenUsage,
          executor_duration_ms: Date.now() - started,
        },
      });
      await this.recordRuntimeToolCall(task, completed, {
        name: "pi_exec_error",
        started,
        output: { error: message, token_usage: tokenUsage },
      });
      return { agentRun: completed, output: message, filesChanged: [], commandsRun: [], tokenUsage };
    } finally {
      await heartbeat.stop();
    }
  }

  private async recordPiToolCalls(task: AgentTask, agentRun: AgentRunRecord, events: unknown[]): Promise<void> {
    const calls = new Map<string, { name: string; args: Record<string, unknown>; output: Record<string, unknown> }>();
    for (const event of events) {
      const record = safeRecord(event);
      const type = stringValue(record.type);
      if (type === "tool_execution_start") {
        const id = stringValue(record.toolCallId);
        calls.set(id || `${calls.size}`, {
          name: stringValue(record.toolName),
          args: safeRecord(record.args),
          output: {},
        });
      } else if (type === "tool_execution_end") {
        const call = calls.get(stringValue(record.toolCallId));
        if (call) {
          call.output = safeRecord(record.result);
          call.output.is_error = Boolean(record.isError);
        }
      }
    }
    for (const call of calls.values()) {
      const name = call.name || "tool";
      await this.store.appendToolCall({
        at: nowReadableDateTime(),
        session_id: task.sessionId,
        agent_run_id: agentRun.agent_run_id,
        role: task.role,
        kind: piToolCallKind(name),
        name,
        input: call.args,
        output: call.output,
        exit_code: undefined,
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
      at: nowReadableDateTime(),
      session_id: task.sessionId,
      agent_run_id: agentRun.agent_run_id,
      role: task.role,
      kind: "agent_run",
      name: args.name,
      input: {
        write_allowed: Boolean(task.writeAllowed),
        max_turns: task.maxTurns,
        skills: taskSkillMetadata(task.skills, "pi_skill_folder"),
      },
      output: args.output,
      duration_ms: Date.now() - args.started,
    });
  }
}

export type PiSkillMaterialization = {
  skillDirs: string[];
  index: Array<{
    name: string;
    path: string;
    relative_path: string;
    content_sha256: string;
    required: boolean;
  }>;
};

/**
 * Materialize the stage-routed skills into per-stage folders under the pi
 * skills root (default `<stateRoot>/pi-skills/<stage>/<skill-name>/`). Each pi
 * run then loads exactly these folders via `--no-skills --skill <dir>`, so
 * every stage is isolated to its own skill set and the exact bodies used stay
 * auditable in the state root.
 */
export async function materializePiSkills(task: AgentTask, skillsRoot: string): Promise<PiSkillMaterialization> {
  const skills = task.skills?.filter((skill) => skill.content.trim()) ?? [];
  if (skills.length === 0) {
    return { skillDirs: [], index: [] };
  }
  const stageSegment = sanitizeSkillSegment(task.stage ?? task.role);
  const stageDir = path.join(skillsRoot, stageSegment);
  const skillDirs: string[] = [];
  const index: PiSkillMaterialization["index"] = [];
  for (const skill of skills) {
    const target = path.join(stageDir, sanitizeSkillSegment(skill.name));
    await mkdir(target, { recursive: true });
    await writeFile(path.join(target, "SKILL.md"), skill.content, "utf8");
    const sourceDir = skill.path ? path.dirname(skill.path) : "";
    if (sourceDir && sourceDir !== target && existsSync(sourceDir)) {
      await cp(sourceDir, target, {
        recursive: true,
        filter: (src) => path.basename(src) !== "SKILL.md",
      });
    }
    skillDirs.push(target);
    index.push({
      name: skill.name,
      path: target,
      relative_path: path.relative(task.repoRoot, target),
      content_sha256: skill.content_sha256,
      required: skill.required,
    });
  }
  return { skillDirs, index };
}

export function buildPiExecPrompt(task: AgentTask, materialized: PiSkillMaterialization): string {
  if (materialized.skillDirs.length === 0) {
    return task.prompt;
  }
  const sections = materialized.index.map((skill) => [
    `## Skill: ${skill.name}`,
    `Required: ${skill.required ? "yes" : "no"}`,
    `Path (relative to repo root): ${skill.relative_path}`,
    `Content SHA256: ${skill.content_sha256}`,
    "",
    "Load this skill's SKILL.md with the read tool before starting, and follow its instructions as the active stage skill.",
  ].join("\n"));
  return [
    task.prompt,
    "",
    "# AGT Stage Skills",
    "",
    "The following skills were selected by AGT for this stage and are already loaded as pi skills. Read each SKILL.md from the given path before working. Do not invoke unrelated local skills unless the stage prompt explicitly asks for them.",
    "",
    ...sections,
  ].join("\n");
}

export function parsePiExecJsonl(stdout: string): unknown[] {
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

export function commandsFromPiExecEvents(events: unknown[]): string[] {
  const commands = events
    .filter((event) => stringValue(safeRecord(event).type) === "tool_execution_start")
    .filter((event) => stringValue(safeRecord(event).toolName) === "bash")
    .map((event) => stringValue(safeRecord(safeRecord(event).args).command))
    .filter(Boolean);
  return [...new Set(commands)];
}

export function finalMessageFromPiExecEvents(events: unknown[]): string {
  let lastText = "";
  for (const event of events) {
    const record = safeRecord(event);
    if (record.type !== "message_end") {
      continue;
    }
    const message = safeRecord(record.message);
    if (message.role !== "assistant") {
      continue;
    }
    const text = assistantTextFromContent(message.content);
    if (text) {
      lastText = text;
    }
  }
  return lastText;
}

export function summarizePiExecUsage(events: unknown[]): TokenUsage {
  const usageByResponse = new Map<string, Record<string, unknown>>();
  for (const event of events) {
    const record = safeRecord(event);
    if (!["message_start", "message_update", "message_end"].includes(stringValue(record.type))) {
      continue;
    }
    const message = safeRecord(record.message);
    const usage = safeRecord(message.usage);
    if (usageHasTokens(usage)) {
      const key = stringValue(message.responseId) || stringValue(message.id) || `m${usageByResponse.size}`;
      usageByResponse.set(key, usage);
    }
  }
  if (usageByResponse.size === 0) {
    return emptyTokenUsage();
  }
  const usages = [...usageByResponse.values()];
  const inputTokens = sumPiUsageNumber(usages, "input");
  const outputTokens = sumPiUsageNumber(usages, "output");
  const cacheRead = sumPiUsageNumber(usages, "cacheRead");
  const cacheWrite = sumPiUsageNumber(usages, "cacheWrite");
  const reasoningTokens = sumPiUsageNumber(usages, "reasoning");
  return TokenUsageSchema.parse({
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    total_tokens: inputTokens + outputTokens + cacheRead + cacheWrite,
    reasoning_tokens: reasoningTokens,
    raw: usages,
  });
}

function piBinary(): string {
  return process.env.AGT_PI_BIN?.trim() || "pi";
}

function piModelOverride(): string | undefined {
  return process.env.AGT_PI_MODEL?.trim() || undefined;
}

function piProviderOverride(): string | undefined {
  return process.env.AGT_PI_PROVIDER?.trim() || undefined;
}

function piThinkingOverride(): string | undefined {
  return process.env.AGT_PI_THINKING?.trim() || undefined;
}

/**
 * pi has no max-turns CLI flag, so the stage is bounded by a wall-clock
 * timeout instead. Default 30 minutes; override with AGT_PI_TIMEOUT_MS.
 */
function piTimeoutMs(): number {
  const raw = process.env.AGT_PI_TIMEOUT_MS?.trim();
  const parsed = raw ? Number(raw) : Number.NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 30 * 60 * 1000;
}

function piExecFailureMessage(result: { timedOut?: boolean; exitCode?: number | null; signal?: NodeJS.Signals }, timeoutMs: number): string {
  if (result.timedOut) {
    return `pi timed out after ${timeoutMs}ms`;
  }
  if (result.signal) {
    return `pi was terminated by signal ${result.signal}`;
  }
  if (result.exitCode !== undefined && result.exitCode !== null && result.exitCode !== 0) {
    return `pi exited with code ${result.exitCode}`;
  }
  return "";
}

function resolvePiSkillsRoot(stateRoot: string): string {
  const explicit = process.env.AGT_PI_SKILLS_ROOT?.trim();
  return explicit ? path.resolve(explicit) : path.join(stateRoot, "pi-skills");
}

function piExecArgs(
  task: AgentTask,
  options: { model?: string; provider?: string; thinking?: string; skillDirs: string[] },
): string[] {
  const args = [
    "--mode",
    "json",
    "--no-session",
    "--no-skills",
    "--no-extensions",
    "--no-context-files",
    "--no-approve",
  ];
  if (options.model) {
    args.push("--model", options.model);
  }
  if (options.provider) {
    args.push("--provider", options.provider);
  }
  if (options.thinking) {
    args.push("--thinking", options.thinking);
  }
  for (const dir of options.skillDirs) {
    args.push("--skill", dir);
  }
  return args;
}

function piToolCallKind(name: string): ToolCallRecord["kind"] {
  if (name === "bash") {
    return "shell";
  }
  if (name === "read") {
    return "read_file";
  }
  if (name === "ls" || name === "find") {
    return "list_files";
  }
  if (name === "write" || name === "edit") {
    return "apply_patch";
  }
  return "runtime";
}

function sanitizeSkillSegment(value: string): string {
  const sanitized = value.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
  return sanitized || "unlabeled";
}

function assistantTextFromContent(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }
  if (!Array.isArray(content)) {
    return "";
  }
  return content
    .map((item) => {
      const record = safeRecord(item);
      return record.type === "text" ? stringValue(record.text) : "";
    })
    .filter(Boolean)
    .join("");
}

function usageHasTokens(usage: Record<string, unknown>): boolean {
  return Object.keys(usage).some((key) => typeof usage[key] === "number" && (usage[key] as number) > 0);
}

function sumPiUsageNumber(usages: Array<Record<string, unknown>>, key: string): number {
  return usages.reduce((total, usage) => {
    const value = usage[key];
    return typeof value === "number" && Number.isFinite(value) && value >= 0 ? total + Math.trunc(value) : total;
  }, 0);
}

function normalizePiExecEventsArtifact(stdout: string, stderr: string): string {
  const lines = stdout.trim() ? stdout.trim().split(/\r?\n/) : [];
  if (stderr.trim()) {
    lines.push(JSON.stringify({ type: "stderr", text: stderr }));
  }
  return lines.length ? `${lines.join("\n")}\n` : "";
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
        at: nowReadableDateTime(),
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

function sandboxCapabilities(task: AgentTask, options: { enableApplyPatchTool: boolean }) {
  const capabilities = options.enableApplyPatchTool
    ? Capabilities.default()
    : Capabilities.default().map((capability) => capability.type === "filesystem"
      ? filesystem({
        configureTools: (tools) => tools.filter((tool) => tool.type !== "apply_patch"),
      })
      : capability);
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
  delivery: "sdk_skill" | "prompt_inline" | "pi_skill_folder" = "sdk_skill",
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
    `## Skill: ${skill.name}`,
    `Required: ${skill.required ? "yes" : "no"}`,
    `Source path: ${skill.path}`,
    `Content SHA256: ${skill.content_sha256}`,
    "",
    skill.content.trim(),
  ].join("\n"));
  return [
    task.prompt,
    "",
    "# AGT-Routed Skill Bodies",
    "",
    "The following skill bodies were selected by AGT for this stage. Treat these sections as the active stage skills. Do not invoke unrelated local skills unless the stage prompt explicitly asks for them.",
    "",
    ...skillSections,
  ].join("\n");
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
