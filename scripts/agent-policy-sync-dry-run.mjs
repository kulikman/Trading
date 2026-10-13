#!/usr/bin/env node
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const repoRoot = process.env.AGENT_REPO_ROOT || "/Users/DEV";
const configPath = ".github/agent-policy-sync.yml";
const inventoryPath = "docs/18_AGENT_REPO_INVENTORY.md";

function read(path) {
  return readFileSync(path, "utf8");
}

function parseSyncConfig() {
  const text = read(configPath);
  const repos = text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("kulikman/"));

  const files = [];
  let current = null;

  for (const line of text.split("\n")) {
    const sourceMatch = line.match(/^\s+- source: (.+)$/);
    if (sourceMatch) {
      current = { dest: "", source: sourceMatch[1].trim() };
      files.push(current);
      continue;
    }

    const destMatch = line.match(/^\s+dest: (.+)$/);
    if (destMatch && current) current.dest = destMatch[1].trim();
  }

  return { files, repos };
}

function repoSlugFromRemote(remote) {
  const match = remote.match(/github\.com[:/]kulikman\/([^/.]+)(?:\.git)?$/);
  return match ? `kulikman/${match[1]}` : "";
}

function parseInventory() {
  if (!existsSync(inventoryPath)) return new Map();

  const repos = new Map();
  for (const line of read(inventoryPath).split("\n")) {
    if (!line.startsWith("| ") || line.includes("---")) continue;

    const cells = line.split("|").map((cell) => cell.trim());
    if (cells[1] === "Repo") continue;

    const remote = cells[14];
    const slug = repoSlugFromRemote(remote);
    if (!slug) continue;

    repos.set(slug, {
      localPath: join(repoRoot, cells[2]),
      name: cells[1],
      remote,
    });
  }

  return repos;
}

function listSourceFiles(path) {
  if (!existsSync(path)) return [];

  if (statSync(path).isFile()) return [path];

  const entries = readdirSync(path, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const child = join(path, entry.name);
    if (entry.isDirectory()) {
      files.push(...listSourceFiles(child));
      continue;
    }
    if (entry.isFile()) files.push(child);
  }

  return files;
}

function equivalentFilePath(sourceRoot, destRoot, sourceFile) {
  if (!sourceRoot.endsWith("/")) return destRoot;
  return join(destRoot, relative(sourceRoot, sourceFile));
}

function compareFile(sourceFile, targetFile) {
  if (!existsSync(targetFile)) return "add";
  return read(sourceFile) === read(targetFile) ? "same" : "change";
}

function planForRepo(repo, files) {
  if (!existsSync(repo.localPath)) {
    return { adds: 0, changes: 0, same: 0, unavailable: true };
  }

  const result = { adds: 0, changes: 0, same: 0, unavailable: false };

  for (const file of files) {
    const sourceFiles = listSourceFiles(file.source);
    for (const sourceFile of sourceFiles) {
      const targetFile = equivalentFilePath(file.source, join(repo.localPath, file.dest), sourceFile);
      const status = compareFile(sourceFile, targetFile);
      result[`${status}s`] += 1;
    }
  }

  return result;
}

const { files, repos } = parseSyncConfig();
const inventory = parseInventory();
let hasMissingSource = false;

console.log("# Agent Policy Sync Dry Run");
console.log("");
console.log(`Config: ${configPath}`);
console.log(`Targets: ${repos.length}`);
console.log(`File mappings: ${files.length}`);
console.log("");

for (const file of files) {
  if (!existsSync(file.source)) {
    hasMissingSource = true;
    console.log(`missing source: ${file.source}`);
  }
}

if (hasMissingSource) process.exit(1);

console.log("| Repo | Local path | Add | Change | Same | Notes |");
console.log("|---|---|---:|---:|---:|---|");

for (const slug of repos) {
  const repo = inventory.get(slug);
  if (!repo) {
    console.log(`| ${slug} | n/a | 0 | 0 | 0 | not present in inventory |`);
    continue;
  }

  const plan = planForRepo(repo, files);
  const notes = plan.unavailable ? "local checkout unavailable" : "local diff only";
  console.log(
    `| ${slug} | ${repo.localPath} | ${plan.adds} | ${plan.changes} | ${plan.same} | ${notes} |`
  );
}
