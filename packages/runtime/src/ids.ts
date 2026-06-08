import { createHash, randomBytes } from "node:crypto";

// 把用户输入转成适合文件名、分支名和 id 片段的 slug。
// Converts user input into a slug suitable for filenames, branch names, and id fragments.
export function slugify(value: string, fallback = "task"): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  return slug || fallback;
}

// 基于时间、需求摘要 hash 和 slug 生成 session id。
// Generates a session id from time, request hash, and slug.
export function createSessionId(request: string): string {
  const timestamp = new Date().toISOString().replace(/[-:.]/g, "").replace("T", "T").slice(0, 18);
  const digest = createHash("sha1").update(request).digest("hex").slice(0, 8);
  return `${timestamp}-${digest}-${slugify(request)}`;
}

// 基于 role 和随机后缀生成 agent run id。
// Generates an agent-run id from role plus a random suffix.
export function createRunId(role: string): string {
  return `${role}-${randomBytes(5).toString("hex")}`;
}

// 基于时间、role 和 prompt hash 生成 prompt trace id。
// Generates a prompt-trace id from time, role, and prompt hash.
export function createPromptTraceId(role: string, prompt: string): string {
  const timestamp = new Date().toISOString().replace(/[-:.]/g, "").replace("T", "T").slice(0, 18);
  const digest = createHash("sha1").update(prompt).digest("hex").slice(0, 8);
  return `prompt-${timestamp}-${role}-${digest}`;
}

// 基于时间、role 和 artifact 名称生成 artifact id。
// Generates an artifact id from time, role, and artifact name.
export function createArtifactId(role: string, name: string): string {
  const timestamp = new Date().toISOString().replace(/[-:.]/g, "").replace("T", "T").slice(0, 18);
  return `artifact-${timestamp}-${role}-${slugify(name, "output")}`;
}

// 计算字符串的 sha256 十六进制摘要。
// Computes the SHA-256 hex digest for a string.
export function sha256Hex(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
