import { Agent, run, setTracingDisabled } from "@openai/agents";
import { SandboxAgent } from "@openai/agents/sandbox";
import { Capabilities } from "@openai/agents/sandbox";
import { localDir } from "@openai/agents/sandbox";
import { UnixLocalSandboxClient } from "@openai/agents/sandbox/local";
import { execa } from "execa";
import {
  type AgentRole,
  type AgentRunRecord,
  type RuntimeProfile,
  type ToolCallRecord,
  nowIso,
} from "./schema.js";
import { RuntimeStore } from "./store.js";

export type AgentTask = {
  sessionId: string;
  role: AgentRole;
  profile: RuntimeProfile;
  repoRoot: string;
  prompt: string;
  writeAllowed?: boolean;
  maxTurns?: number;
};

export type AgentTaskResult = {
  agentRun: AgentRunRecord;
  output: string;
  filesChanged: string[];
  commandsRun: string[];
};

export type AgentRunner = {
  name: AgentRunRecord["runner"];
  // 执行一个 workflow stage，并返回 agent run、输出和可观察证据。
  // Runs one workflow stage and returns the agent run, output, and observable evidence.
  runTask(task: AgentTask): Promise<AgentTaskResult>;
};

// 根据环境变量选择真实 OpenAI sandbox runner 或本地 deterministic fallback。
// Selects the real OpenAI sandbox runner or deterministic local fallback from environment variables.
export function buildAgentRunner(store: RuntimeStore): AgentRunner {
  if (process.env.OPENAI_API_KEY || process.env.OPENAI_BASE_URL) {
    return new OpenAISandboxRunner(store);
  }
  return new LocalFallbackRunner(store);
}

// OpenAISandboxRunner：通过 OpenAI Agents SDK 在 sandbox 中执行 stage agent。
// OpenAISandboxRunner: executes stage agents in a sandbox through the OpenAI Agents SDK.
export class OpenAISandboxRunner implements AgentRunner {
  readonly name = "openai_sandbox" as const;

  // 保存 RuntimeStore，用于写入 agent run、tool call 和 artifact trace。
  // Stores RuntimeStore so agent runs, tool calls, and artifact traces can be written.
  constructor(private readonly store: RuntimeStore) {}

  // 执行一个 stage prompt，并把 SDK 结果转成 runtime 的标准 trace。
  // Runs one stage prompt and converts SDK results into the runtime trace schema.
  async runTask(task: AgentTask): Promise<AgentTaskResult> {
    const config = await this.store.loadConfig();
    const model = process.env.AGT_OPENAI_MODEL || process.env.OPENAI_MODEL || config.default_model;
    const maxTurns = task.maxTurns ?? config.max_turns[task.profile];
    setTracingDisabled(false);
    const agentRun = await this.store.createAgentRun({
      sessionId: task.sessionId,
      role: task.role,
      runner: this.name,
      input: task.prompt,
      metadata: { profile: task.profile, write_allowed: Boolean(task.writeAllowed), model, max_turns: maxTurns },
    });
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
                permissions: task.writeAllowed ? "read_write" : "read_only",
              }),
            },
          },
        },
      });
      const output = stringifyFinalOutput(result.finalOutput);
      const filesChanged = await this.changedFiles(task.repoRoot, toolCallsBefore);
      const commandsRun = commandsFromRunItems(result.newItems);
      await this.recordSdkToolCalls(task, agentRun, result.newItems);
      const sdkTrace = await this.store.writeArtifact({
        sessionId: task.sessionId,
        role: task.role,
        name: `${agentRun.agent_run_id}-sdk-trace.json`,
        content: JSON.stringify(summarizeOpenAIResult(result), null, 2),
        metadata: { agent_run_id: agentRun.agent_run_id, kind: "sdk_trace" },
      });
      const completed = await this.store.completeAgentRun(agentRun, {
        status: "completed",
        output,
        metadata: {
          ...agentRun.metadata,
          raw_response_count: result.rawResponses.length,
          new_item_count: result.newItems.length,
          last_response_id: result.lastResponseId ?? "",
          sdk_trace_artifact_path: sdkTrace.path,
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
        },
      });
      return { agentRun: completed, output, filesChanged, commandsRun };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const completed = await this.store.completeAgentRun(agentRun, {
        status: "failed",
        error: message,
        output: "",
      });
      await this.recordRuntimeToolCall(task, completed, {
        name: "openai_sandbox_error",
        started,
        output: { error: message },
      });
      return { agentRun: completed, output: message, filesChanged: [], commandsRun: [] };
    }
  }

  // 创建带有角色说明和读写权限约束的 SandboxAgent。
  // Creates a SandboxAgent with role instructions and read/write permission constraints.
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
      capabilities: Capabilities.default(),
      model,
    });
  }

  // 从 SDK run items 中提取 tool-like 记录，并写入 tool-calls.jsonl。
  // Extracts tool-like records from SDK run items and writes them to tool-calls.jsonl.
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

  // 记录 runtime 自身的一次 agent_run 级别 tool call。
  // Records the runtime's own agent_run-level tool call.
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
      input: { profile: task.profile, write_allowed: Boolean(task.writeAllowed) },
      output: args.output,
      duration_ms: Date.now() - args.started,
    };
    await this.store.appendToolCall(call);
  }

  // 捕获执行前的 git diff 文件列表，用于后续计算新增变更。
  // Captures the pre-run git diff file list so later changes can be calculated.
  private async snapshotGit(repoRoot: string): Promise<string> {
    try {
      const result = await execa("git", ["diff", "--name-only"], { cwd: repoRoot });
      return result.stdout;
    } catch {
      return "";
    }
  }

  // 对比执行前后的 git diff，返回本次 stage 新增变化的文件。
  // Compares git diff before and after execution and returns files newly changed by this stage.
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

// LocalFallbackRunner：无 OpenAI 环境变量时的确定性本地 runner。
// LocalFallbackRunner: deterministic local runner used when OpenAI environment variables are missing.
export class LocalFallbackRunner implements AgentRunner {
  readonly name = "local_fallback" as const;

  // 保存 RuntimeStore，用于记录 fallback run 的状态和 tool call。
  // Stores RuntimeStore so fallback run state and tool calls can be recorded.
  constructor(private readonly store: RuntimeStore) {}

  // 执行本地 fallback，只采集 git status 作为 smoke evidence。
  // Runs the local fallback and records git status as smoke-test evidence.
  async runTask(task: AgentTask): Promise<AgentTaskResult> {
    const agentRun = await this.store.createAgentRun({
      sessionId: task.sessionId,
      role: task.role,
      runner: this.name,
      input: task.prompt,
      metadata: {
        profile: task.profile,
        reason: "OPENAI_API_KEY/OPENAI_BASE_URL not set; using deterministic local runner.",
      },
    });
    const started = Date.now();
    const git = await runGitStatus(task.repoRoot);
    const output = [
      `${task.role} local fallback completed.`,
      `Profile: ${task.profile}`,
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
    const completed = await this.store.completeAgentRun(agentRun, {
      status: "completed",
      output,
    });
    return {
      agentRun: completed,
      output,
      filesChanged: git.changedFiles,
      commandsRun: ["git status --short"],
    };
  }
}

// 执行 git status --short，并整理变更文件列表和摘要。
// Runs git status --short and normalizes changed files plus a summary.
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

// 把 SDK finalOutput 统一转成可写入 artifact 的字符串。
// Converts SDK finalOutput into a string suitable for artifact storage.
function stringifyFinalOutput(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (value === undefined || value === null) {
    return "";
  }
  return JSON.stringify(value, null, 2);
}

// 序列化 SDK run item，优先使用 toJSON 输出。
// Serializes an SDK run item, preferring its toJSON output.
function serializeRunItem(value: unknown): Record<string, unknown> {
  const withToJson = value as { toJSON?: () => unknown };
  return safeRecord(typeof withToJson?.toJSON === "function" ? withToJson.toJSON() : value);
}

// 压缩 OpenAI SDK 结果，生成可落盘的 sdk trace artifact。
// Summarizes an OpenAI SDK result into a persisted sdk trace artifact.
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

// 摘要化单个 raw response，避免把完整响应直接塞进控制台。
// Summarizes one raw response so the console does not need the full response body.
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

// 摘要化单个 run item，并裁剪过长输入输出。
// Summarizes one run item and truncates overly large inputs and outputs.
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

// 从 shell_call run items 中提取去重后的命令列表。
// Extracts a deduplicated command list from shell_call run items.
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

// 判断 SDK run item 类型是否应记录为 runtime tool call。
// Checks whether an SDK run item type should be recorded as a runtime tool call.
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

// 将 SDK run item 类型映射到 runtime tool call kind。
// Maps an SDK run item type to a runtime tool-call kind.
function kindForRunItem(rawType: string): ToolCallRecord["kind"] {
  if (rawType.startsWith("shell_call")) {
    return "shell";
  }
  if (rawType.startsWith("apply_patch_call")) {
    return "apply_patch";
  }
  return "runtime";
}

// 为 SDK run item 推导一个稳定的 tool call 名称。
// Derives a stable tool-call name for an SDK run item.
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

// 从 SDK run item 中抽取适合落盘的输入字段。
// Extracts persistable input fields from an SDK run item.
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

// 从 SDK run item 中抽取适合落盘的输出字段。
// Extracts persistable output fields from an SDK run item.
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

// 从 shell_call_output 中解析退出码；无法解析时保持 undefined。
// Parses exit code from shell_call_output and leaves it undefined when unavailable.
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

// 把 unknown 安全收窄为普通对象；非对象返回空对象。
// Safely narrows unknown to a plain record and returns an empty record otherwise.
function safeRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

// 把 unknown 安全收窄为字符串；非字符串返回空串。
// Safely narrows unknown to a string and returns an empty string otherwise.
function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

// 裁剪过长字符串，避免 trace artifact 和 UI 输出过大。
// Truncates overly long strings so trace artifacts and UI output stay bounded.
function redactLargeStrings(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      typeof item === "string" && item.length > 4000 ? `${item.slice(0, 4000)}...<truncated>` : item,
    ]),
  );
}
