import { access, readFile } from "node:fs/promises";
import path from "node:path";
import { getAgentDir, parseFrontmatter } from "@earendil-works/pi-coding-agent";

export type RoleDefinition = {
  name: string;
  description: string;
  model?: string;
  tools?: string[];
  skills?: string[];
  requiredSkills?: string[];
  systemPrompt: string;
  filePath: string;
};

export async function loadRoleDefinition(options: {
  role: string;
  cwd: string;
  agentDir?: string;
}): Promise<RoleDefinition> {
  const agentDir = options.agentDir ?? getAgentDir();
  const candidates = [
    path.join(options.cwd, ".pi", "agents", `${options.role}.md`),
    path.join(agentDir, "agents", `${options.role}.md`),
  ];
  for (const filePath of candidates) {
    try {
      await access(filePath);
      const content = await readFile(filePath, "utf8");
      const parsed = parseFrontmatter<Record<string, string>>(content);
      const name = parsed.frontmatter.name?.trim() || options.role;
      const description = parsed.frontmatter.description?.trim() || "";
      const tools = parseCommaList(parsed.frontmatter.tools);
      return {
        name,
        description,
        model: parsed.frontmatter.model?.trim() || undefined,
        tools,
        skills: parseCommaList(parsed.frontmatter.skills),
        requiredSkills: parseCommaList(parsed.frontmatter.required_skills ?? parsed.frontmatter["required-skills"]),
        systemPrompt: parsed.body.trim(),
        filePath,
      };
    } catch {
      // Try the next project/user scope candidate.
    }
  }
  throw new Error(`Pi agent definition not found: ${options.role}`);
}

function parseCommaList(value: string | undefined): string[] | undefined {
  const values = value?.split(",").map((item) => item.trim()).filter(Boolean);
  return values?.length ? values : undefined;
}
