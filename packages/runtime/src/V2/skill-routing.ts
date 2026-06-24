import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { type AgentRole } from "./schema.js";

export type ResolvedSkill = {
  name: string;
  description: string;
  required: boolean;
  source: "project_config" | "installed" | "missing";
  scope: "project";
  delivery: "prompt" | "sdk_skill" | "missing";
  path: string;
  content_sha256: string;
  included_in_prompt: boolean;
  reason: string;
  content?: string;
};

export type RoutedExecutorSkill = {
  name: string;
  description: string;
  content: string;
  path: string;
  content_sha256: string;
  required: boolean;
};

export type SkillRoutingDecision = {
  config_path: string;
  project_name: string;
  workflow_id: string;
  stage: string;
  role: AgentRole;
  matched: boolean;
  selected_skills: ResolvedSkill[];
  missing_skills: string[];
  missing_required_skills: string[];
  reasons: string[];
};

type SkillRequirement = {
  name: string;
  required: boolean;
};

type RoutingConfig = {
  path: string;
  projectName: string;
  repoFamily: string[];
  skillDirs: string[];
  stageRoutes: Record<string, SkillRequirement[]>;
};

export async function resolveSkillRouting(args: {
  repoRoot: string;
  projectRoot: string;
  workflowId: string;
  stage: string;
  role: AgentRole;
}): Promise<SkillRoutingDecision> {
  const candidates = await routingConfigCandidates(args.repoRoot, args.projectRoot);
  const reasons: string[] = [];
  for (const candidate of candidates) {
    if (!existsSync(candidate)) {
      reasons.push(`missing config: ${candidate}`);
      continue;
    }
    const config = parseRoutingConfig(candidate, await readFile(candidate, "utf8"));
    if (!configMatchesRepo(config, args.repoRoot, args.projectRoot)) {
      reasons.push(`config did not match repo: ${candidate}`);
      continue;
    }
    const skillRequirements = skillRequirementsForStage(config, args.stage, args.role);
    const selected = await Promise.all(skillRequirements.map((requirement) => resolveSkill(requirement, config.skillDirs)));
    return {
      config_path: candidate,
      project_name: config.projectName,
      workflow_id: args.workflowId,
      stage: args.stage,
      role: args.role,
      matched: true,
      selected_skills: selected,
      missing_skills: selected.filter((skill) => skill.source === "missing").map((skill) => skill.name),
      missing_required_skills: selected
        .filter((skill) => skill.required && skill.source === "missing")
        .map((skill) => skill.name),
      reasons: [
        ...reasons,
        skillRequirements.length ? `matched ${skillRequirements.length} skill(s)` : `no skills configured for ${args.role}`,
      ],
    };
  }
  return {
    config_path: "",
    project_name: projectNameFromPath(args.projectRoot || args.repoRoot),
    workflow_id: args.workflowId,
    stage: args.stage,
    role: args.role,
    matched: false,
    selected_skills: [],
    missing_skills: [],
    missing_required_skills: [],
    reasons,
  };
}

export function skillRoutingMetadata(decision: SkillRoutingDecision): Record<string, unknown> {
  return {
    project_name: decision.project_name,
    workflow_id: decision.workflow_id,
    stage: decision.stage,
    role: decision.role,
    matched: decision.matched,
    skills: decision.selected_skills
      .filter((skill) => skill.source !== "missing")
      .map((skill) => skill.name),
    missing_skills: decision.missing_skills,
    missing_required_skills: decision.missing_required_skills,
  };
}

export function skillRoutingAuditMetadata(decision: SkillRoutingDecision): Record<string, unknown> {
  return {
    config_path: decision.config_path,
    project_name: decision.project_name,
    workflow_id: decision.workflow_id,
    stage: decision.stage,
    role: decision.role,
    matched: decision.matched,
    selected_skill_count: decision.selected_skills.length,
    provided_skill_count: decision.selected_skills.filter((skill) => skill.source !== "missing").length,
    prompt_injected_skill_count: decision.selected_skills.filter((skill) => skill.included_in_prompt).length,
    missing_skills: decision.missing_skills,
    missing_required_skills: decision.missing_required_skills,
    reasons: decision.reasons,
    selected_skills: decision.selected_skills.map(({ content, ...skill }) => skill),
  };
}

export function renderSkillInjection(decision: SkillRoutingDecision): string {
  if (!decision.matched && decision.selected_skills.length === 0) {
    return "";
  }
  const sections = [
    "# Routed Skills",
    decision.selected_skills.length
      ? `Available skills: ${decision.selected_skills.filter((skill) => skill.source !== "missing").map((skill) => skill.name).join(", ") || "none"}`
      : "Available skills: none",
    "Skill bodies are provided to compatible executors as SDK skills and are not embedded in this prompt.",
  ];
  if (decision.missing_skills.length) {
    sections.push(`Missing skills: ${decision.missing_skills.join(", ")}`);
  }
  if (decision.missing_required_skills.length) {
    sections.push(`Missing required skills: ${decision.missing_required_skills.join(", ")}`);
  }
  for (const skill of decision.selected_skills) {
    sections.push(
      [
        `## Skill: ${skill.name}`,
        `Description: ${skill.description || "No description provided."}`,
        `Delivery: ${skill.delivery}`,
        `Path: ${skill.path || "not found"}`,
        skill.source === "missing" ? `Status: ${skill.reason}` : "",
      ].join("\n"),
    );
  }
  return sections.join("\n\n");
}

export function skillsForExecutor(decision: SkillRoutingDecision): RoutedExecutorSkill[] {
  return decision.selected_skills
    .filter((skill): skill is ResolvedSkill & { content: string } => skill.source !== "missing" && Boolean(skill.content))
    .map((skill) => ({
      name: skill.name,
      description: skill.description || "No description provided.",
      content: skill.content,
      path: skill.path,
      content_sha256: skill.content_sha256,
      required: skill.required,
    }));
}

async function routingConfigCandidates(repoRoot: string, projectRoot: string): Promise<string[]> {
  const explicit = process.env.AGT_SKILL_ROUTING_CONFIG ? [process.env.AGT_SKILL_ROUTING_CONFIG] : [];
  const roots = [projectRoot, repoRoot].filter(Boolean).map((item) => path.resolve(item));
  const names = [...new Set(roots.map(projectNameFromPath).filter(Boolean))];
  const projectConfigRoot = process.env.AGT_PROJECT_CONFIG_ROOT || defaultProjectConfigRoot();
  const projectConfigs = projectConfigRoot
    ? names.map((name) => path.join(projectConfigRoot, name, "skill-routing.yaml"))
    : [];
  const repoLocal = roots.map((root) => path.join(root, ".agt2", "skill-routing.yaml"));
  const discoverable = await discoverProjectRoutingConfigs(projectConfigRoot);
  return [...new Set([...explicit, ...projectConfigs, ...repoLocal, ...discoverable])];
}

async function discoverProjectRoutingConfigs(root: string): Promise<string[]> {
  if (!root) {
    return [];
  }
  if (!existsSync(root)) {
    return [];
  }
  const { readdir } = await import("node:fs/promises");
  const entries = await readdir(root, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(root, entry.name, "skill-routing.yaml"));
}

function parseRoutingConfig(configPath: string, content: string): RoutingConfig {
  const lines = content.split(/\r?\n/);
  const config: RoutingConfig = {
    path: configPath,
    projectName: projectNameFromPath(path.dirname(configPath)),
    repoFamily: [],
    skillDirs: defaultSkillDirs(),
    stageRoutes: {},
  };
  let section = "";
  let stage = "";
  let listTarget = "";
  let primaryRepo = false;
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const indent = line.length - line.trimStart().length;
    if (indent === 0 && trimmed.endsWith(":")) {
      section = trimmed.slice(0, -1);
      stage = "";
      listTarget = "";
      primaryRepo = false;
      continue;
    }
    if (section === "project" && indent === 2 && trimmed.startsWith("name:")) {
      config.projectName = scalarValue(trimmed);
      continue;
    }
    if (section === "project" && indent === 2 && trimmed.startsWith("repo_family:")) {
      listTarget = "repo_family";
      continue;
    }
    if (listTarget === "repo_family" && indent >= 4 && trimmed.startsWith("- ")) {
      config.repoFamily.push(scalarValue(trimmed.slice(2)));
      continue;
    }
    if (section === "skill_sources" && indent === 2) {
      primaryRepo = trimmed === "primary_repo:";
      if (trimmed === "installed_skills:") {
        listTarget = "installed_skills";
      }
      continue;
    }
    if (section === "skill_sources" && primaryRepo && indent === 4 && trimmed.startsWith("path:")) {
      config.skillDirs.push(expandHome(scalarValue(trimmed)));
      continue;
    }
    if (section === "skill_sources" && listTarget === "installed_skills" && indent >= 4 && trimmed.startsWith("- ")) {
      config.skillDirs.push(expandHome(scalarValue(trimmed.slice(2))));
      continue;
    }
    if (section === "stage_routes" && indent === 2 && trimmed.endsWith(":")) {
      stage = trimmed.slice(0, -1);
      config.stageRoutes[stage] = config.stageRoutes[stage] ?? [];
      listTarget = "";
      continue;
    }
    if (section === "stage_routes" && stage && indent === 4 && ["required_skills:", "optional_skills:"].includes(trimmed)) {
      listTarget = `${stage}.${trimmed.slice(0, -1)}`;
      continue;
    }
    if (section === "stage_routes" && stage && listTarget.startsWith(`${stage}.`) && indent >= 6 && trimmed.startsWith("- ")) {
      config.stageRoutes[stage]?.push({
        name: scalarValue(trimmed.slice(2)),
        required: listTarget.endsWith(".required_skills"),
      });
    }
  }
  config.skillDirs = [...new Set(config.skillDirs.filter(Boolean).map((dir) => path.resolve(expandHome(dir))))];
  return config;
}

function configMatchesRepo(config: RoutingConfig, repoRoot: string, projectRoot: string): boolean {
  if (process.env.AGT_SKILL_ROUTING_CONFIG && path.resolve(process.env.AGT_SKILL_ROUTING_CONFIG) === path.resolve(config.path)) {
    return true;
  }
  const roots = [repoRoot, projectRoot].filter(Boolean).map((item) => path.resolve(item));
  if (roots.some((root) => projectNameFromPath(root) === config.projectName)) {
    return true;
  }
  return config.repoFamily.some((pattern) => roots.some((root) => globMatch(expandHome(pattern), root)));
}

function skillRequirementsForStage(config: RoutingConfig, stage: string, role: AgentRole): SkillRequirement[] {
  const aliases = stageAliases(stage, role);
  const requirements = aliases.flatMap((alias) => config.stageRoutes[alias] ?? []);
  const byName = new Map<string, SkillRequirement>();
  for (const requirement of requirements) {
    const existing = byName.get(requirement.name);
    byName.set(requirement.name, {
      name: requirement.name,
      required: Boolean(existing?.required || requirement.required),
    });
  }
  return [...byName.values()];
}

async function resolveSkill(requirement: SkillRequirement, skillDirs: string[]): Promise<ResolvedSkill> {
  for (const dir of skillDirs) {
    const skillPath = path.join(dir, requirement.name, "SKILL.md");
    if (!existsSync(skillPath)) {
      continue;
    }
    const content = await readFile(skillPath, "utf8");
    const frontmatter = parseSkillFrontmatter(content);
    return {
      name: requirement.name,
      description: frontmatter.description ?? "No description provided.",
      required: requirement.required,
      source: "installed",
      scope: "project",
      delivery: "sdk_skill",
      path: skillPath,
      content_sha256: sha256(content),
      included_in_prompt: false,
      reason: "resolved from configured skill source and provided through executor skill capability",
      content,
    };
  }
  return {
    name: requirement.name,
    description: "Missing skill.",
    required: requirement.required,
    source: "missing",
    scope: "project",
    delivery: "missing",
    path: "",
    content_sha256: "",
    included_in_prompt: false,
    reason: "skill was selected by routing config but no SKILL.md was found in configured sources",
  };
}

function stageAliases(stage: string, role: AgentRole): string[] {
  const stageSpecific: Record<string, string[]> = {
    intake_summary: ["intake_summary", "story_intake"],
    product: ["product", "product_definition", "requirement_triage"],
    "dev.technical_plan": ["dev.technical_plan", "dev:technical_plan", "technical_design", "implementation_planning"],
    "dev.implementation": ["dev.implementation", "dev:implementation", "implementation"],
    qa: ["qa", "verification", "backend_verification"],
  };
  const roleFallback: Partial<Record<AgentRole, string[]>> = {
    intake_summary: ["intake_summary", "story_intake"],
    product: ["product", "product_definition", "requirement_triage"],
    dev: ["dev"],
    qa: ["qa", "verification", "backend_verification"],
    verification: ["verification"],
    verifier: ["verifier", "verification"],
    implementation: ["implementation"],
    writer: ["writer", "implementation"],
    route: ["route", "story_intake"],
    technical_design: ["technical_design", "implementation_planning"],
    product_definition: ["product_definition", "requirement_triage"],
    governance_review: ["governance_review"],
    acceptance: ["acceptance"],
    session_handoff: ["session_handoff", "wiki_publish"],
  };
  return [...new Set([stage, stage.replace(/\./g, ":"), ...(stageSpecific[stage] ?? roleFallback[role] ?? [role])])];
}

function projectNameFromPath(value: string): string {
  return path.basename(path.resolve(value));
}

function defaultSkillDirs(): string[] {
  const explicit = process.env.AGT_SKILL_ROOTS
    ?.split(path.delimiter)
    .map((item) => item.trim())
    .filter(Boolean);
  if (explicit?.length) {
    return explicit.map(expandHome);
  }
  const home = process.env.HOME || "";
  if (!home) {
    return [];
  }
  const codexHome = process.env.CODEX_HOME || path.join(home, ".codex");
  const agentsHome = process.env.AGENTS_HOME || path.join(home, ".agents");
  return [
    path.join(codexHome, "skills"),
    path.join(agentsHome, "skills"),
  ];
}

function defaultProjectConfigRoot(): string {
  const home = process.env.HOME || "";
  return home ? path.join(home, ".config", "agt", "projects") : "";
}

function expandHome(value: string): string {
  if (value === "~") {
    return process.env.HOME || value;
  }
  if (value.startsWith("~/")) {
    return path.join(process.env.HOME || "", value.slice(2));
  }
  return value;
}

function scalarValue(value: string): string {
  const raw = value.includes(":") ? value.slice(value.indexOf(":") + 1) : value;
  return raw.trim().replace(/^["']|["']$/g, "");
}

function parseSkillFrontmatter(markdown: string): Record<string, string> {
  const lines = markdown.split(/\r?\n/);
  if (lines[0]?.trim() !== "---") {
    return {};
  }
  const endIndex = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
  if (endIndex === -1) {
    return {};
  }
  const metadata: Record<string, string> = {};
  const frontmatterLines = lines.slice(1, endIndex);
  for (let index = 0; index < frontmatterLines.length; index += 1) {
    const line = frontmatterLines[index] ?? "";
    const trimmed = line.trim();
    const separator = trimmed.indexOf(":");
    if (!trimmed || trimmed.startsWith("#") || separator === -1) {
      continue;
    }
    const key = trimmed.slice(0, separator).trim();
    const value = trimmed.slice(separator + 1).trim().replace(/^["']|["']$/g, "");
    if (value === "|" || value === ">") {
      const block: string[] = [];
      for (let cursor = index + 1; cursor < frontmatterLines.length; cursor += 1) {
        const next = frontmatterLines[cursor] ?? "";
        if (/^\S[^:]*:\s*/.test(next)) {
          break;
        }
        if (next.trim()) {
          block.push(next.trim());
        }
        index = cursor;
      }
      if (key && block.length) {
        metadata[key] = block.join(" ");
      }
      continue;
    }
    if (key && value) {
      metadata[key] = value;
    }
  }
  return metadata;
}

function globMatch(pattern: string, value: string): boolean {
  const normalizedPattern = path.resolve(pattern).split(path.sep).join("/");
  const normalizedValue = path.resolve(value).split(path.sep).join("/");
  const escaped = normalizedPattern.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*");
  return new RegExp(`^${escaped}$`).test(normalizedValue);
}

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
