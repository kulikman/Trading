#!/usr/bin/env node
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const DEFAULT_CONFIG_PATH = ".github/agent-policy-sync.yml";
const DEFAULT_BRANCH_PREFIX = "agent-policy-sync";
const SYNC_LABELS = [
  ["agent-policy-sync", "0969da", "Automated Solo Founder Agent OS policy sync"],
  ["automated-pr", "5319e7", "Pull request created by automation"],
];
const FORBIDDEN_SYNC_DESTS = [
  "AGENTS.md",
  "CLAUDE.md",
  ".claude/",
  ".codex/",
  ".cursor/",
  ".github/workflows/",
];

export function parseSyncConfigText(text) {
  const repos = [];
  const files = [];
  let inReposBlock = false;
  let currentFile = null;

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();

    if (line === "- repos: |") {
      inReposBlock = true;
      continue;
    }

    if (inReposBlock && line.startsWith("kulikman/")) {
      repos.push(line);
      continue;
    }

    if (inReposBlock && line === "files:") {
      inReposBlock = false;
      continue;
    }

    const sourceMatch = rawLine.match(/^\s+- source: (.+)$/);
    if (sourceMatch) {
      currentFile = { dest: "", source: sourceMatch[1].trim() };
      files.push(currentFile);
      continue;
    }

    const destMatch = rawLine.match(/^\s+dest: (.+)$/);
    if (destMatch && currentFile) currentFile.dest = destMatch[1].trim();
  }

  return { files, repos };
}

export function validateFileMappings(files) {
  const errors = [];

  for (const file of files) {
    for (const key of ["source", "dest"]) {
      const value = file[key];
      if (!value) errors.push(`mapping is missing ${key}`);
      if (value.startsWith("/") || value.includes("..")) {
        errors.push(`unsafe ${key} path: ${value}`);
      }
    }

    const dest = file.dest.replace(/\\/g, "/");
    for (const forbidden of FORBIDDEN_SYNC_DESTS) {
      if (dest === forbidden || dest.startsWith(forbidden)) {
        errors.push(`refusing to sync live agent/workflow path: ${dest}`);
      }
    }
  }

  return errors;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    encoding: "utf8",
    env: options.env || process.env,
    stdio: options.capture ? "pipe" : "inherit",
  });

  if (result.status !== 0) {
    const detail = result.stderr || result.stdout || "";
    throw new Error(`${command} ${args.join(" ")} failed\n${detail}`.trim());
  }

  return (result.stdout || "").trim();
}

function sourceVersion() {
  return readFileSync(".agent-policy-version", "utf8").trim();
}

function readConfig(configPath) {
  const text = readFileSync(configPath, "utf8");
  const config = parseSyncConfigText(text);
  const errors = validateFileMappings(config.files);

  for (const file of config.files) {
    if (!existsSync(file.source)) errors.push(`missing source path: ${file.source}`);
  }

  if (config.repos.length === 0) errors.push("sync config contains no repositories");
  if (config.files.length === 0) errors.push("sync config contains no file mappings");
  if (errors.length > 0) throw new Error(errors.join("\n"));

  return config;
}

function parseArgs(argv) {
  const options = {
    branchPrefix: DEFAULT_BRANCH_PREFIX,
    configPath: DEFAULT_CONFIG_PATH,
    dryRun: true,
    limit: 0,
    repos: [],
    watchChecks: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--") continue;
    else if (arg === "--apply") options.dryRun = false;
    else if (arg === "--dry-run") options.dryRun = true;
    else if (arg === "--watch-checks") options.watchChecks = true;
    else if (arg === "--config") options.configPath = argv[++index];
    else if (arg === "--repo") options.repos.push(argv[++index]);
    else if (arg === "--limit") options.limit = Number(argv[++index]);
    else if (arg === "--branch-prefix") options.branchPrefix = argv[++index];
    else throw new Error(`unknown argument: ${arg}`);
  }

  return options;
}

function copyMappingToRepo(mapping, repoPath) {
  const sourcePath = resolve(mapping.source);
  const destPath = join(repoPath, mapping.dest);

  rmSync(destPath, { force: true, recursive: true });
  cpSync(sourcePath, destPath, { recursive: statSync(sourcePath).isDirectory() });
}

function changedFiles(repoPath) {
  const output = run("git", ["status", "--porcelain", "--untracked-files=all"], {
    capture: true,
    cwd: repoPath,
  });
  return output
    .split("\n")
    .filter(Boolean)
    .map((line) => parsePorcelainPath(line));
}

export function parsePorcelainPath(line) {
  const path = line.replace(/^.. ?/, "");
  const renameSeparator = " -> ";
  return path.includes(renameSeparator) ? path.split(renameSeparator).at(-1) : path;
}

function isAllowedChange(path, files) {
  const normalized = path.replace(/\\/g, "/");
  return files.some((file) => {
    const dest = file.dest.replace(/\\/g, "/");
    return dest.endsWith("/") ? normalized.startsWith(dest) : normalized === dest;
  });
}

function assertOnlyAllowedChanges(repoPath, files) {
  const changed = changedFiles(repoPath);
  const unexpected = changed.filter((path) => !isAllowedChange(path, files));
  if (unexpected.length > 0) {
    throw new Error(`unexpected changed files:\n${unexpected.join("\n")}`);
  }
  return changed;
}

function repoName(slug) {
  return slug.split("/").at(-1) || slug;
}

function existingPrUrl(slug, branch) {
  return run(
    "gh",
    ["pr", "list", "--repo", slug, "--head", branch, "--json", "url", "--jq", ".[0].url"],
    { capture: true }
  );
}

function createOrUpdatePr(slug, branch, defaultBranch, version, changed) {
  const existing = existingPrUrl(slug, branch);
  if (existing) return existing;

  const body = [
    "Automated PR-only propagation from `kulikman/Template-Projects`.",
    "",
    `Policy version: \`${version}\``,
    "",
    "Synced canonical bundle paths only:",
    ...changed.map((path) => `- \`${path}\``),
    "",
    "This PR intentionally does not modify live repo files such as `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.cursor/` or workflows.",
  ].join("\n");

  const url = run(
    "gh",
    [
      "pr",
      "create",
      "--repo",
      slug,
      "--head",
      branch,
      "--base",
      defaultBranch,
      "--title",
      `chore(agent-policy): sync policy bundle ${version}`,
      "--body",
      body,
    ],
    { capture: true }
  );

  for (const [label, color, description] of SYNC_LABELS) {
    spawnSync(
      "gh",
      ["label", "create", label, "--repo", slug, "--color", color, "--description", description],
      {
        encoding: "utf8",
        stdio: "pipe",
      }
    );

    const edit = spawnSync("gh", ["pr", "edit", url, "--add-label", label], {
      encoding: "utf8",
      stdio: "pipe",
    });
    if (edit.status !== 0) {
      console.warn(`warning: could not add label "${label}" to ${url}`);
    }
  }

  return url;
}

function waitForChecks(prUrl) {
  run("gh", ["pr", "checks", prUrl, "--watch", "--fail-fast"]);
}

function syncRepo(slug, files, options) {
  const version = sourceVersion();
  const branch = `${options.branchPrefix}/${version}`;
  const tmpRoot = mkdtempSync(join(tmpdir(), "agent-policy-sync-"));
  const repoPath = join(tmpRoot, repoName(slug));

  console.log(`\n## ${slug}`);
  run("gh", ["repo", "clone", slug, repoPath, "--", "--quiet"]);

  const defaultBranch = run("git", ["branch", "--show-current"], {
    capture: true,
    cwd: repoPath,
  });

  const branchExists =
    spawnSync("git", ["ls-remote", "--exit-code", "--heads", "origin", branch], {
      cwd: repoPath,
      encoding: "utf8",
      stdio: "pipe",
    }).status === 0;

  if (branchExists) {
    run("git", ["fetch", "origin", branch], { cwd: repoPath });
    run("git", ["checkout", "-B", branch, `origin/${branch}`], { cwd: repoPath });
  } else {
    run("git", ["checkout", "-b", branch], { cwd: repoPath });
  }

  for (const file of files) copyMappingToRepo(file, repoPath);

  const changed = assertOnlyAllowedChanges(repoPath, files);
  if (changed.length === 0) {
    console.log("No policy changes required.");
    rmSync(tmpRoot, { force: true, recursive: true });
    return { changed: 0, prUrl: "", slug, status: "unchanged" };
  }

  console.log(`Changed files: ${changed.length}`);
  if (options.dryRun) {
    for (const path of changed) console.log(`- ${path}`);
    rmSync(tmpRoot, { force: true, recursive: true });
    return { changed: changed.length, prUrl: "", slug, status: "planned" };
  }

  run("git", ["add", ...changed], { cwd: repoPath });
  run("git", ["commit", "-m", `chore(agent-policy): sync policy bundle ${version}`], {
    cwd: repoPath,
  });
  run("git", ["push", "origin", `HEAD:${branch}`], { cwd: repoPath });

  const prUrl = createOrUpdatePr(slug, branch, defaultBranch, version, changed);
  console.log(`PR: ${prUrl}`);

  if (options.watchChecks) waitForChecks(prUrl);

  rmSync(tmpRoot, { force: true, recursive: true });
  return { changed: changed.length, prUrl, slug, status: "pr" };
}

export function selectRepos(repos, options) {
  let selected =
    options.repos.length > 0 ? repos.filter((repo) => options.repos.includes(repo)) : repos;
  if (options.limit > 0) selected = selected.slice(0, options.limit);
  return selected;
}

export function main(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  const config = readConfig(options.configPath);
  const selectedRepos = selectRepos(config.repos, options);

  if (!options.dryRun && !process.env.GH_TOKEN && !process.env.GITHUB_TOKEN) {
    throw new Error("write sync requires GH_TOKEN or GITHUB_TOKEN with target repository access");
  }

  console.log("# Agent Policy PR Sync");
  console.log(`Mode: ${options.dryRun ? "dry-run" : "apply"}`);
  console.log(`Targets: ${selectedRepos.length}`);
  console.log(`Config: ${options.configPath}`);

  const results = selectedRepos.map((slug) => syncRepo(slug, config.files, options));

  console.log("\n# Summary");
  for (const result of results) {
    const detail = result.prUrl ? ` ${result.prUrl}` : "";
    console.log(`- ${result.slug}: ${result.status} (${result.changed} files)${detail}`);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  }
}
