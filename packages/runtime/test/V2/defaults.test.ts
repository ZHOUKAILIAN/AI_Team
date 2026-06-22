import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { execa } from "execa";
import { describe, expect, it } from "vitest";

import { createTaskWorktree, initRuntime } from "../../src/V2/index.js";

describe("V2 runtime defaults", () => {
  it("uses .agt2 for the source runtime and task worktrees", async () => {
    const repoRoot = await mkdtemp(path.join(tmpdir(), "agt2-defaults-"));
    await execa("git", ["init"], { cwd: repoRoot });
    await writeFile(path.join(repoRoot, "README.md"), "v2 defaults\n");
    await execa("git", ["add", "README.md"], { cwd: repoRoot });
    await execa("git", [
      "-c",
      "user.name=AGT Test",
      "-c",
      "user.email=agt-test@example.com",
      "commit",
      "-m",
      "initial",
    ], { cwd: repoRoot });

    const initialized = await initRuntime({ repoRoot });
    expect(initialized.stateRoot).toBe(path.join(repoRoot, ".agt2"));
    expect(initialized.configPath).toBe(path.join(repoRoot, ".agt2", "config.json"));
    const config = JSON.parse(await readFile(initialized.configPath, "utf8")) as { state_root: string };
    expect(config.state_root).toBe(".agt2");

    const worktree = await createTaskWorktree({
      projectRoot: repoRoot,
      stateRoot: initialized.stateRoot,
      request: "ship v2 defaults",
    });
    expect(worktree.stateRoot).toBe(path.join(worktree.repoRoot, ".agt2"));
    expect(worktree.worktree.policy_snapshot_path).toBe(path.join(worktree.repoRoot, ".agt2", "config.json"));
  });
});
