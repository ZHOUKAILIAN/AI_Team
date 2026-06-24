import { createHash, randomBytes } from "node:crypto";

export function slugify(value: string, fallback = "task"): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  return slug || fallback;
}

export function createSessionId(request: string): string {
  const timestamp = new Date().toISOString().replace(/[-:.]/g, "").replace("T", "T").slice(0, 18);
  const digest = createHash("sha1").update(request).digest("hex").slice(0, 8);
  return `${timestamp}-${digest}`;
}

export function createRunId(role: string): string {
  return `${role}-${randomBytes(5).toString("hex")}`;
}

export function createPromptTraceId(role: string, prompt: string): string {
  const timestamp = new Date().toISOString().replace(/[-:.]/g, "").replace("T", "T").slice(0, 18);
  const digest = createHash("sha1").update(prompt).digest("hex").slice(0, 8);
  return `prompt-${timestamp}-${role}-${digest}`;
}

export function createArtifactId(role: string, name: string): string {
  const timestamp = new Date().toISOString().replace(/[-:.]/g, "").replace("T", "T").slice(0, 18);
  return `artifact-${timestamp}-${role}-${slugify(name, "output")}`;
}

export function sha256Hex(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
