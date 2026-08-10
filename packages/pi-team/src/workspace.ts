import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

export type RunWorkspace = {
  root: string;
  runId: string;
};

export async function createRunWorkspace(baseDir: string, runId: string): Promise<RunWorkspace> {
  const root = path.resolve(baseDir, "runs", runId);
  await mkdir(root, { recursive: true });
  return { root, runId };
}

export async function writeWorkspaceFile(workspace: RunWorkspace, relativePath: string, content: string): Promise<string> {
  const target = path.resolve(workspace.root, relativePath);
  if (!target.startsWith(`${workspace.root}${path.sep}`)) {
    throw new Error(`Workspace path escapes run root: ${relativePath}`);
  }
  await mkdir(path.dirname(target), { recursive: true });
  const temporary = `${target}.${process.pid}.tmp`;
  await writeFile(temporary, content, "utf8");
  await rename(temporary, target);
  return target;
}

export async function readWorkspaceFile(workspace: RunWorkspace, relativePath: string): Promise<string> {
  const target = path.resolve(workspace.root, relativePath);
  if (!target.startsWith(`${workspace.root}${path.sep}`)) {
    throw new Error(`Workspace path escapes run root: ${relativePath}`);
  }
  return readFile(target, "utf8");
}

export async function writeWorkspaceJson<T>(workspace: RunWorkspace, relativePath: string, value: T): Promise<string> {
  return writeWorkspaceFile(workspace, relativePath, `${JSON.stringify(value, null, 2)}\n`);
}

export async function readWorkspaceJson<T>(workspace: RunWorkspace, relativePath: string): Promise<T> {
  return JSON.parse(await readWorkspaceFile(workspace, relativePath)) as T;
}
