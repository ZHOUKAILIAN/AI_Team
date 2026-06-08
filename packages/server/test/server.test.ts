import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  type AgentRunner,
  type AgentTask,
  type AgentTaskResult,
  runWorkflow,
  RuntimeStore,
} from "@agent-team-runtime/runtime";
import { createServer } from "../src/index.js";

// FakeRunner：服务端测试用 runner，用固定输出构造可查询 session。
// FakeRunner: server-test runner that creates queryable sessions with fixed output.
class FakeRunner implements AgentRunner {
  readonly name = "local_fallback" as const;

  // 模拟一个 stage 执行，并返回服务端 API 可读取的 trace 记录。
  // Simulates one stage execution and returns trace records readable by server APIs.
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
      filesChanged: [],
      commandsRun: ["echo test"],
    };
  }
}

describe("server", () => {
  // 验证服务端会暴露 session detail、prompt、artifact 和 console snapshot。
  // Verifies that the server exposes session detail, prompts, artifacts, and console snapshot.
  it("exposes traceable session data", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt-server-"));
    const stateRoot = path.join(repoRoot, ".agt-test");
    const result = await runWorkflow({
      repoRoot,
      stateRoot,
      request: "server snapshot",
      profile: "quick",
      runner: new FakeRunner(),
    });

    const app = await createServer({ stateRoot });
    const detail = await app.inject(`/api/sessions/${result.session_id}`);
    expect(detail.statusCode).toBe(200);
    const detailBody = detail.json();
    expect(detailBody.prompts).toHaveLength(5);
    expect(detailBody.artifacts).toHaveLength(5);
    expect(detailBody.agent_runs).toHaveLength(5);
    expect(detailBody.snapshot.state.steps).toHaveLength(5);

    const prompts = await app.inject(`/api/sessions/${result.session_id}/prompts`);
    const promptList = prompts.json().prompts;
    expect(promptList).toHaveLength(5);
    const promptContent = await app.inject(`/api/sessions/${result.session_id}/prompts/${promptList[0].prompt_id}`);
    expect(promptContent.statusCode).toBe(200);
    expect(promptContent.json().content).toContain("User request: server snapshot");

    const artifacts = await app.inject(`/api/sessions/${result.session_id}/artifacts`);
    const artifactList = artifacts.json().artifacts;
    expect(artifactList).toHaveLength(5);
    const artifactContent = await app.inject(`/api/sessions/${result.session_id}/artifacts/${artifactList[0].name}`);
    expect(artifactContent.statusCode).toBe(200);
    expect(artifactContent.json().content).toContain("ok");

    const config = await app.inject("/api/config");
    expect(config.json().state_root).toBe(path.resolve(stateRoot));

    const snapshot = await app.inject("/api/console/snapshot");
    expect(snapshot.json().stats.sessions).toBe(1);

    await app.close();
  });
});
