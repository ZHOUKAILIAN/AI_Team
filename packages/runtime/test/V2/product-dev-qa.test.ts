import { access, mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  type AgentRunner,
  type AgentTask,
  type AgentTaskResult,
  recordProductDevQaHumanDecision,
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

    const artifacts = await store.readArtifacts(result.session_id);
    expect(artifacts.map((item) => item.name)).toEqual([
      "request-summary.md",
      "product-contract.md",
      "product-handoff.md",
    ]);

    await access(path.join(stateRoot, "sessions", result.session_id, "stages", "intake_summary", "attempt-001", "context-packet.json"));
    await access(path.join(stateRoot, "sessions", result.session_id, "stages", "product", "attempt-001", "prompt.md"));
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
});
