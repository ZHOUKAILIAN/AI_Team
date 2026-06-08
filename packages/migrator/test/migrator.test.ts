import { mkdir, writeFile } from "node:fs/promises";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { RuntimeStore } from "@agent-team-runtime/runtime";
import { migrateLegacySessions } from "../src/index.js";

describe("migrator", () => {
  // 验证迁移器 dry-run 不写入，apply 会生成新 schema 的 session。
  // Verifies that migrator dry-run is read-only and apply creates a new-schema session.
  it("dry-runs and applies legacy session migration", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agt-migrate-"));
    const legacySession = path.join(root, ".agt", "_runtime", "sessions", "legacy-1");
    await mkdir(legacySession, { recursive: true });
    await writeFile(
      path.join(legacySession, "session.json"),
      JSON.stringify({
        session_id: "legacy-1",
        request: "old request",
        created_at: "2026-06-01T00:00:00.000Z",
        updated_at: "2026-06-01T00:01:00.000Z",
        repo_root: root,
      }),
    );
    await writeFile(
      path.join(legacySession, "workflow_summary.json"),
      JSON.stringify({
        session_id: "legacy-1",
        current_state: "Done",
        current_stage: "SessionHandoff",
        stage_statuses: { Implementation: "completed" },
      }),
    );
    await writeFile(
      path.join(legacySession, "events.jsonl"),
      `${JSON.stringify({ at: "2026-06-01T00:00:00.000Z", kind: "legacy", stage: "Implementation" })}\n`,
    );

    const target = path.join(root, ".agt-js");
    const dryRun = await migrateLegacySessions({ sourceRoot: root, targetStateRoot: target, apply: false });
    expect(dryRun.scanned).toBe(1);
    expect(dryRun.dry_run).toBe(true);

    const applied = await migrateLegacySessions({ sourceRoot: root, targetStateRoot: target, apply: true });
    expect(applied.migrated).toBe(1);
    const store = new RuntimeStore(target);
    const session = await store.loadSession("migrated-legacy-1");
    expect(session.source).toBe("migrated");
    const workflow = await store.loadWorkflow("migrated-legacy-1");
    expect(workflow.status).toBe("done");
    const events = await store.readEvents("migrated-legacy-1");
    expect(events.some((event) => event.kind === "legacy")).toBe(true);
    expect(events.filter((event) => event.kind === "artifact_written")).toHaveLength(3);
    const artifacts = await store.readArtifacts("migrated-legacy-1");
    expect(artifacts.map((artifact) => artifact.name)).toEqual(
      expect.arrayContaining(["legacy-session.json", "legacy-workflow_summary.json", "legacy-source.txt"]),
    );
    const legacySessionArtifact = await store.readArtifactContent("migrated-legacy-1", "legacy-session.json");
    expect(legacySessionArtifact.content).toContain("old request");
  });
});
