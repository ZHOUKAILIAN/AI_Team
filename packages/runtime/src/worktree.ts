import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { execa } from "execa";
import { slugify } from "./ids.js";
import { type RuntimeConfig, type WorktreeRecord } from "./schema.js";
import { RuntimeStore } from "./store.js";

export type InitRuntimeOptions = {
  repoRoot: string;
  stateRoot?: string;
  config?: Partial<RuntimeConfig>;
};

export type TaskWorktreeResult = {
  repoRoot: string;
  stateRoot: string;
  worktree: WorktreeRecord;
};

// 初始化 runtime 状态目录、配置文件和本地 worktree 策略快照。
// Initializes the runtime state root, config file, and local worktree policy snapshot.
export async function initRuntime(options: InitRuntimeOptions): Promise<{ stateRoot: string; configPath: string }> {
  const repoRoot = path.resolve(options.repoRoot);
  const stateRoot = path.resolve(options.stateRoot ?? path.join(repoRoot, ".agt"));
  const store = new RuntimeStore(stateRoot);
  await store.ensureLayout();
  const config = await store.ensureConfig(options.config);
  await mkdir(path.join(stateRoot, "local"), { recursive: true });
  await writeFile(path.join(stateRoot, "local", "worktree-policy.json"), `${JSON.stringify(config.task_worktree, null, 2)}\n`);
  return { stateRoot, configPath: store.configPath() };
}

// 为一次任务自动创建隔离 git worktree，并复制当前 runtime 配置。
// Automatically creates an isolated git worktree for one task and copies the runtime config.
export async function createTaskWorktree(options: {
  projectRoot: string;
  stateRoot: string;
  request: string;
  config?: RuntimeConfig;
}): Promise<TaskWorktreeResult> {
  const projectRoot = path.resolve(options.projectRoot);
  const sourceStore = new RuntimeStore(options.stateRoot);
  const config = options.config ?? (await sourceStore.loadConfig());
  const policy = config.task_worktree;
  const base = await resolveBaseRef(projectRoot, policy.base_ref_candidates);
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const baseName = `${date}-${slugify(options.request, "task").slice(0, policy.slug_max_length)}`;
  const worktreeRoot = path.resolve(projectRoot, policy.worktree_root);
  await mkdir(worktreeRoot, { recursive: true });
  let suffix = 0;
  let name = baseName;
  let branch = `${normalizeBranchPrefix(policy.branch_prefix)}${name}`;
  let worktreePath = path.join(worktreeRoot, name);
  while (await refOrPathExists(projectRoot, branch, worktreePath)) {
    suffix += 1;
    name = `${baseName}-${suffix}`;
    branch = `${normalizeBranchPrefix(policy.branch_prefix)}${name}`;
    worktreePath = path.join(worktreeRoot, name);
  }
  await execa("git", ["worktree", "add", "-b", branch, worktreePath, base.ref], { cwd: projectRoot });
  const targetStateRoot = path.join(worktreePath, ".agt");
  const targetStore = new RuntimeStore(targetStateRoot);
  await targetStore.ensureConfig(config);
  return {
    repoRoot: worktreePath,
    stateRoot: targetStateRoot,
    worktree: {
      path: worktreePath,
      branch,
      base_ref: base.ref,
      base_commit: base.commit,
      policy_source: "config.json",
      policy_snapshot_path: targetStore.configPath(),
    },
  };
}

// 读取当前仓库分支名；非 git 目录或失败时返回空字符串。
// Reads the current branch name and returns an empty string for non-git or failed reads.
export async function currentBranch(repoRoot: string): Promise<string> {
  try {
    const result = await execa("git", ["branch", "--show-current"], { cwd: repoRoot });
    return result.stdout.trim();
  } catch {
    return "";
  }
}

// 按配置候选顺序解析 worktree base ref，找不到时退回 HEAD。
// Resolves the worktree base ref from configured candidates and falls back to HEAD.
async function resolveBaseRef(projectRoot: string, candidates: string[]): Promise<{ ref: string; commit: string }> {
  for (const candidate of candidates) {
    try {
      const result = await execa("git", ["rev-parse", "--verify", `${candidate}^{commit}`], { cwd: projectRoot });
      return { ref: candidate, commit: result.stdout.trim() };
    } catch {
      // Try the next configured base.
    }
  }
  const head = await execa("git", ["rev-parse", "HEAD"], { cwd: projectRoot });
  return { ref: "HEAD", commit: head.stdout.trim() };
}

// 检查目标分支或 worktree 路径是否已存在，避免覆盖已有任务。
// Checks whether the target branch or worktree path already exists to avoid overwriting tasks.
async function refOrPathExists(projectRoot: string, branch: string, worktreePath: string): Promise<boolean> {
  try {
    await execa("git", ["rev-parse", "--verify", "--quiet", branch], { cwd: projectRoot });
    return true;
  } catch {
    // Branch is free.
  }
  try {
    await execa("test", ["-e", worktreePath]);
    return true;
  } catch {
    return false;
  }
}

// 规范化分支前缀，确保拼接分支名时只有一个尾部斜杠。
// Normalizes a branch prefix so composed branch names have one trailing slash.
function normalizeBranchPrefix(prefix: string): string {
  return prefix.endsWith("/") ? prefix : `${prefix}/`;
}
