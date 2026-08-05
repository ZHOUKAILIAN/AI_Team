import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";

export type OpenAIExecutorConfig = {
  apiKey?: string;
  baseUrl?: string;
  model?: string;
  apiKeySource: "env" | "codex" | "unset";
  baseUrlSource: "env" | "codex" | "unset";
  modelSource: "env" | "codex" | "runtime_default" | "unset";
};

export type ResolveOpenAIExecutorConfigOptions = {
  env?: NodeJS.ProcessEnv;
  codexHome?: string;
  runtimeDefaultModel?: string;
};

type CodexConfig = {
  model?: string;
  modelProvider?: string;
  baseUrl?: string;
};

export function resolveOpenAIExecutorConfig(
  options: ResolveOpenAIExecutorConfigOptions = {},
): OpenAIExecutorConfig {
  const env = options.env ?? process.env;
  const codexHome = options.codexHome ?? nonEmpty(env.CODEX_HOME);
  const codex = loadCodexConfig(codexHome);
  const apiKey = nonEmpty(env.OPENAI_API_KEY) ?? codex.apiKey;
  const baseUrl = nonEmpty(env.OPENAI_BASE_URL) ?? codex.baseUrl;
  const model = nonEmpty(env.AGT_OPENAI_MODEL)
    ?? nonEmpty(env.OPENAI_MODEL)
    ?? codex.model
    ?? nonEmpty(options.runtimeDefaultModel);

  return {
    apiKey,
    baseUrl,
    model,
    apiKeySource: nonEmpty(env.OPENAI_API_KEY) ? "env" : codex.apiKey ? "codex" : "unset",
    baseUrlSource: nonEmpty(env.OPENAI_BASE_URL) ? "env" : codex.baseUrl ? "codex" : "unset",
    modelSource: nonEmpty(env.AGT_OPENAI_MODEL) || nonEmpty(env.OPENAI_MODEL)
      ? "env"
      : codex.model
        ? "codex"
        : nonEmpty(options.runtimeDefaultModel)
          ? "runtime_default"
          : "unset",
  };
}

export function hasOpenAIExecutorConfig(config: OpenAIExecutorConfig): boolean {
  return Boolean(config.apiKey || config.baseUrl);
}

export function applyOpenAIExecutorEnv(config: OpenAIExecutorConfig, env: NodeJS.ProcessEnv = process.env): void {
  if (!nonEmpty(env.OPENAI_API_KEY) && config.apiKey) {
    env.OPENAI_API_KEY = config.apiKey;
  }
  if (!nonEmpty(env.OPENAI_BASE_URL) && config.baseUrl) {
    env.OPENAI_BASE_URL = config.baseUrl;
  }
}

export function shouldEnableOpenAITracing(config: OpenAIExecutorConfig): boolean {
  if (!config.baseUrl) {
    return true;
  }
  return isOfficialOpenAIBaseUrl(config.baseUrl);
}

export function shouldEnableOpenAISandboxApplyPatch(config: OpenAIExecutorConfig): boolean {
  if (!config.baseUrl) {
    return true;
  }
  return isOfficialOpenAIBaseUrl(config.baseUrl);
}

function isOfficialOpenAIBaseUrl(value: string): boolean {
  try {
    const host = new URL(value).hostname.toLowerCase();
    return host === "api.openai.com";
  } catch {
    return false;
  }
}

function loadCodexConfig(codexHome = path.join(homedir(), ".codex")): CodexConfig & { apiKey?: string } {
  return {
    ...loadCodexRuntimeConfig(path.join(codexHome, "config.toml")),
    apiKey: loadCodexApiKey(path.join(codexHome, "auth.json")),
  };
}

function loadCodexRuntimeConfig(configPath: string): CodexConfig {
  if (!existsSync(configPath)) {
    return {};
  }
  try {
    const content = readFileSync(configPath, "utf8");
    const model = tomlStringValue(content, "model");
    const modelProvider = tomlStringValue(content, "model_provider");
    const providerSection = modelProvider ? tomlSection(content, `model_providers.${modelProvider}`) : "";
    return {
      model,
      modelProvider,
      baseUrl: providerSection ? tomlStringValue(providerSection, "base_url") : undefined,
    };
  } catch {
    return {};
  }
}

function loadCodexApiKey(authPath: string): string | undefined {
  if (!existsSync(authPath)) {
    return undefined;
  }
  try {
    const parsed = JSON.parse(readFileSync(authPath, "utf8")) as Record<string, unknown>;
    return typeof parsed.OPENAI_API_KEY === "string" && parsed.OPENAI_API_KEY.trim()
      ? parsed.OPENAI_API_KEY.trim()
      : undefined;
  } catch {
    return undefined;
  }
}

function tomlStringValue(content: string, key: string): string | undefined {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = content.match(new RegExp(`^\\s*${escaped}\\s*=\\s*"([^"]*)"\\s*(?:#.*)?$`, "m"));
  return match?.[1]?.trim() || undefined;
}

function tomlSection(content: string, sectionName: string): string {
  const lines = content.split(/\r?\n/);
  const header = `[${sectionName}]`;
  const sectionLines: string[] = [];
  let inSection = false;
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
      if (inSection) {
        break;
      }
      inSection = trimmed === header;
      continue;
    }
    if (inSection) {
      sectionLines.push(line);
    }
  }
  return sectionLines.join("\n");
}

function nonEmpty(value: string | undefined): string | undefined {
  return value?.trim() || undefined;
}
