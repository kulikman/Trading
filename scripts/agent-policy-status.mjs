#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

const inventoryPath = "docs/18_AGENT_REPO_INVENTORY.md";
const syncPath = ".github/agent-policy-sync.yml";
const outputPath =
  process.env.AGENT_POLICY_STATUS_OUT || "docs/21_AGENT_POLICY_STATUS.md";

function read(path) {
  return readFileSync(path, "utf8");
}

function parseInventory() {
  if (!existsSync(inventoryPath)) {
    throw new Error(`${inventoryPath} does not exist. Run pnpm agent:inventory first.`);
  }

  return read(inventoryPath)
    .split("\n")
    .filter((line) => line.startsWith("| ") && !line.includes("---"))
    .slice(1)
    .map((line) => {
      const cells = line.split("|").map((cell) => cell.trim());
      return {
        agents: cells[7],
        branch: cells[4],
        claude: cells[8],
        codex: cells[13],
        cursorRules: Number(cells[12] || 0),
        dirty: Number(cells[5] || 0),
        path: cells[2],
        policy: cells[6],
        remote: cells[14],
        repo: cells[1],
        stack: cells[3],
      };
    });
}

function parseSyncTargets() {
  if (!existsSync(syncPath)) return new Set();

  return new Set(
    read(syncPath)
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.startsWith("kulikman/"))
  );
}

function repoSlugFromRemote(remote) {
  const match = remote.match(/github\.com[:/]kulikman\/([^/.]+)(?:\.git)?$/);
  return match ? `kulikman/${match[1]}` : "";
}

function markdownTable(rows, headers) {
  const lines = [
    `| ${headers.join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
  ];

  for (const row of rows) {
    lines.push(`| ${row.map((cell) => String(cell).replaceAll("|", "\\|")).join(" | ")} |`);
  }

  return lines.join("\n");
}

function render() {
  const generatedAt = new Date().toISOString();
  const repos = parseInventory();
  const syncTargets = parseSyncTargets();
  const activeTargets = repos.filter((repo) => syncTargets.has(repoSlugFromRemote(repo.remote)));
  const excluded = repos.filter((repo) => !syncTargets.has(repoSlugFromRemote(repo.remote)));
  const dirty = repos.filter((repo) => repo.dirty > 0);
  const missingPolicy = repos.filter((repo) => repo.policy === "missing");
  const missingAgents = repos.filter((repo) => repo.agents !== "yes");
  const missingClaude = repos.filter((repo) => repo.claude !== "yes");
  const missingCursor = repos.filter((repo) => repo.cursorRules === 0);

  return [
    "# Agent Policy Status",
    "",
    `Generated: ${generatedAt}`,
    "",
    `Source inventory: \`${inventoryPath}\``,
    "",
    "## Summary",
    "",
    `- Local repositories in inventory: ${repos.length}`,
    `- Active sync targets: ${activeTargets.length}`,
    `- Excluded local repositories: ${excluded.length}`,
    `- Missing policy version marker: ${missingPolicy.length}`,
    `- Repositories with dirty working tree: ${dirty.length}`,
    `- Missing AGENTS.md: ${missingAgents.length}`,
    `- Missing CLAUDE.md: ${missingClaude.length}`,
    `- Missing Cursor rules: ${missingCursor.length}`,
    "",
    "## Active Sync Targets",
    "",
    markdownTable(
      activeTargets.map((repo) => [
        repo.repo,
        repoSlugFromRemote(repo.remote),
        repo.stack,
        repo.policy,
        repo.dirty,
      ]),
      ["Repo", "Remote", "Stack signals", "Policy", "Dirty"]
    ),
    "",
    "## Attention Needed",
    "",
    markdownTable(
      [...new Set([...dirty, ...missingPolicy, ...missingAgents, ...missingClaude, ...missingCursor])]
        .map((repo) => [
          repo.repo,
          repo.path,
          repo.policy,
          repo.dirty,
          repo.agents,
          repo.claude,
          repo.cursorRules,
        ]),
      ["Repo", "Path", "Policy", "Dirty", "AGENTS", "CLAUDE", "Cursor rules"]
    ),
    "",
    "## Excluded Local Repositories",
    "",
    markdownTable(
      excluded.map((repo) => [repo.repo, repo.path, repo.remote || "none", repo.stack]),
      ["Repo", "Path", "Remote", "Stack signals"]
    ),
    "",
    "## Next Actions",
    "",
    "1. Review dirty repositories before applying sync PRs.",
    "2. Run the manual sync workflow in dry-run mode first.",
    "3. Merge policy marker PRs only after target repo checks pass.",
    "4. Add generated-block merge support before syncing live `AGENTS.md`, `CLAUDE.md`, `.claude/` or `.cursor/` files.",
    "",
  ].join("\n");
}

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, render(), "utf8");
console.log(`wrote ${outputPath}`);
