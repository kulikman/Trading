#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, join, relative } from "node:path";

const repoRoot = process.env.AGENT_REPO_ROOT || "/Users/DEV";
const outputPath =
  process.env.AGENT_INVENTORY_OUT || "docs/18_AGENT_REPO_INVENTORY.md";
const policyVersionPath = ".agent-policy-version";
const currentPolicyVersion = readOptional(policyVersionPath)?.trim() || "unknown";

const ignoredDirs = new Set([
  ".cache",
  ".git",
  ".next",
  ".pnpm-store",
  ".turbo",
  ".venv",
  "coverage",
  "dist",
  "node_modules",
  "test-results",
]);

function readOptional(path) {
  try {
    return readFileSync(path, "utf8");
  } catch {
    return null;
  }
}

function listDirectories(path) {
  try {
    return readdirSync(path, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => join(path, entry.name));
  } catch {
    return [];
  }
}

function findGitRepos(root, maxDepth = 5) {
  const repos = [];

  function walk(path, depth) {
    if (depth > maxDepth) return;
    if (existsSync(join(path, ".git"))) {
      repos.push(path);
      return;
    }

    for (const child of listDirectories(path)) {
      if (ignoredDirs.has(basename(child))) continue;
      walk(child, depth + 1);
    }
  }

  walk(root, 0);
  return repos.sort((a, b) => a.localeCompare(b));
}

function git(repo, args) {
  try {
    return execFileSync("git", ["-C", repo, ...args], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "";
  }
}

function countFiles(path) {
  if (!existsSync(path)) return 0;
  const stats = statSync(path);
  if (stats.isFile()) return 1;
  if (!stats.isDirectory()) return 0;

  let count = 0;
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    const child = join(path, entry.name);
    if (entry.isDirectory()) count += countFiles(child);
    if (entry.isFile()) count += 1;
  }
  return count;
}

function readPackageJson(repo) {
  const raw = readOptional(join(repo, "package.json"));
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function findPackageJsonFiles(repo, maxDepth = 4) {
  const files = [];

  function walk(path, depth) {
    if (depth > maxDepth) return;

    for (const entry of readdirSync(path, { withFileTypes: true })) {
      if (ignoredDirs.has(entry.name)) continue;

      const child = join(path, entry.name);
      if (entry.isFile() && entry.name === "package.json") {
        files.push(child);
        continue;
      }

      if (entry.isDirectory()) walk(child, depth + 1);
    }
  }

  try {
    walk(repo, 0);
  } catch {
    return [];
  }

  return files.sort((a, b) => a.localeCompare(b));
}

function readPackageJsonFile(path) {
  const raw = readOptional(path);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function readWorkspacePackageJson(repo) {
  return findPackageJsonFiles(repo)
    .map((path) => readPackageJsonFile(path))
    .filter(Boolean);
}

function getPackageNames(packageJson) {
  if (!packageJson) return new Set();
  return new Set([
    ...Object.keys(packageJson.dependencies || {}),
    ...Object.keys(packageJson.devDependencies || {}),
  ]);
}

function inferStack(repo, packageJson, workspacePackages = []) {
  const packages = [packageJson, ...workspacePackages].filter(Boolean);
  const deps = new Set();
  for (const currentPackage of packages) {
    for (const name of getPackageNames(currentPackage)) deps.add(name);
  }
  const scripts = packageJson?.scripts || {};
  const signals = [];

  if (deps.has("next")) {
    const nextPackage = packages.find(
      (currentPackage) => currentPackage.dependencies?.next || currentPackage.devDependencies?.next
    );
    const version = String(nextPackage?.dependencies?.next || nextPackage?.devDependencies?.next || "");
    signals.push(`Next.js${version ? ` ${version}` : ""}`);
  }
  if (deps.has("react")) signals.push("React");
  if (deps.has("vite")) signals.push("Vite");
  if (deps.has("hono")) signals.push("Hono");
  if (deps.has("@modelcontextprotocol/sdk")) signals.push("MCP");
  if (deps.has("@supabase/supabase-js") || deps.has("@supabase/ssr")) {
    signals.push("Supabase");
  }
  if (deps.has("stripe")) signals.push("Stripe");
  if (existsSync(join(repo, "pubspec.yaml"))) signals.push("Flutter/Dart");
  if (existsSync(join(repo, "Dockerfile")) || existsSync(join(repo, "docker-compose.yml"))) {
    signals.push("Docker");
  }
  if (existsSync(join(repo, "supabase"))) signals.push("Supabase local");
  if (!packageJson && existsSync(join(repo, "index.html"))) signals.push("Static HTML");
  if (scripts.verify) signals.push("verify script");

  return signals.length ? signals.join(", ") : "unknown";
}

function artifactStatus(repo) {
  return {
    agents: existsSync(join(repo, "AGENTS.md")),
    claude: existsSync(join(repo, "CLAUDE.md")),
    claudeCommands: countFiles(join(repo, ".claude", "commands")),
    claudeRules: countFiles(join(repo, ".claude", "rules")),
    claudeSkills: countFiles(join(repo, ".claude", "skills")),
    codex: existsSync(join(repo, ".codex")),
    cursorRules: countFiles(join(repo, ".cursor", "rules")),
  };
}

function policyStatus(repo) {
  const version = readOptional(join(repo, policyVersionPath))?.trim() || "";
  if (!version) return { status: "missing", version: "" };
  if (version === currentPolicyVersion) return { status: "current", version };
  return { status: "outdated", version };
}

function inspectRepo(repo) {
  const packageJson = readPackageJson(repo);
  const workspacePackages = readWorkspacePackageJson(repo).filter(
    (currentPackage) => currentPackage !== packageJson
  );
  const branch = git(repo, ["branch", "--show-current"]) || "detached";
  const remote = git(repo, ["remote", "get-url", "origin"]) || "none";
  const dirtyLines = git(repo, ["status", "--short"])
    .split("\n")
    .filter(Boolean).length;
  const lastCommit = git(repo, ["log", "-1", "--format=%h %s"]) || "none";

  return {
    artifacts: artifactStatus(repo),
    branch,
    dirtyLines,
    lastCommit,
    name: basename(repo),
    packageName: packageJson?.name || "",
    path: repo,
    policy: policyStatus(repo),
    remote,
    scripts: Object.keys(packageJson?.scripts || {}).sort(),
    stack: inferStack(repo, packageJson, workspacePackages),
  };
}

function yes(value) {
  return value ? "yes" : "no";
}

function formatCell(value) {
  return String(value || "").replaceAll("|", "\\|").replaceAll("\n", " ");
}

function renderReport(repos) {
  const generatedAt = new Date().toISOString();
  const current = repos.filter((repo) => repo.policy.status === "current").length;
  const missing = repos.filter((repo) => repo.policy.status === "missing").length;
  const outdated = repos.filter((repo) => repo.policy.status === "outdated").length;
  const dirty = repos.filter((repo) => repo.dirtyLines > 0).length;

  const lines = [
    "# Agent Repository Inventory",
    "",
    `Generated: ${generatedAt}`,
    "",
    `Source: local filesystem scan of \`${repoRoot}\``,
    "",
    `Current policy version: \`${currentPolicyVersion}\``,
    "",
    "## Summary",
    "",
    `- Repositories found: ${repos.length}`,
    `- Current policy version: ${current}`,
    `- Missing policy version: ${missing}`,
    `- Outdated policy version: ${outdated}`,
    `- Repositories with dirty working tree: ${dirty}`,
    "",
    "## Matrix",
    "",
    "| Repo | Relative path | Stack signals | Branch | Dirty | Policy | AGENTS | CLAUDE | Claude commands | Claude rules | Claude skills | Cursor rules | Codex | Remote |",
    "|---|---|---|---|---:|---|---|---|---:|---:|---:|---:|---|---|",
  ];

  for (const repo of repos) {
    const relativePath = relative(repoRoot, repo.path) || ".";
    lines.push(
      [
        formatCell(repo.name),
        formatCell(relativePath),
        formatCell(repo.stack),
        formatCell(repo.branch),
        repo.dirtyLines,
        formatCell(
          repo.policy.version
            ? `${repo.policy.status} (${repo.policy.version})`
            : repo.policy.status
        ),
        yes(repo.artifacts.agents),
        yes(repo.artifacts.claude),
        repo.artifacts.claudeCommands,
        repo.artifacts.claudeRules,
        repo.artifacts.claudeSkills,
        repo.artifacts.cursorRules,
        yes(repo.artifacts.codex),
        formatCell(repo.remote),
      ].join(" | ").replace(/^/, "| ").replace(/$/, " |")
    );
  }

  lines.push(
    "",
    "## Notes",
    "",
    "- Stack signals are inferred from files and `package.json`; they are audit hints, not authoritative architecture labels.",
    "- Dirty counts come from `git status --short`; this report does not modify target repositories.",
    "- Missing `.agent-policy-version` means the repository has not yet declared compatibility with the Template-Projects policy source.",
    "- Archived or legacy folders are included when they are real git repositories under the scanned root.",
    ""
  );

  return lines.join("\n");
}

const repos = findGitRepos(repoRoot).map(inspectRepo);
mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, renderReport(repos), "utf8");
console.log(`wrote ${outputPath}`);
console.log(`repositories: ${repos.length}`);
