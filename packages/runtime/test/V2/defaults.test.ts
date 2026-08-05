import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { execa } from "execa";
import { describe, expect, it } from "vitest";

import {
  applyOpenAIExecutorEnv,
  buildAgentRunner,
  buildCodexExecPrompt,
  buildPiExecPrompt,
  commandsFromCodexExecEvents,
  commandsFromPiExecEvents,
  createTaskWorktree,
  finalMessageFromCodexExecEvents,
  finalMessageFromPiExecEvents,
  hasOpenAIExecutorConfig,
  initRuntime,
  materializePiSkills,
  parseCodexExecJsonl,
  parsePiExecJsonl,
  renderSkillInjection,
  resolveAgentExecutorPreference,
  resolveOpenAIExecutorConfig,
  resolveSkillRouting,
  sandboxWorkspacePermissions,
  shouldEnableOpenAISandboxApplyPatch,
  shouldEnableOpenAITracing,
  skillsForExecutor,
  summarizeCodexExecUsage,
  summarizeOpenAIUsage,
  summarizePiExecUsage,
  RuntimeStore,
} from "../../src/V2/index.js";
import { createSessionId } from "../../src/V2/ids.js";

describe("V2 runtime defaults", () => {
  it("keeps session ids compact", () => {
    const sessionId = createSessionId("Source: /Users/zhoukailian/Desktop/work/group_pals/.worktrees/agtv2-debug-20260623/test.md");

    expect(sessionId).toMatch(/^\d{8}T\d{9}-[a-f0-9]{8}$/);
    expect(sessionId).not.toContain("source-users");
    expect(sessionId.length).toBe(27);
  });

  it("uses .agt2 for the source runtime and task worktrees", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt2-defaults-"));
    await execa("git", ["init"], { cwd: repoRoot });
    await writeFile(path.join(repoRoot, "README.md"), "v2 defaults\n");
    await execa("git", ["add", "README.md"], { cwd: repoRoot });
    await execa("git", [
      "-c",
      "user.name=AGT Test",
      "-c",
      "user.email=agt-test@example.com",
      "commit",
      "-m",
      "initial",
    ], { cwd: repoRoot });

    const initialized = await initRuntime({ repoRoot });
    expect(initialized.stateRoot).toBe(path.join(repoRoot, ".agt2"));
    expect(initialized.configPath).toBe(path.join(repoRoot, ".agt2", "config.json"));
    const config = JSON.parse(await readFile(initialized.configPath, "utf8")) as {
      state_root: string;
      executor: { default_max_turns: number };
    };
    expect(config.state_root).toBe(".agt2");
    expect(config).not.toHaveProperty("default_profile");
    expect(config).not.toHaveProperty("max_turns");
    expect(config.executor.default_max_turns).toBe(8);

    const worktree = await createTaskWorktree({
      projectRoot: repoRoot,
      stateRoot: initialized.stateRoot,
      request: "ship v2 defaults",
    });
    expect(worktree.stateRoot).toBe(path.join(worktree.repoRoot, ".agt2"));
    expect(worktree.worktree.policy_snapshot_path).toBe(path.join(worktree.repoRoot, ".agt2", "config.json"));
  });

  it("summarizes OpenAI token usage without profile context", () => {
    const usage = summarizeOpenAIUsage([
      {
        usage: {
          input_tokens: 10,
          output_tokens: 4,
          output_tokens_details: { reasoning_tokens: 2 },
        },
      },
      {
        usage: {
          prompt_tokens: 3,
          completion_tokens: 5,
          completion_tokens_details: { reasoning_tokens: 1 },
        },
      },
    ]);

    expect(usage).toMatchObject({
      input_tokens: 13,
      output_tokens: 9,
      total_tokens: 22,
      reasoning_tokens: 3,
    });
    expect(JSON.stringify(usage)).not.toContain("profile");
  });

  it("falls back to ~/.codex OpenAI config when env vars are not set", async () => {
    const codexHome = await mkdtemp(path.join(tmpdir(), "agt2-codex-home-"));
    await writeFile(path.join(codexHome, "config.toml"), [
      'model = "gpt-5.5"',
      'model_provider = "smartingredients"',
      "",
      "[model_providers.smartingredients]",
      'name = "SmartIngredients Proxy"',
      'base_url = "https://example.invalid/v1"',
      'wire_api = "responses"',
      "",
    ].join("\n"));
    await writeFile(path.join(codexHome, "auth.json"), JSON.stringify({
      OPENAI_API_KEY: "sk-test",
    }));

    const resolved = resolveOpenAIExecutorConfig({
      env: {},
      codexHome,
      runtimeDefaultModel: "runtime-default",
    });

    expect(resolved).toMatchObject({
      apiKey: "sk-test",
      baseUrl: "https://example.invalid/v1",
      model: "gpt-5.5",
      apiKeySource: "codex",
      baseUrlSource: "codex",
      modelSource: "codex",
    });
    expect(hasOpenAIExecutorConfig(resolved)).toBe(true);

    const env: NodeJS.ProcessEnv = {};
    applyOpenAIExecutorEnv(resolved, env);
    expect(env.OPENAI_API_KEY).toBe("sk-test");
    expect(env.OPENAI_BASE_URL).toBe("https://example.invalid/v1");
    expect(env.OPENAI_MODEL).toBeUndefined();
  });

  it("keeps explicit env vars ahead of ~/.codex defaults", async () => {
    const codexHome = await mkdtemp(path.join(tmpdir(), "agt2-codex-home-"));
    await writeFile(path.join(codexHome, "config.toml"), [
      'model = "codex-model"',
      'model_provider = "codex_proxy"',
      "",
      "[model_providers.codex_proxy]",
      'base_url = "https://codex.invalid/v1"',
      "",
    ].join("\n"));
    await writeFile(path.join(codexHome, "auth.json"), JSON.stringify({
      OPENAI_API_KEY: "sk-codex",
    }));

    const resolved = resolveOpenAIExecutorConfig({
      env: {
        OPENAI_API_KEY: "sk-env",
        OPENAI_BASE_URL: "https://env.invalid/v1",
        AGT_OPENAI_MODEL: "env-model",
      },
      codexHome,
      runtimeDefaultModel: "runtime-default",
    });

    expect(resolved).toMatchObject({
      apiKey: "sk-env",
      baseUrl: "https://env.invalid/v1",
      model: "env-model",
      apiKeySource: "env",
      baseUrlSource: "env",
      modelSource: "env",
    });
  });

  it("disables SDK tracing for custom OpenAI-compatible base URLs", () => {
    expect(shouldEnableOpenAITracing({
      apiKey: "sk-test",
      apiKeySource: "env",
      baseUrlSource: "unset",
      modelSource: "runtime_default",
    })).toBe(true);
    expect(shouldEnableOpenAITracing({
      apiKey: "sk-test",
      baseUrl: "https://api.openai.com/v1",
      apiKeySource: "env",
      baseUrlSource: "env",
      modelSource: "runtime_default",
    })).toBe(true);
    expect(shouldEnableOpenAITracing({
      apiKey: "sk-test",
      baseUrl: "https://example.invalid/v1",
      apiKeySource: "env",
      baseUrlSource: "env",
      modelSource: "runtime_default",
    })).toBe(false);
  });

  it("disables SDK apply_patch for custom OpenAI-compatible base URLs", () => {
    expect(shouldEnableOpenAISandboxApplyPatch({
      apiKey: "sk-test",
      apiKeySource: "env",
      baseUrlSource: "unset",
      modelSource: "runtime_default",
    })).toBe(true);
    expect(shouldEnableOpenAISandboxApplyPatch({
      apiKey: "sk-test",
      baseUrl: "https://api.openai.com/v1",
      apiKeySource: "env",
      baseUrlSource: "env",
      modelSource: "runtime_default",
    })).toBe(true);
    expect(shouldEnableOpenAISandboxApplyPatch({
      apiKey: "sk-test",
      baseUrl: "https://example.invalid/v1",
      apiKeySource: "env",
      baseUrlSource: "env",
      modelSource: "runtime_default",
    })).toBe(false);
  });

  it("respects CODEX_HOME when falling back to Codex OpenAI config", async () => {
    const codexHome = await mkdtemp(path.join(tmpdir(), "agt2-codex-home-"));
    await writeFile(path.join(codexHome, "config.toml"), [
      'model = "codex-home-model"',
      'model_provider = "codex_home_proxy"',
      "",
      "[model_providers.codex_home_proxy]",
      'base_url = "https://codex-home.invalid/v1"',
      "",
    ].join("\n"));
    await writeFile(path.join(codexHome, "auth.json"), JSON.stringify({
      OPENAI_API_KEY: "sk-codex-home",
    }));

    const resolved = resolveOpenAIExecutorConfig({
      env: {
        CODEX_HOME: codexHome,
      },
      runtimeDefaultModel: "runtime-default",
    });

    expect(resolved).toMatchObject({
      apiKey: "sk-codex-home",
      baseUrl: "https://codex-home.invalid/v1",
      model: "codex-home-model",
      apiKeySource: "codex",
      baseUrlSource: "codex",
      modelSource: "codex",
    });
  });

  it("uses SDK-cleanup-safe numeric sandbox permissions", () => {
    expect(sandboxWorkspacePermissions(false)).toBe(0o755);
    expect(sandboxWorkspacePermissions(true)).toBe(0o755);
  });

  it("can select codex exec as the V2 executor without changing the default auto path", async () => {
    expect(resolveAgentExecutorPreference({})).toBe("auto");
    expect(resolveAgentExecutorPreference({ AGT_EXECUTOR: "codex" })).toBe("codex_exec");
    expect(resolveAgentExecutorPreference({ AGT_V2_EXECUTOR: "codex-exec" })).toBe("codex_exec");
    expect(resolveAgentExecutorPreference({ AGT_EXECUTOR: "openai-sdk" })).toBe("openai_sandbox");

    const stateRoot = await mkdtemp(path.join(tmpdir(), "agt2-runner-select-"));
    const store = new RuntimeStore(stateRoot);
    const previous = process.env.AGT_EXECUTOR;
    process.env.AGT_EXECUTOR = "codex_exec";
    try {
      expect(buildAgentRunner(store).name).toBe("codex_exec");
    } finally {
      if (previous === undefined) {
        delete process.env.AGT_EXECUTOR;
      } else {
        process.env.AGT_EXECUTOR = previous;
      }
    }
  });

  it("builds a codex exec prompt with AGT-controlled skill bodies", () => {
    const prompt = buildCodexExecPrompt({
      sessionId: "session",
      role: "dev",
      repoRoot: "/repo",
      prompt: "Base stage prompt.",
      skills: [{
        name: "backend-verification",
        description: "Verify backend changes.",
        content: "# Backend Verification\nRun API checks.",
        path: "/skills/backend-verification/SKILL.md",
        content_sha256: "abc123",
        required: true,
      }],
    });

    expect(prompt).toContain("Base stage prompt.");
    expect(prompt).toContain("# AGT-Routed Skill Bodies");
    expect(prompt).toContain("## Skill: backend-verification");
    expect(prompt).toContain("Run API checks.");
  });

  it("parses codex exec JSONL events into output, commands, and usage", () => {
    const events = parseCodexExecJsonl([
      JSON.stringify({ type: "thread.started", thread_id: "thread" }),
      JSON.stringify({ type: "item.completed", item: { type: "command_execution", command: "npm test", status: "completed" } }),
      JSON.stringify({ type: "item.completed", item: { type: "agent_message", text: "done" } }),
      JSON.stringify({
        type: "turn.completed",
        usage: {
          input_tokens: 10,
          cached_input_tokens: 4,
          output_tokens: 3,
          reasoning_output_tokens: 2,
        },
      }),
    ].join("\n"));

    expect(commandsFromCodexExecEvents(events)).toEqual(["npm test"]);
    expect(finalMessageFromCodexExecEvents(events)).toBe("done");
    expect(summarizeCodexExecUsage(events)).toMatchObject({
      input_tokens: 10,
      output_tokens: 3,
      total_tokens: 13,
      reasoning_tokens: 2,
    });
  });

  it("can select pi as the V2 executor without changing the default auto path", async () => {
    expect(resolveAgentExecutorPreference({ AGT_EXECUTOR: "pi" })).toBe("pi_exec");
    expect(resolveAgentExecutorPreference({ AGT_V2_EXECUTOR: "pi-exec" })).toBe("pi_exec");
    expect(resolveAgentExecutorPreference({ AGT_EXECUTOR: "pi_exec" })).toBe("pi_exec");

    const stateRoot = await mkdtemp(path.join(tmpdir(), "agt2-pi-runner-select-"));
    const store = new RuntimeStore(stateRoot);
    const previous = process.env.AGT_EXECUTOR;
    process.env.AGT_EXECUTOR = "pi_exec";
    try {
      expect(buildAgentRunner(store).name).toBe("pi_exec");
    } finally {
      if (previous === undefined) {
        delete process.env.AGT_EXECUTOR;
      } else {
        process.env.AGT_EXECUTOR = previous;
      }
    }
  });

  it("materializes stage skills into per-stage pi skill folders", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt2-pi-skills-repo-"));
    const skillsRoot = await mkdtemp(path.join(tmpdir(), "agt2-pi-skills-root-"));
    const materialized = await materializePiSkills({
      sessionId: "session",
      role: "dev",
      repoRoot,
      prompt: "Base stage prompt.",
      stage: "dev.implementation",
      skills: [{
        name: "implementation-skill",
        description: "Implement changes.",
        content: "# Implementation Skill\nFollow the plan.",
        path: path.join(skillsRoot, "implementation-skill", "SKILL.md"),
        content_sha256: "def456",
        required: true,
      }],
    }, skillsRoot);

    expect(materialized.skillDirs).toHaveLength(1);
    expect(materialized.skillDirs[0]).toContain(path.join("dev.implementation", "implementation-skill"));
    expect(materialized.index[0]).toMatchObject({
      name: "implementation-skill",
      content_sha256: "def456",
      required: true,
    });
    const skillMd = await readFile(path.join(materialized.skillDirs[0], "SKILL.md"), "utf8");
    expect(skillMd).toContain("Follow the plan.");
  });

  it("builds a pi exec prompt that references materialized skill folders instead of inlining bodies", () => {
    const prompt = buildPiExecPrompt({
      sessionId: "session",
      role: "dev",
      repoRoot: "/repo",
      prompt: "Base stage prompt.",
      stage: "dev.implementation",
      skills: [{
        name: "implementation-skill",
        description: "Implement changes.",
        content: "# Implementation Skill\nFollow the plan.",
        path: "/skills/implementation-skill/SKILL.md",
        content_sha256: "def456",
        required: true,
      }],
    }, {
      skillDirs: ["/repo/.agt2/pi-skills/dev.implementation/implementation-skill"],
      index: [{
        name: "implementation-skill",
        path: "/repo/.agt2/pi-skills/dev.implementation/implementation-skill",
        relative_path: ".agt2/pi-skills/dev.implementation/implementation-skill",
        content_sha256: "def456",
        required: true,
      }],
    });

    expect(prompt).toContain("Base stage prompt.");
    expect(prompt).toContain("# AGT Stage Skills");
    expect(prompt).toContain("Path (relative to repo root): .agt2/pi-skills/dev.implementation/implementation-skill");
    expect(prompt).not.toContain("Follow the plan.");
    expect(prompt).not.toContain("# AGT-Routed Skill Bodies");
  });

  it("parses pi exec JSONL events into output, commands, and usage", () => {
    const events = parsePiExecJsonl([
      JSON.stringify({ type: "session", version: 3, id: "s1", timestamp: "t", cwd: "/repo" }),
      JSON.stringify({ type: "agent_start" }),
      JSON.stringify({
        type: "message_end",
        message: {
          role: "assistant",
          content: [{ type: "text", text: "first draft" }, { type: "thinking", thinking: "hidden" }],
          responseId: "r1",
          usage: { input: 10, output: 2, cacheRead: 3, cacheWrite: 1, reasoning: 1, cost: { total: 0 } },
        },
      }),
      JSON.stringify({
        type: "tool_execution_start",
        toolCallId: "c1",
        toolName: "bash",
        args: { command: "npm test" },
      }),
      JSON.stringify({
        type: "tool_execution_end",
        toolCallId: "c1",
        toolName: "bash",
        result: { content: [{ type: "text", text: "ok" }] },
        isError: false,
      }),
      JSON.stringify({
        type: "message_end",
        message: {
          role: "assistant",
          content: [{ type: "text", text: "final answer" }],
          responseId: "r2",
          usage: { input: 20, output: 5, cacheRead: 0, cacheWrite: 0, cost: { total: 0 } },
        },
      }),
      JSON.stringify({ type: "agent_end" }),
    ].join("\n"));

    expect(commandsFromPiExecEvents(events)).toEqual(["npm test"]);
    expect(finalMessageFromPiExecEvents(events)).toBe("final answer");
    expect(summarizePiExecUsage(events)).toMatchObject({
      input_tokens: 30,
      output_tokens: 7,
      total_tokens: 41,
      reasoning_tokens: 1,
    });
  });

  it("routes V2 skills by concrete stage without broad role bleed-through", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt2-routing-repo-"));
    const configRoot = await mkdtemp(path.join(tmpdir(), "agt2-routing-config-"));
    const skillsRoot = await mkdtemp(path.join(tmpdir(), "agt2-routing-skills-"));
    for (const name of ["route-skill", "product-skill", "plan-skill", "implementation-skill", "qa-skill"]) {
      await mkdir(path.join(skillsRoot, name), { recursive: true });
      const descriptionLines = name === "product-skill"
        ? ["description: |", `  ${name} description`]
        : [`description: ${name} description`];
      await writeFile(path.join(skillsRoot, name, "SKILL.md"), [
        "---",
        `name: ${name}`,
        ...descriptionLines,
        "---",
        "",
        `# ${name}`,
        "",
        `${name} private body.`,
        "",
      ].join("\n"));
    }
    const projectConfigDir = path.join(configRoot, path.basename(repoRoot));
    await mkdir(projectConfigDir, { recursive: true });
    await writeFile(path.join(projectConfigDir, "skill-routing.yaml"), [
      "schema_version: 0.1",
      "project:",
      `  name: ${path.basename(repoRoot)}`,
      "  repo_family:",
      `    - ${repoRoot}`,
      "skill_sources:",
      "  installed_skills:",
      `    - ${skillsRoot}`,
      "stage_routes:",
      "  route:",
      "    required_skills:",
      "      - route-skill",
      "  product_definition:",
      "    required_skills:",
      "      - product-skill",
      "  technical_design:",
      "    required_skills:",
      "      - plan-skill",
      "  implementation:",
      "    required_skills:",
      "      - implementation-skill",
      "  backend_verification:",
      "    required_skills:",
      "      - qa-skill",
      "",
    ].join("\n"));

    const previousConfigRoot = process.env.AGT_PROJECT_CONFIG_ROOT;
    process.env.AGT_PROJECT_CONFIG_ROOT = configRoot;
    try {
      const intake = await resolveSkillRouting({
        repoRoot,
        projectRoot: repoRoot,
        workflowId: "product-dev-qa",
        stage: "intake_summary",
        role: "intake_summary",
      });
      expect(intake.selected_skills.map((skill) => skill.name)).toEqual([]);

      const product = await resolveSkillRouting({
        repoRoot,
        projectRoot: repoRoot,
        workflowId: "product-dev-qa",
        stage: "product",
        role: "product",
      });
      expect(product.selected_skills.map((skill) => skill.name)).toEqual(["product-skill"]);
      expect(product.missing_skills).toEqual([]);
      expect(product.missing_required_skills).toEqual([]);
      expect(product.selected_skills[0]).toMatchObject({
        description: "product-skill description",
        delivery: "sdk_skill",
        included_in_prompt: false,
      });
      const productPromptSkills = renderSkillInjection(product);
      expect(productPromptSkills).toContain("Available skills: product-skill");
      expect(productPromptSkills).toContain("Skill bodies are provided to compatible executors as SDK skills");
      expect(productPromptSkills).not.toContain("product-skill private body.");
      expect(skillsForExecutor(product)).toEqual([
        expect.objectContaining({
          name: "product-skill",
          description: "product-skill description",
          content: expect.stringContaining("product-skill private body."),
          required: true,
        }),
      ]);

      const technicalPlan = await resolveSkillRouting({
        repoRoot,
        projectRoot: repoRoot,
        workflowId: "product-dev-qa",
        stage: "dev.technical_plan",
        role: "dev",
      });
      expect(technicalPlan.selected_skills.map((skill) => skill.name)).toEqual(["plan-skill"]);

      const implementation = await resolveSkillRouting({
        repoRoot,
        projectRoot: repoRoot,
        workflowId: "product-dev-qa",
        stage: "dev.implementation",
        role: "dev",
      });
      expect(implementation.selected_skills.map((skill) => skill.name)).toEqual(["implementation-skill"]);

      const qa = await resolveSkillRouting({
        repoRoot,
        projectRoot: repoRoot,
        workflowId: "product-dev-qa",
        stage: "qa",
        role: "qa",
      });
      expect(qa.selected_skills.map((skill) => skill.name)).toEqual(["qa-skill"]);
    } finally {
      if (previousConfigRoot === undefined) {
        delete process.env.AGT_PROJECT_CONFIG_ROOT;
      } else {
        process.env.AGT_PROJECT_CONFIG_ROOT = previousConfigRoot;
      }
    }
  });
});
