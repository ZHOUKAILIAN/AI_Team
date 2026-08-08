import type { AgentSessionEvent } from "@earendil-works/pi-coding-agent";

export type TerminalEventRenderer = (event: AgentSessionEvent) => void;

export function createTerminalEventRenderer(output: NodeJS.WritableStream = process.stdout): TerminalEventRenderer {
  return (event) => {
    const record = asRecord(event);
    switch (record.type) {
      case "tool_execution_start":
        output.write(`\n[tool] ${String(record.toolName ?? "unknown")}\n`);
        break;
      case "tool_execution_end":
        output.write(`[tool ${record.isError ? "error" : "done"}]\n`);
        break;
      case "message_update": {
        const assistantEvent = asRecord(record.assistantMessageEvent);
        if (assistantEvent.type === "text_delta" && typeof assistantEvent.delta === "string") {
          output.write(assistantEvent.delta);
        }
        break;
      }
      case "agent_end":
        output.write("\n[agent] completed\n");
        break;
      default:
        break;
    }
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? value as Record<string, unknown> : {};
}
