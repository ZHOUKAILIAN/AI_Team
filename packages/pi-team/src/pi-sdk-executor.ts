import {
  createAgentSession,
  DefaultResourceLoader,
  getAgentDir,
  ModelRuntime,
  SessionManager,
  type AgentSessionEvent,
} from "@earendil-works/pi-coding-agent";
import type { RoleExecutionInput, RoleExecutionResult, RoleExecutor } from "./types.js";
import { loadRoleDefinition } from "./roles.js";

export type PiSdkExecutorOptions = {
  modelRuntime?: ModelRuntime;
  model?: Parameters<typeof createAgentSession>[0] extends infer T
    ? T extends { model?: infer M }
      ? M
      : never
    : never;
  thinkingLevel?: "off" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max";
  tools?: string[];
  agentDir?: string;
  onEvent?: (event: AgentSessionEvent) => void;
};

/** Thin adapter around pi's AgentSession. Team orchestration remains outside pi. */
export class PiSdkExecutor implements RoleExecutor {
  constructor(private readonly options: PiSdkExecutorOptions = {}) {}

  async run(input: RoleExecutionInput): Promise<RoleExecutionResult> {
    const events: unknown[] = [];
    const role = await loadRoleDefinition({ role: input.role, cwd: input.repoRoot, agentDir: this.options.agentDir });
    const agentDir = this.options.agentDir ?? getAgentDir();
    const modelRuntime = this.options.modelRuntime ?? await ModelRuntime.create({});
    const roleModel = role.model ? resolveRoleModel(modelRuntime, role.model) : undefined;
    const selectedSkills: Array<{ name: string; filePath: string }> = [];
    const requestedSkills = input.skillNames ?? role.skills ?? [];
    const requiredSkills = new Set(input.requiredSkillNames ?? role.requiredSkills ?? []);
    const allowedSkills = new Set([...requestedSkills, ...requiredSkills]);
    const loader = new DefaultResourceLoader({
      cwd: input.repoRoot,
      agentDir,
      systemPromptOverride: () => role.systemPrompt,
      skillsOverride: (base) => {
        const skills = base.skills.filter((skill) => allowedSkills.has(skill.name));
        selectedSkills.splice(0, selectedSkills.length, ...skills.map((skill) => ({ name: skill.name, filePath: skill.filePath })));
        const loadedNames = new Set(skills.map((skill) => skill.name));
        const missing = [...requiredSkills].filter((name) => !loadedNames.has(name));
        if (missing.length > 0) throw new Error(`Required pi skills not found for ${input.stage}/${input.role}: ${missing.join(", ")}`);
        return { skills, diagnostics: base.diagnostics };
      },
    });
    await loader.reload();
    const { session } = await createAgentSession({
      cwd: input.repoRoot,
      agentDir: this.options.agentDir,
      modelRuntime,
      model: this.options.model ?? roleModel,
      thinkingLevel: this.options.thinkingLevel,
      tools: this.options.tools ?? role.tools,
      resourceLoader: loader,
      sessionManager: SessionManager.inMemory(input.repoRoot),
    });
    const unsubscribe = session.subscribe((event: AgentSessionEvent) => {
      events.push(event);
      input.onEvent?.(event);
      this.options.onEvent?.(event);
    });
    try {
      await session.prompt(input.prompt);
      return {
        status: "completed",
        output: collectAssistantText(events),
        events,
        filesChanged: [],
        commandsRun: collectCommands(events),
        skills: selectedSkills,
      };
    } finally {
      unsubscribe();
      session.dispose();
    }
  }
}

function collectAssistantText(events: unknown[]): string {
  let output = "";
  for (const event of events) {
    const record = asRecord(event);
    if (record.type !== "message_end") continue;
    const message = asRecord(record.message);
    if (message.role !== "assistant") continue;
    const content = Array.isArray(message.content) ? message.content : [];
    const text = content
      .map((item) => asRecord(item))
      .filter((item) => item.type === "text")
      .map((item) => typeof item.text === "string" ? item.text : "")
      .join("");
    if (text) output = text;
  }
  return output;
}

function collectCommands(events: unknown[]): string[] {
  return [...new Set(events
    .map((event) => asRecord(event))
    .filter((event) => event.type === "tool_execution_start" && event.toolName === "bash")
    .map((event) => asRecord(event.args).command)
    .filter((command): command is string => typeof command === "string"))];
}

function resolveRoleModel(runtime: ModelRuntime, value: string) {
  const separator = value.indexOf("/");
  if (separator <= 0 || separator === value.length - 1) {
    throw new Error(`Pi agent model must use provider/model format: ${value}`);
  }
  const model = runtime.getModel(value.slice(0, separator), value.slice(separator + 1));
  if (!model) {
    throw new Error(`Pi agent model is not available: ${value}`);
  }
  return model;
}
function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" ? value as Record<string, any> : {};
}
