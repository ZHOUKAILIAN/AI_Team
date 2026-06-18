import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  type AgentRunner,
  type AgentTask,
  type AgentTaskResult,
  readSessionStatus,
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

class ThrowingRunner implements AgentRunner {
  readonly name = "local_fallback" as const;

  async runTask(task: AgentTask): Promise<AgentTaskResult> {
    if (task.role === "verification") {
      throw new Error("Executor timed out after 900 seconds.");
    }
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
      filesChanged: [],
      commandsRun: ["echo test"],
    };
  }
}

class CountingRunner extends FakeRunner {
  calls = 0;

  override async runTask(task: AgentTask): Promise<AgentTaskResult> {
    this.calls += 1;
    return super.runTask(task);
  }
}

class HeartbeatRunner implements AgentRunner {
  readonly name = "local_fallback" as const;

  async runTask(task: AgentTask): Promise<AgentTaskResult> {
    const store = new RuntimeStore(path.join(task.repoRoot, ".agt-test"));
    const agentRun = await store.createAgentRun({
      sessionId: task.sessionId,
      role: task.role,
      runner: this.name,
      input: task.prompt,
    });
    const heartbeat = await store.heartbeatAgentRun(agentRun, { test: true });
    const completed = await store.completeAgentRun(heartbeat, {
      status: "completed",
      output: `${task.role} ok`,
    });
    return {
      agentRun: completed,
      output: `${task.role} ok`,
      filesChanged: [],
      commandsRun: ["echo heartbeat"],
    };
  }
}

describe("profiles", () => {
  it("keeps the lightweight quick profile available", () => {
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
    const workflow = await store.loadExecutionWorkflow(result.session_id);
    const delivery = await store.loadDeliveryWorkflow(result.session_id);
    expect(workflow.steps).toHaveLength(5);
    expect(workflow.files_changed).toContain("example.txt");
    expect(workflow.steps.every((step) => step.prompt_trace_id)).toBe(true);
    expect(workflow.steps.every((step) => step.artifact_path)).toBe(true);
    expect(delivery.status).toBe("done");
    expect(delivery.phases.map((phase) => [phase.phase, phase.status])).toEqual([
      ["requirement", "passed"],
      ["development", "passed"],
      ["verification", "passed"],
      ["handoff", "passed"],
    ]);

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

  it("records agent run heartbeat state for CLI polling", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-runtime-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const result = await runWorkflow({
      repoRoot,
      stateRoot,
      request: "observe heartbeat",
      profile: "quick",
      runner: new HeartbeatRunner(),
    });

    const store = new RuntimeStore(stateRoot);
    const runs = await store.listAgentRuns(result.session_id);
    expect(runs.every((run) => run.heartbeat_count >= 1)).toBe(true);
    expect(runs.every((run) => run.last_heartbeat_at)).toBe(true);

    const status = await readSessionStatus(store, result.session_id);
    expect(status.runtime_status).toBe("done");
    expect(status.latest_run?.heartbeat_count).toBeGreaterThanOrEqual(1);
    const events = await store.readEvents(result.session_id);
    expect(events.some((event) => event.kind === "agent_run_heartbeat")).toBe(true);
  });

  it("marks a running agent run as stalled when heartbeat is stale", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-runtime-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const store = new RuntimeStore(stateRoot);
    const session = await store.createSession({
      request: "stalled status",
      profile: "quick",
      repoRoot,
    });
    await store.updateExecutionWorkflow(session.session_id, (workflow) => ({
      ...workflow,
      current_stage: "planner",
      status: "in_progress",
      updated_at: "2026-06-16T00:00:00.000Z",
    }));
    const run = await store.createAgentRun({
      sessionId: session.session_id,
      role: "planner",
      runner: "local_fallback",
      input: "prompt",
    });
    await store.writeAgentRun({
      ...run,
      started_at: "2026-06-16T00:00:00.000Z",
      last_heartbeat_at: "2026-06-16T00:00:01.000Z",
      heartbeat_count: 1,
    });

    const status = await readSessionStatus(store, session.session_id, {
      now: new Date("2026-06-16T00:01:00.000Z"),
      stalledAfterMs: 10_000,
    });

    expect(status.runtime_status).toBe("stalled");
    expect(status.active_run?.runtime_status).toBe("stalled");
    expect(status.active_run?.heartbeat_age_ms).toBe(59_000);
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
    const workflow = await store.loadExecutionWorkflow(first.session_id);
    const delivery = await store.loadDeliveryWorkflow(first.session_id);
    expect(workflow.steps.find((step) => step.role === "product_definition")?.status).toBe("completed");
    expect(workflow.steps.find((step) => step.role === "technical_design")?.status).toBe("completed");
    expect(delivery.status).toBe("waiting_human");
    expect(delivery.current_phase).toBe("requirement");
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
    const workflow = await store.loadExecutionWorkflow(first.session_id);
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

  it("blocks verification timeouts without losing prompt trace context", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-runtime-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const result = await runWorkflow({
      repoRoot,
      stateRoot,
      request: "verify timeout behavior",
      profile: "full",
      runner: new ThrowingRunner(),
    });

    expect(result.status).toBe("blocked");
    expect(result.current_stage).toBe("verification");
    expect(result.blocked_reason).toContain("Executor timed out after 900 seconds");

    const store = new RuntimeStore(stateRoot);
    const workflow = await store.loadExecutionWorkflow(result.session_id);
    const delivery = await store.loadDeliveryWorkflow(result.session_id);
    const implementation = workflow.steps.find((step) => step.role === "implementation");
    const verification = workflow.steps.find((step) => step.role === "verification");
    expect(implementation?.status).toBe("completed");
    expect(verification?.status).toBe("blocked");
    expect(verification?.prompt_trace_id).toBeTruthy();
    expect(verification?.artifact_path).toBeTruthy();

    const runs = await store.listAgentRuns(result.session_id);
    const verificationRun = runs.find((run) => run.role === "verification");
    expect(verificationRun?.status).toBe("blocked");
    expect(verificationRun?.metadata.executor_status).toBe("timeout");
    expect(verificationRun?.metadata.result_parse_status).toBe("not_produced");
    expect(delivery.status).toBe("blocked");
    expect(delivery.current_phase).toBe("verification");
    expect(delivery.blockers[0]?.source_role).toBe("verification");
  });

  it("records configured skill routing in prompt trace metadata and prompt content", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-runtime-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const configRoot = await mkdtemp(path.join(tmpdir(), "agt-routing-"));
    const skillRoot = path.join(configRoot, "skills");
    const skillDir = path.join(skillRoot, "backend-service-verification");
    await mkdir(skillDir, { recursive: true });
    await writeFile(
      path.join(skillDir, "SKILL.md"),
      [
        "---",
        "name: backend-service-verification",
        "---",
        "",
        "# Backend Service Verification",
        "",
        "Run concrete service checks before claiming verification.",
      ].join("\n"),
    );
    const configPath = path.join(configRoot, "skill-routing.yaml");
    await writeFile(
      configPath,
      [
        "schema_version: 0.1",
        "project:",
        "  name: crewpals-mp",
        "  repo_family:",
        `    - ${repoRoot}`,
        "skill_sources:",
        "  installed_skills:",
        `    - ${skillRoot}`,
        "stage_routes:",
        "  verification:",
        "    required_skills:",
        "      - backend-service-verification",
      ].join("\n"),
    );
    const previous = process.env.AGT_SKILL_ROUTING_CONFIG;
    const previousSkillRoots = process.env.AGT_SKILL_ROOTS;
    process.env.AGT_SKILL_ROUTING_CONFIG = configPath;
    process.env.AGT_SKILL_ROOTS = skillRoot;
    try {
      const result = await runWorkflow({
        repoRoot,
        projectRoot: path.join(repoRoot, "crewpals-mp"),
        stateRoot,
        request: "verify with routed skill",
        profile: "full",
        humanGates: false,
        runner: new FakeRunner(),
      });

      expect(result.status).toBe("done");
      const store = new RuntimeStore(stateRoot);
      const workflow = await store.loadExecutionWorkflow(result.session_id);
      const verification = workflow.steps.find((step) => step.role === "verification");
      expect(verification?.prompt_trace_id).toBeTruthy();
      const prompt = await store.readPromptContent(verification!.prompt_trace_id);
      expect(prompt.content).toContain("# Routed Skills");
      expect(prompt.content).toContain("backend-service-verification");
      expect(prompt.prompt.metadata.skill_routing).toMatchObject({
        matched: true,
        selected_skill_count: 1,
        included_skill_count: 1,
        missing_skills: [],
      });
    } finally {
      if (previous === undefined) {
        delete process.env.AGT_SKILL_ROUTING_CONFIG;
      } else {
        process.env.AGT_SKILL_ROUTING_CONFIG = previous;
      }
      if (previousSkillRoots === undefined) {
        delete process.env.AGT_SKILL_ROOTS;
      } else {
        process.env.AGT_SKILL_ROOTS = previousSkillRoots;
      }
    }
  });

  it("blocks when routing selects missing required skills", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-runtime-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const configRoot = await mkdtemp(path.join(tmpdir(), "agt-routing-"));
    const emptySkillRoot = path.join(configRoot, "empty-skills");
    await mkdir(emptySkillRoot, { recursive: true });
    const configPath = path.join(configRoot, "skill-routing.yaml");
    await writeFile(
      configPath,
      [
        "schema_version: 0.1",
        "project:",
        "  name: generic-tool-project",
        "  repo_family:",
        `    - ${repoRoot}`,
        "skill_sources:",
        "  installed_skills:",
        `    - ${emptySkillRoot}`,
        "stage_routes:",
        "  verification:",
        "    required_skills:",
        "      - required-verification-skill",
      ].join("\n"),
    );
    const previous = process.env.AGT_SKILL_ROUTING_CONFIG;
    const previousSkillRoots = process.env.AGT_SKILL_ROOTS;
    process.env.AGT_SKILL_ROUTING_CONFIG = configPath;
    process.env.AGT_SKILL_ROOTS = emptySkillRoot;
    const runner = new CountingRunner();
    try {
      const result = await runWorkflow({
        repoRoot,
        projectRoot: repoRoot,
        stateRoot,
        request: "verify with missing routed skill",
        profile: "full",
        humanGates: false,
        runner,
      });

      expect(result.status).toBe("blocked");
      expect(result.current_stage).toBe("verification");
      expect(result.blocked_reason).toContain("Routing config gap");
      expect(runner.calls).toBe(5);

      const store = new RuntimeStore(stateRoot);
      const workflow = await store.loadExecutionWorkflow(result.session_id);
      const verification = workflow.steps.find((step) => step.role === "verification");
      expect(verification?.status).toBe("blocked");
      const runs = await store.listAgentRuns(result.session_id);
      const verificationRun = runs.find((run) => run.role === "verification");
      expect(verificationRun?.metadata.routing_config_gap).toBe(true);
      expect(verificationRun?.metadata.missing_required_skills).toEqual(["required-verification-skill"]);
    } finally {
      if (previous === undefined) {
        delete process.env.AGT_SKILL_ROUTING_CONFIG;
      } else {
        process.env.AGT_SKILL_ROUTING_CONFIG = previous;
      }
      if (previousSkillRoots === undefined) {
        delete process.env.AGT_SKILL_ROOTS;
      } else {
        process.env.AGT_SKILL_ROOTS = previousSkillRoots;
      }
    }
  });
});
