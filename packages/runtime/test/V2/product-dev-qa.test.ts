import { access, mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  type AgentRunner,
  type AgentTask,
  type AgentTaskResult,
  emptyTokenUsage,
  recordProductDevQaHumanDecision,
  retryProductDevQaBlockedStage,
  runProductDevQaWorkflow,
  RuntimeStore,
} from "../../src/V2/index.js";

class ProductDevQaRunner implements AgentRunner {
  readonly name = "local_fallback" as const;

  constructor(
    private readonly options: {
      qaShouldFailOnce?: boolean;
    } = {},
  ) {}

  private qaCalls = 0;

  async runTask(task: AgentTask): Promise<AgentTaskResult> {
    const store = new RuntimeStore(path.join(task.repoRoot, ".agt-test"));
    const agentRun = await store.createAgentRun({
      sessionId: task.sessionId,
      role: task.role,
      runner: this.name,
      input: task.prompt,
    });
    const stageLine = task.prompt.split("\n").find((line) => line.startsWith("Stage: ")) ?? "";
    let output = `${task.role} ok`;
    if (stageLine === "Stage: intake_summary") {
      output = "Generated request summary.";
    } else if (stageLine === "Stage: product") {
      output = "Defined scope, acceptance criteria, and QA focus.";
    } else if (stageLine === "Stage: dev:technical_plan") {
      output = "Planned implementation, tests, and assumptions.";
    } else if (stageLine === "Stage: dev:implementation") {
      output = "Implemented local code changes and recorded self-tests.";
    } else if (stageLine === "Stage: qa") {
      this.qaCalls += 1;
      output = this.options.qaShouldFailOnce && this.qaCalls === 1
        ? "QA found edge cases.\nVERDICT: failed"
        : "QA verified local delivery.\nVERDICT: passed";
    }
    const completed = await store.completeAgentRun(agentRun, {
      status: "completed",
      output,
    });
    return {
      agentRun: completed,
      output,
      filesChanged: task.writeAllowed ? ["src/example.ts"] : [],
      commandsRun: task.writeAllowed ? ["npm test -- example"] : ["echo verify"],
      tokenUsage: emptyTokenUsage(),
    };
  }
}

class ThrowingRunner implements AgentRunner {
  readonly name = "local_fallback" as const;

  async runTask(): Promise<AgentTaskResult> {
    throw new Error("synthetic executor failure");
  }
}

class RetryableFailureRunner implements AgentRunner {
  readonly name = "local_fallback" as const;

  constructor(private failuresRemaining: number) {}

  async runTask(task: AgentTask): Promise<AgentTaskResult> {
    const store = new RuntimeStore(path.join(task.repoRoot, ".agt-test"));
    const agentRun = await store.createAgentRun({
      sessionId: task.sessionId,
      role: task.role,
      runner: this.name,
      input: task.prompt,
    });
    if (this.failuresRemaining > 0) {
      this.failuresRemaining -= 1;
      const message = "stream disconnected before completion: error sending request for url (https://ai.smartingredients.my/v1/responses)";
      const failed = await store.completeAgentRun(agentRun, {
        status: "failed",
        output: message,
        error: message,
        metadata: {
          failure_kind: "executor_transient",
          failure_message: message,
          retryable: true,
        },
      });
      return {
        agentRun: failed,
        output: message,
        filesChanged: [],
        commandsRun: [],
        tokenUsage: emptyTokenUsage(),
      };
    }
    const completed = await store.completeAgentRun(agentRun, {
      status: "completed",
      output: task.role === "qa" ? "QA verified local delivery.\nVERDICT: passed" : `${task.role} recovered.`,
    });
    return {
      agentRun: completed,
      output: completed.output,
      filesChanged: task.writeAllowed ? ["src/example.ts"] : [],
      commandsRun: [],
      tokenUsage: emptyTokenUsage(),
    };
  }
}

class NonRetryableFailureRunner implements AgentRunner {
  readonly name = "local_fallback" as const;

  async runTask(task: AgentTask): Promise<AgentTaskResult> {
    const store = new RuntimeStore(path.join(task.repoRoot, ".agt-test"));
    const agentRun = await store.createAgentRun({
      sessionId: task.sessionId,
      role: task.role,
      runner: this.name,
      input: task.prompt,
    });
    const message = "Routing config gap: missing required skills.";
    const failed = await store.completeAgentRun(agentRun, {
      status: "failed",
      output: message,
      error: message,
      metadata: {
        failure_kind: "executor_failed",
        failure_message: message,
        retryable: false,
      },
    });
    return {
      agentRun: failed,
      output: message,
      filesChanged: [],
      commandsRun: [],
      tokenUsage: emptyTokenUsage(),
    };
  }
}

describe("product-dev-qa workflow", () => {
  it("stops at product_check and writes audit files", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-p0-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const result = await runProductDevQaWorkflow({
      repoRoot,
      stateRoot,
      request: "implement product dev qa runtime",
      runner: new ProductDevQaRunner(),
    });

    expect(result.status).toBe("waiting_human");
    expect(result.current_stage).toBe("product");

    const store = new RuntimeStore(stateRoot);
    const workflow = await store.loadProductDevQaWorkflow(result.session_id);
    expect(workflow.status).toBe("waiting_human");
    expect(workflow.current_role).toBe("product");
    expect(workflow.waiting_on).toBe("product_check");
    const sessionDir = path.join(stateRoot, "sessions", result.session_id);
    const sessionJson = JSON.parse(await readFile(path.join(sessionDir, "session.json"), "utf8")) as Record<string, unknown>;
    const executionJson = JSON.parse(await readFile(path.join(sessionDir, "execution-workflow.json"), "utf8")) as Record<string, unknown>;
    const indexJson = JSON.parse(await readFile(path.join(stateRoot, "session-index.json"), "utf8")) as {
      sessions: Array<Record<string, unknown>>;
    };
    expect(sessionJson).not.toHaveProperty("profile");
    expect(executionJson).not.toHaveProperty("profile");
    expect(indexJson.sessions[0]).not.toHaveProperty("profile");

    const eventKinds = (await store.readEvents(result.session_id)).map((event) => event.kind);
    expect(eventKinds).toEqual(expect.arrayContaining([
      "stage_started",
      "executor_started",
      "executor_completed",
      "stage_completed",
    ]));
    expect(eventKinds).not.toContain("product_dev_qa_stage_started");
    expect(eventKinds).not.toContain("product_dev_qa_stage_completed");

    const metrics = await store.readMetrics(result.session_id);
    expect(metrics.map((metric) => metric.stage)).toEqual(["intake_summary", "product"]);
    expect(metrics.every((metric) => metric.kind === "stage.completed")).toBe(true);
    expect(metrics[0]?.stage_started_at).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(metrics[0]).toMatchObject({
      workflow_id: "product-dev-qa",
      attempt: 1,
      verdict: "passed",
      runner: "local_fallback",
      token_usage: {
        total_tokens: 0,
      },
    });
    expect(JSON.stringify(metrics)).not.toContain("profile");

    const artifacts = await store.readArtifacts(result.session_id);
    expect(artifacts.map((item) => item.name)).toEqual([
      "request-summary.md",
      "product-contract.md",
      "product-handoff.md",
    ]);

    const intakeAttemptDir = path.join(stateRoot, "sessions", result.session_id, "stages", "intake_summary", "attempt-001");
    const productAttemptDir = path.join(stateRoot, "sessions", result.session_id, "stages", "product", "attempt-001");
    const contextPacket = JSON.parse(await readFile(path.join(intakeAttemptDir, "context-packet.json"), "utf8")) as {
      skill_routing: Record<string, unknown>;
    };
    expect(contextPacket.skill_routing).toMatchObject({
      workflow_id: "product-dev-qa",
      stage: "intake_summary",
      role: "intake_summary",
      matched: false,
      skills: [],
      missing_skills: [],
      missing_required_skills: [],
    });
    expect(contextPacket.skill_routing).not.toHaveProperty("selected_skills");
    expect(contextPacket.skill_routing).not.toHaveProperty("reasons");
    await access(path.join(intakeAttemptDir, "skill-routing.json"));
    const prompt = await readFile(path.join(productAttemptDir, "prompt.md"), "utf8");
    expect(prompt).toContain("# AGT Stage");
    expect(prompt).toContain("## Output Contract");
    expect(prompt).not.toContain("Included in prompt:");
    await access(path.join(stateRoot, "sessions", result.session_id, "stages", "product", "attempt-001", "verdict.json"));
  });

  it("continues through dev plan and completes implementation plus qa", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-p0-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const runner = new ProductDevQaRunner();
    const first = await runProductDevQaWorkflow({
      repoRoot,
      stateRoot,
      request: "ship local code change with qa report",
      runner,
    });

    const second = await recordProductDevQaHumanDecision({
      stateRoot,
      sessionId: first.session_id,
      decision: "go",
      runner,
    });
    expect(second.status).toBe("waiting_human");
    expect(second.current_stage).toBe("dev:technical_plan");

    const done = await recordProductDevQaHumanDecision({
      stateRoot,
      sessionId: first.session_id,
      decision: "go",
      runner,
    });
    expect(done.status).toBe("done");
    expect(done.current_stage).toBe("done");

    const store = new RuntimeStore(stateRoot);
    const workflow = await store.loadProductDevQaWorkflow(first.session_id);
    expect(workflow.status).toBe("done");
    expect(workflow.last_stage_verdict).toBe("passed");
    expect(workflow.stage_attempt_counts).toMatchObject({
      intake_summary: 1,
      product: 1,
      "dev.technical_plan": 1,
      "dev.implementation": 1,
      qa: 1,
    });

    const artifacts = await store.readArtifacts(first.session_id);
    expect(artifacts.map((item) => item.name)).toEqual([
      "request-summary.md",
      "product-contract.md",
      "product-handoff.md",
      "technical-plan.md",
      "implementation-report.md",
      "self-test-report.md",
      "implementation-ambiguities.json",
      "qa-handoff.md",
      "qa-report.md",
      "verification-evidence.json",
    ]);

    const implementationAmbiguities = await store.readArtifactContent(first.session_id, "implementation-ambiguities.json");
    expect(implementationAmbiguities.content).toContain("\"schema_version\": 1");
    const verificationEvidence = await store.readArtifactContent(first.session_id, "verification-evidence.json");
    expect(verificationEvidence.content).toContain("\"stage\": \"qa\"");
  });

  it("loops qa failure back to dev implementation with a second audited attempt", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-p0-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const runner = new ProductDevQaRunner({ qaShouldFailOnce: true });
    const first = await runProductDevQaWorkflow({
      repoRoot,
      stateRoot,
      request: "exercise qa failed loop",
      runner,
    });

    await recordProductDevQaHumanDecision({
      stateRoot,
      sessionId: first.session_id,
      decision: "go",
      runner,
    });
    const done = await recordProductDevQaHumanDecision({
      stateRoot,
      sessionId: first.session_id,
      decision: "go",
      runner,
    });

    expect(done.status).toBe("done");
    const store = new RuntimeStore(stateRoot);
    const workflow = await store.loadProductDevQaWorkflow(first.session_id);
    expect(workflow.stage_attempt_counts["dev.implementation"]).toBe(2);
    expect(workflow.stage_attempt_counts.qa).toBe(2);

    await access(path.join(stateRoot, "sessions", first.session_id, "stages", "dev", "implementation", "attempt-002", "post-state.json"));
    await access(path.join(stateRoot, "sessions", first.session_id, "stages", "qa", "attempt-002", "verdict.json"));
  });

  it("blocks and audits executor errors instead of leaking them out of the workflow", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-p0-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const result = await runProductDevQaWorkflow({
      repoRoot,
      stateRoot,
      request: "exercise executor failure",
      runner: new ThrowingRunner(),
    });

    expect(result.status).toBe("blocked");
    expect(result.current_stage).toBe("intake_summary");
    expect(result.blocked_reason).toContain("synthetic executor failure");

    const store = new RuntimeStore(stateRoot);
    const workflow = await store.loadProductDevQaWorkflow(result.session_id);
    expect(workflow.status).toBe("blocked");
    expect(workflow.last_stage_verdict).toBe("blocked");
    expect(workflow.blocked_reason).toContain("synthetic executor failure");

    const events = await store.readEvents(result.session_id);
    expect(events.map((event) => event.kind)).toEqual(expect.arrayContaining([
      "stage_error",
      "executor_completed",
      "stage_completed",
    ]));
    expect(events.find((event) => event.kind === "stage_error")?.details).toMatchObject({
      phase: "executor",
      stage: "intake_summary",
    });

    const sessionDir = path.join(stateRoot, "sessions", result.session_id);
    await access(path.join(sessionDir, "stages", "intake_summary", "attempt-001", "verdict.json"));
    const executionJson = JSON.parse(await readFile(path.join(sessionDir, "execution-workflow.json"), "utf8")) as {
      status: string;
      steps: Array<{ status: string; agent_run_id?: string }>;
    };
    expect(executionJson.status).toBe("blocked");
    expect(executionJson.steps[0]?.status).toBe("blocked");
    expect(executionJson.steps[0]?.agent_run_id).toBeTruthy();
  });

  it("automatically retries retryable executor failures and preserves attempt artifacts", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-p0-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const result = await runProductDevQaWorkflow({
      repoRoot,
      stateRoot,
      request: "exercise retryable executor failure",
      runner: new RetryableFailureRunner(2),
    });

    expect(result.status).toBe("waiting_human");
    expect(result.current_stage).toBe("product");

    const store = new RuntimeStore(stateRoot);
    const workflow = await store.loadProductDevQaWorkflow(result.session_id);
    expect(workflow.stage_attempt_counts.intake_summary).toBe(3);
    expect(workflow.stage_attempt_counts.product).toBe(1);

    const events = await store.readEvents(result.session_id);
    const retryEvents = events.filter((event) => event.kind === "stage_retry_scheduled");
    expect(retryEvents).toHaveLength(2);
    expect(retryEvents[0]?.details).toMatchObject({
      stage: "intake_summary",
      attempt: 1,
      next_attempt: 2,
      failure_kind: "executor_transient",
    });

    const sessionDir = path.join(stateRoot, "sessions", result.session_id);
    await access(path.join(sessionDir, "stages", "intake_summary", "attempt-001", "retry-scheduled.json"));
    await access(path.join(sessionDir, "stages", "intake_summary", "attempt-002", "retry-scheduled.json"));
    await access(path.join(sessionDir, "stages", "intake_summary", "attempt-003", "verdict.json"));
  });

  it("blocks with a deterministic reason after retryable executor failures exhaust retries", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-p0-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const result = await runProductDevQaWorkflow({
      repoRoot,
      stateRoot,
      request: "exercise retry exhaustion",
      runner: new RetryableFailureRunner(4),
    });

    expect(result.status).toBe("blocked");
    expect(result.current_stage).toBe("intake_summary");
    expect(result.blocked_reason).toContain("Executor failed after 4 attempt(s), 3 retries exhausted:");
    expect(result.blocked_reason).toContain("stream disconnected before completion");

    const store = new RuntimeStore(stateRoot);
    const workflow = await store.loadProductDevQaWorkflow(result.session_id);
    expect(workflow.stage_attempt_counts.intake_summary).toBe(4);
    const retryEvents = (await store.readEvents(result.session_id)).filter((event) => event.kind === "stage_retry_scheduled");
    expect(retryEvents).toHaveLength(3);
  });

  it("does not automatically retry non-retryable blocked outcomes", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-p0-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const result = await runProductDevQaWorkflow({
      repoRoot,
      stateRoot,
      request: "exercise non retryable failure",
      runner: new NonRetryableFailureRunner(),
    });

    expect(result.status).toBe("blocked");
    expect(result.blocked_reason).toContain("Routing config gap");

    const store = new RuntimeStore(stateRoot);
    const workflow = await store.loadProductDevQaWorkflow(result.session_id);
    expect(workflow.stage_attempt_counts.intake_summary).toBe(1);
    expect((await store.readEvents(result.session_id)).map((event) => event.kind)).not.toContain("stage_retry_scheduled");
  });

  it("retries a blocked stage after human context without creating a new session", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-p0-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const first = await runProductDevQaWorkflow({
      repoRoot,
      stateRoot,
      request: "exercise human retry",
      runner: new ThrowingRunner(),
    });
    expect(first.status).toBe("blocked");

    const retried = await retryProductDevQaBlockedStage({
      stateRoot,
      sessionId: first.session_id,
      message: "I fixed the executor network issue; retry the same stage.",
      runner: new ProductDevQaRunner(),
    });

    expect(retried.session_id).toBe(first.session_id);
    expect(retried.status).toBe("waiting_human");
    expect(retried.current_stage).toBe("product");

    const store = new RuntimeStore(stateRoot);
    const workflow = await store.loadProductDevQaWorkflow(first.session_id);
    expect(workflow.stage_attempt_counts.intake_summary).toBe(2);
    expect(workflow.retry_context).toBeNull();
    const eventKinds = (await store.readEvents(first.session_id)).map((event) => event.kind);
    expect(eventKinds).toContain("human_retry_requested");

    const retryPrompt = await readFile(
      path.join(stateRoot, "sessions", first.session_id, "stages", "intake_summary", "attempt-002", "prompt.md"),
      "utf8",
    );
    expect(retryPrompt).toContain("## Human Retry Context");
    expect(retryPrompt).toContain("I fixed the executor network issue");

    const artifacts = await store.readArtifacts(first.session_id);
    expect(artifacts.some((artifact) => artifact.name.startsWith("retry-context-intake_summary-"))).toBe(true);
  });

  it("rejects retry while waiting for human approval and points to approve", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-p0-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const first = await runProductDevQaWorkflow({
      repoRoot,
      stateRoot,
      request: "exercise retry restriction",
      runner: new ProductDevQaRunner(),
    });

    await expect(retryProductDevQaBlockedStage({
      stateRoot,
      sessionId: first.session_id,
      runner: new ProductDevQaRunner(),
    })).rejects.toThrow("use agt2 approve");
  });

  it("blocks and writes runtime-error artifacts when runtime persistence fails", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-p0-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const originalWriteArtifact = RuntimeStore.prototype.writeArtifact;
    RuntimeStore.prototype.writeArtifact = async function writeArtifactWithSyntheticFailure(...args) {
      if (args[0]?.name === "request-summary.md") {
        throw new Error("synthetic artifact failure");
      }
      return originalWriteArtifact.apply(this, args);
    };
    try {
      const result = await runProductDevQaWorkflow({
        repoRoot,
        stateRoot,
        request: "exercise runtime persistence failure",
        runner: new ProductDevQaRunner(),
      });

      expect(result.status).toBe("blocked");
      expect(result.current_stage).toBe("intake_summary");
      expect(result.blocked_reason).toContain("synthetic artifact failure");

      const store = new RuntimeStore(stateRoot);
      const events = await store.readEvents(result.session_id);
      expect(events.map((event) => event.kind)).toEqual(expect.arrayContaining([
        "stage_error",
        "stage_blocked_by_error",
      ]));
      expect(events.find((event) => event.kind === "stage_error")?.details).toMatchObject({
        phase: "write_artifacts",
        stage: "intake_summary",
      });

      const sessionDir = path.join(stateRoot, "sessions", result.session_id);
      await access(path.join(sessionDir, "stages", "intake_summary", "attempt-001", "runtime-error.json"));
    } finally {
      RuntimeStore.prototype.writeArtifact = originalWriteArtifact;
    }
  });
});
