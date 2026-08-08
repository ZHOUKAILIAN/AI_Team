#!/usr/bin/env node
import path from "node:path";
import process from "node:process";
import { PiAgentTeam, PiSdkExecutor, TerminalHumanGate, createTerminalEventRenderer } from "./index.js";

async function main(): Promise<void> {
  const [command, ...args] = process.argv.slice(2);
  const repoRoot = process.cwd();
  const workspaceDir = path.join(repoRoot, ".pi-team");
  const gate = new TerminalHumanGate();
  const executor = new PiSdkExecutor({ onEvent: createTerminalEventRenderer() });
  const team = new PiAgentTeam({ repoRoot, workspaceDir, executor, gate });

  try {
    if (command === "run") {
      const task = args.join(" ").trim();
      if (!task) throw new Error('Usage: pi-team run "<task>"');
      const result = await team.run(task);
      printResult(result);
      return;
    }
    if (command === "resume") {
      const runId = args[0];
      if (!runId) throw new Error("Usage: pi-team resume <run-id>");
      const result = await team.resume(runId);
      printResult(result);
      return;
    }
    throw new Error('Usage: pi-team <run "<task>" | resume <run-id> >');
  } finally {
    gate.close();
  }
}

function printResult(result: { runId: string; status: string; completedStages: string[]; waitingStage?: string }): void {
  process.stdout.write(`\n[team] run=${result.runId} status=${result.status}\n`);
  process.stdout.write(`[team] stages=${result.completedStages.join(" -> ") || "none"}\n`);
  if (result.waitingStage) process.stdout.write(`[team] waiting_stage=${result.waitingStage}\n`);
}

main().catch((error: unknown) => {
  process.stderr.write(`[team] ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
