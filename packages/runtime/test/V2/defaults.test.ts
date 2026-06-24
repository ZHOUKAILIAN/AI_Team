import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { execa } from "execa";
import { describe, expect, it } from "vitest";

import {
  applyOpenAIExecutorEnv,
  createTaskWorktree,
  hasOpenAIExecutorConfig,
  initRuntime,
  renderSkillInjection,
  resolveOpenAIExecutorConfig,
  resolveSkillRouting,
  sandboxWorkspacePermissions,
  skillsForExecutor,
  summarizeOpenAIUsage,
} from "../../src/V2/index.js";

describe("V2 runtime defaults", () => {
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
