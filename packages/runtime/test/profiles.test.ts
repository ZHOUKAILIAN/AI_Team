import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  type AgentRunner,
  type AgentTask,
  type AgentTaskResult,
  recordHumanDecision,
  runWorkflow,
  RuntimeStore,
  stepsForProfile,
} from "../src/index.js";

class FakeRunner implements AgentRunner {
  readonly name = "local_fallback" as const;

  async runTask(task: AgentTask): Promise<AgentTaskResult> {
    const store = new RuntimeStore(path.join(task.repoRoot, ".agt-test"));
    const agentRun = await store.createAgentRun({
      sessionId: task.sessionId,
      role: task.role,
      runner: this.name,
      input: task.prompt,
    });
    const completed = await store.completeAgentRun(agentRun, {
      status: "completed",
      output: `${task.role} ok`,
    });
    return {
      agentRun: completed,
      output: `${task.role} ok`,
      filesChanged: task.writeAllowed ? ["example.txt"] : [],
      commandsRun: ["echo test"],
    };
  }
}

describe("profiles", () => {
  it("uses the lightweight quick profile by default", () => {
    expect(stepsForProfile("quick").map((step) => step.role)).toEqual([
      "planner",
      "repo_scout",
      "writer",
      "verifier",
      "summarizer",
    ]);
  });

  it("runs a traceable quick workflow", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-runtime-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const result = await runWorkflow({
      repoRoot,
      stateRoot,
      request: "make a small change",
      profile: "quick",
      runner: new FakeRunner(),
    });

    expect(result.status).toBe("done");
    const store = new RuntimeStore(stateRoot);
    const workflow = await store.loadWorkflow(result.session_id);
    expect(workflow.steps).toHaveLength(5);
    expect(workflow.files_changed).toContain("example.txt");
    expect(workflow.steps.every((step) => step.prompt_trace_id)).toBe(true);
    expect(workflow.steps.every((step) => step.artifact_path)).toBe(true);

    const prompts = await store.readPromptTraces(result.session_id);
    expect(prompts).toHaveLength(5);
    expect(prompts[0]?.path.endsWith("prompt.md")).toBe(true);
    const promptContent = await store.readPromptContent(prompts[0]!.prompt_id);
    expect(promptContent.content).toContain("User request: make a small change");

    const artifacts = await store.readArtifacts(result.session_id);
    expect(artifacts).toHaveLength(5);
    const artifactContent = await store.readArtifactContent(result.session_id, artifacts[0]!.name);
    expect(artifactContent.content).toContain("ok");

    const agentRuns = await store.listAgentRuns(result.session_id);
    expect(agentRuns).toHaveLength(5);

    const events = await store.readEvents(result.session_id);
    expect(events.some((event) => event.kind === "agent_run_started")).toBe(true);
    expect(events.some((event) => event.kind === "prompt_trace_recorded")).toBe(true);
    expect(events.some((event) => event.kind === "artifact_written")).toBe(true);
  });

  it("stops at full-profile human gates and continues after approval", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-runtime-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const first = await runWorkflow({
      repoRoot,
      stateRoot,
      request: "make a governed change",
      profile: "full",
      humanGates: true,
      runner: new FakeRunner(),
    });

    expect(first.status).toBe("waiting_human");
    expect(first.current_stage).toBe("product_definition");

    const approved = await recordHumanDecision({
      stateRoot,
      sessionId: first.session_id,
      decision: "go",
    });
    expect(approved.status).toBe("in_progress");
    expect(approved.current_stage).toBe("project_runtime");

    const second = await runWorkflow({
      repoRoot,
      stateRoot,
      sessionId: first.session_id,
      humanGates: true,
      runner: new FakeRunner(),
    });
    expect(second.status).toBe("waiting_human");
    expect(second.current_stage).toBe("technical_design");

    const store = new RuntimeStore(stateRoot);
    const workflow = await store.loadWorkflow(first.session_id);
    expect(workflow.steps.find((step) => step.role === "product_definition")?.status).toBe("completed");
    expect(workflow.steps.find((step) => step.role === "technical_design")?.status).toBe("completed");
    expect((await store.readPromptTraces(first.session_id)).length).toBeGreaterThanOrEqual(4);
  });

  it("clears downstream trace pointers when a human requests rework", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-runtime-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const first = await runWorkflow({
      repoRoot,
      stateRoot,
      request: "rework governed change",
      profile: "full",
      humanGates: true,
      runner: new FakeRunner(),
    });
    await recordHumanDecision({ stateRoot, sessionId: first.session_id, decision: "go" });
    await runWorkflow({
      repoRoot,
      stateRoot,
      sessionId: first.session_id,
      humanGates: true,
      runner: new FakeRunner(),
    });

    const rework = await recordHumanDecision({
      stateRoot,
      sessionId: first.session_id,
      decision: "rework",
      targetRole: "product_definition",
    });
    expect(rework.current_stage).toBe("product_definition");

    const store = new RuntimeStore(stateRoot);
    const workflow = await store.loadWorkflow(first.session_id);
    const route = workflow.steps.find((step) => step.role === "route");
    const product = workflow.steps.find((step) => step.role === "product_definition");
    const design = workflow.steps.find((step) => step.role === "technical_design");
    expect(route?.status).toBe("completed");
    expect(product?.status).toBe("pending");
    expect(product?.prompt_trace_id).toBe("");
    expect(product?.agent_run_id).toBeUndefined();
    expect(product?.artifact_path).toBe("");
    expect(design?.status).toBe("pending");
    expect(design?.prompt_trace_id).toBe("");
  });
});
