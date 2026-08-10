import { describe, expect, it, vi } from "vitest";
import { PiAgentTeam } from "../src/team.js";
import type { HumanDecision, RoleExecutionInput, RoleExecutionResult, RoleExecutor } from "../src/types.js";

const result = (output: string): RoleExecutionResult => ({ status: "completed", output, events: [], filesChanged: [], commandsRun: [] });
class FakeExecutor implements RoleExecutor {
  inputs: RoleExecutionInput[] = [];
  async run(input: RoleExecutionInput): Promise<RoleExecutionResult> { this.inputs.push(input); return result(`${input.stage} output`); }
}
function gate(decisions: HumanDecision[]) { return { confirm: vi.fn(async () => decisions.shift() ?? "approve") }; }

describe("PiAgentTeam", () => {
  it("requires alignment approval before implementation and runs review then verification", async () => {
    const executor = new FakeExecutor();
    const humanGate = gate(["approve", "approve", "approve"]);
    const team = new PiAgentTeam({ repoRoot: "/repo", workspaceDir: "/tmp/pi-team-test", executor, gate: humanGate });
    const run = await team.run("Add avatar upload");

    expect(run.status).toBe("completed");
    expect(run.completedStages).toEqual(["requirement_alignment", "technical_plan", "implementation", "review", "verification"]);
    expect(executor.inputs.map((input) => input.stage)).toEqual(["requirement_alignment", "technical_plan", "implementation", "review", "verification"]);
    expect(executor.inputs[2]?.prompt).toContain("technical_plan output");
    expect(humanGate.confirm).toHaveBeenCalledTimes(3);
  });

  it("persists a waiting run and resumes without rerunning the completed stage", async () => {
    const executor = new FakeExecutor();
    const humanGate = gate(["pause", "approve", "approve", "approve"]);
    const team = new PiAgentTeam({ repoRoot: "/repo", workspaceDir: "/tmp/pi-team-resume-test", executor, gate: humanGate, runId: "resume-test" });

    const paused = await team.run("Add a health endpoint");
    expect(paused.status).toBe("waiting_for_human");
    expect(paused.waitingStage).toBe("requirement_alignment");
    expect(executor.inputs.map((input) => input.stage)).toEqual(["requirement_alignment"]);

    const resumed = await team.resume("resume-test");
    expect(resumed.status).toBe("completed");
    expect(executor.inputs.map((input) => input.stage)).toEqual([
      "requirement_alignment", "technical_plan", "implementation", "review", "verification",
    ]);
  });

  it("reruns the alignment stage after an edit decision", async () => {
    const executor = new FakeExecutor();
    const humanGate = gate(["edit", "approve", "approve", "approve"]);
    const team = new PiAgentTeam({ repoRoot: "/repo", workspaceDir: "/tmp/pi-team-edit-test", executor, gate: humanGate });
    const run = await team.run("Change button copy");

    expect(run.status).toBe("completed");
    expect(executor.inputs.map((input) => input.stage)).toEqual([
      "requirement_alignment", "requirement_alignment", "technical_plan", "implementation", "review", "verification",
    ]);
  });
});
