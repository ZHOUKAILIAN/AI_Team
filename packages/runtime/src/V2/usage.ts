import { TokenUsageSchema, type TokenUsage } from "./schema.js";

export function emptyTokenUsage(): TokenUsage {
  return TokenUsageSchema.parse({});
}

export function summarizeOpenAIUsage(rawResponses: unknown[]): TokenUsage {
  const usages = rawResponses
    .map((response) => usageFromRawResponse(response))
    .filter((usage): usage is Record<string, unknown> => Object.keys(usage).length > 0);
  if (usages.length === 0) {
    return emptyTokenUsage();
  }

  const inputTokens = sumUsageNumber(usages, ["input_tokens", "inputTokens", "prompt_tokens", "promptTokens"]);
  const outputTokens = sumUsageNumber(usages, ["output_tokens", "outputTokens", "completion_tokens", "completionTokens"]);
  const explicitTotal = sumUsageNumber(usages, ["total_tokens", "totalTokens"]);
  const reasoningTokens = usages.reduce((total, usage) => total + reasoningTokenCount(usage), 0);

  return TokenUsageSchema.parse({
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    total_tokens: explicitTotal || inputTokens + outputTokens,
    reasoning_tokens: reasoningTokens,
    raw: usages,
  });
}

function usageFromRawResponse(response: unknown): Record<string, unknown> {
  const record = safeRecord(toJson(response));
  return safeRecord(record.usage);
}

function sumUsageNumber(usages: Array<Record<string, unknown>>, keys: string[]): number {
  return usages.reduce((total, usage) => {
    for (const key of keys) {
      const value = numberValue(usage[key]);
      if (value !== undefined) {
        return total + value;
      }
    }
    return total;
  }, 0);
}

function reasoningTokenCount(usage: Record<string, unknown>): number {
  const direct = numberValue(usage.reasoning_tokens ?? usage.reasoningTokens);
  if (direct !== undefined) {
    return direct;
  }
  const outputDetails = safeRecord(usage.output_tokens_details ?? usage.outputTokensDetails);
  const outputReasoning = numberValue(outputDetails.reasoning_tokens ?? outputDetails.reasoningTokens);
  if (outputReasoning !== undefined) {
    return outputReasoning;
  }
  const completionDetails = safeRecord(usage.completion_tokens_details ?? usage.completionTokensDetails);
  return numberValue(completionDetails.reasoning_tokens ?? completionDetails.reasoningTokens) ?? 0;
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? Math.trunc(value) : undefined;
}

function toJson(value: unknown): unknown {
  const maybe = value as { toJSON?: () => unknown };
  return typeof maybe?.toJSON === "function" ? maybe.toJSON() : value;
}

function safeRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
