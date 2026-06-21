#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import path from "node:path";

const command = process.argv[2];
const args = parseArgs(process.argv.slice(3));

try {
  if (command === "verify-version") {
    await verifyVersion();
  } else if (command === "release-type") {
    releaseType();
  } else if (command === "extract-changelog") {
    await extractChangelog();
  } else if (command === "render-install") {
    await renderInstall();
  } else {
    usage();
    process.exitCode = 1;
  }
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}

async function verifyVersion() {
  const tag = requireArg("--tag");
  const packagePath = args["--package"] ?? "package.json";
  const pkg = JSON.parse(await readFile(packagePath, "utf8"));
  const actual = versionFromTag(tag);
  if (actual !== pkg.version) {
    throw new Error(`tag ${actual} does not match package version ${pkg.version}`);
  }
  console.log(pkg.version);
}

function releaseType() {
  const version = requireArg("--version");
  const prerelease = isPrereleaseVersion(version);
  if (args["--github-args"]) {
    if (prerelease) {
      console.log("--prerelease --latest=false");
    }
    return;
  }
  console.log(prerelease ? "prerelease" : "stable");
}

async function extractChangelog() {
  const version = requireArg("--version");
  const changelogPath = requireArg("--changelog");
  const markdown = await readFile(changelogPath, "utf8");
  console.log(extractVersionSection(markdown, version));
}

async function renderInstall() {
  const templatePath = args["--template"] ?? path.join("scripts", "release", "install.sh.template");
  const replacements = {
    "{{ repo }}": requireArg("--repo"),
    "{{ tag }}": requireArg("--tag"),
    "{{ version }}": requireArg("--version"),
    "{{ tarball }}": requireArg("--tarball"),
  };
  let content = await readFile(templatePath, "utf8");
  for (const [token, value] of Object.entries(replacements)) {
    content = content.replaceAll(token, value);
  }
  process.stdout.write(content);
}

function parseArgs(values) {
  const parsed = {};
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (!value.startsWith("--")) {
      throw new Error(`Unexpected argument: ${value}`);
    }
    const next = values[index + 1];
    if (!next || next.startsWith("--")) {
      parsed[value] = true;
    } else {
      parsed[value] = next;
      index += 1;
    }
  }
  return parsed;
}

function requireArg(name) {
  const value = args[name];
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function versionFromTag(tag) {
  return tag.replace(/^refs\/tags\//, "").replace(/^v/, "");
}

function isPrereleaseVersion(version) {
  return /(a|alpha|b|beta|rc|pre|preview|dev)[.-]?\d+/i.test(version);
}

function extractVersionSection(markdown, version) {
  const header = `## [${version}]`;
  const lines = markdown.split(/\r?\n/);
  const start = lines.findIndex((line) => line.startsWith(header));
  if (start === -1) {
    throw new Error(`CHANGELOG.md is missing a section for ${version}`);
  }
  let end = lines.length;
  for (let index = start + 1; index < lines.length; index += 1) {
    if (lines[index].startsWith("## [")) {
      end = index;
      break;
    }
  }
  return `${lines.slice(start, end).join("\n").trim()}\n`;
}

function usage() {
  console.error(`Usage:
  node scripts/release/release-tools.mjs verify-version --tag <tag> [--package package.json]
  node scripts/release/release-tools.mjs release-type --version <version> [--github-args]
  node scripts/release/release-tools.mjs extract-changelog --version <version> --changelog CHANGELOG.md
  node scripts/release/release-tools.mjs render-install --repo <owner/repo> --tag <tag> --version <version> --tarball <name> [--template path]`);
}
