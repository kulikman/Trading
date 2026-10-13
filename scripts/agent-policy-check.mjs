#!/usr/bin/env node
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const errors = [];
const warnings = [];

function read(path) {
  return readFileSync(path, "utf8");
}

function captureList(text, pattern) {
  return [...text.matchAll(pattern)].map((match) => match[1].trim());
}

function addError(message) {
  errors.push(message);
}

function addWarning(message) {
  warnings.push(message);
}

function assertExists(path, context) {
  if (!existsSync(path)) addError(`${context}: missing ${path}`);
}

function versionFromManifest(text) {
  return text.match(/^version:\s*(.+)$/m)?.[1]?.trim() || "";
}

function validateVersion() {
  const marker = read(".agent-policy-version").trim();
  const manifest = read("solo-founder-os/policy/manifest.yml");
  const manifestVersion = versionFromManifest(manifest);

  if (marker !== manifestVersion) {
    addError(
      `.agent-policy-version (${marker}) does not match manifest version (${manifestVersion})`
    );
  }
}

function validateManifestPaths() {
  const manifest = read("solo-founder-os/policy/manifest.yml");
  const paths = captureList(manifest, /^\s+-\s+(solo-founder-os\/[^\s]+)$/gm);

  for (const path of paths) {
    assertExists(path, "manifest canonical_paths");
  }

  return paths;
}

function validatePolicyPacks() {
  const packDir = "solo-founder-os/policy/packs";
  const packs = readdirSync(packDir)
    .filter((file) => file.endsWith(".yml"))
    .sort();

  for (const file of packs) {
    const packPath = join(packDir, file);
    validateInherits(packPath, read(packPath));
  }
}

function validateProjectProfiles() {
  const profileDir = "solo-founder-os/project-profiles";
  const profiles = readdirSync(profileDir)
    .filter((file) => file.endsWith(".yml"))
    .sort();

  for (const file of profiles) {
    const profilePath = join(profileDir, file);
    const profileText = read(profilePath);
    validateInherits(profilePath, profileText);
    validateTargetProfile(profilePath, profileText);
  }
}

function parseProfileFields(text) {
  const profile = {
    checks: [],
    forbidden: [],
    project: text.match(/^project:\s*(.+)$/m)?.[1]?.trim() || "",
    protectedFiles: [],
    repo: text.match(/^repo:\s*(.+)$/m)?.[1]?.trim() || "",
    stacks: [],
  };
  let section = "";
  let subsection = "";

  for (const line of text.split("\n")) {
    const rootMatch = line.match(/^([a-z_]+):/);
    if (rootMatch) {
      section = rootMatch[1];
      subsection = "";
      continue;
    }

    const subsectionMatch = line.match(/^\s{2}([a-z_]+):/);
    if (subsectionMatch) {
      subsection = subsectionMatch[1];
      continue;
    }

    const itemMatch = line.match(/^\s{4}- (.+)$/);
    if (!itemMatch) continue;

    const value = itemMatch[1].trim();
    if (section === "inherits" && subsection === "stacks") profile.stacks.push(value);
    if (section === "overrides" && subsection === "checks") profile.checks.push(value);
    if (section === "overrides" && subsection === "forbidden") profile.forbidden.push(value);
    if (section === "overrides" && subsection === "protected_files") {
      profile.protectedFiles.push(value);
    }
  }

  return profile;
}

function inventoryRows() {
  const inventoryPath = "docs/18_AGENT_REPO_INVENTORY.md";
  if (!existsSync(inventoryPath)) return [];

  return read(inventoryPath)
    .split("\n")
    .filter((line) => line.startsWith("| ") && !line.includes("---"))
    .slice(1)
    .map((line) => {
      const cells = line.split("|").map((cell) => cell.trim());
      return {
        branch: cells[4],
        dirty: Number(cells[5] || 0),
        localPath: `/Users/DEV/${cells[2]}`,
        policy: cells[6],
        remote: cells[14],
        repo: cells[1],
        stack: cells[3],
      };
    });
}

function profileInventoryRow(profile) {
  const expected = profile.repo;
  return inventoryRows().find((row) => repoSlugFromRemote(row.remote) === expected);
}

function repoSlugFromRemote(remote) {
  const match = remote.match(/github\.com[:/]kulikman\/([^/.]+)(?:\.git)?$/);
  return match ? `kulikman/${match[1]}` : "";
}

function validateTargetProfile(profilePath, text) {
  const profile = parseProfileFields(text);
  if (!profile.repo) return;

  const row = profileInventoryRow(profile);
  if (!row) {
    addWarning(`${profilePath}: target repo is not present in inventory: ${profile.repo}`);
    return;
  }

  validateTargetChecks(profilePath, profile, row);
  validateTargetStack(profilePath, profile, row);
  validateTargetProtectedFiles(profilePath, profile, row);
  validateTargetForbiddenPaths(profilePath, profile, row);
}

function readPackageScripts(repoPath) {
  const packageJsonPath = join(repoPath, "package.json");
  if (!existsSync(packageJsonPath)) return null;

  try {
    return JSON.parse(read(packageJsonPath)).scripts || {};
  } catch {
    addWarning(`${repoPath}: package.json could not be parsed`);
    return null;
  }
}

function validateTargetChecks(profilePath, profile, row) {
  const scripts = readPackageScripts(row.localPath);
  if (!scripts) {
    if (profile.checks.length > 0) {
      addWarning(`${profilePath}: target has checks but no readable package.json: ${row.localPath}`);
    }
    return;
  }

  for (const check of profile.checks) {
    const pnpmScript = check.match(/^pnpm\s+([^\s]+)/)?.[1];
    if (pnpmScript && !scripts[pnpmScript]) {
      addError(`${profilePath}: check command is not in target package.json scripts: ${check}`);
    }
  }
}

function validateTargetStack(profilePath, profile, row) {
  const stack = row.stack.toLowerCase();

  for (const inheritedStack of profile.stacks) {
    if (inheritedStack === "next15" && !stack.includes("next.js 15")) {
      addError(`${profilePath}: inherits next15 but inventory stack is "${row.stack}"`);
    }

    if (inheritedStack === "next16" && !stack.includes("next.js 16")) {
      addError(`${profilePath}: inherits next16 but inventory stack is "${row.stack}"`);
    }

    if (inheritedStack === "flutter" && !stack.includes("flutter")) {
      addError(`${profilePath}: inherits flutter but inventory stack is "${row.stack}"`);
    }

    if (inheritedStack === "hono-mcp" && !stack.includes("hono") && !stack.includes("mcp")) {
      addWarning(`${profilePath}: inherits hono-mcp but inventory stack is "${row.stack}"`);
    }
  }
}

function protectedPathExists(repoPath, protectedPath) {
  const basePath = protectedPath.replace(/\/\*\*$/, "");
  return existsSync(join(repoPath, basePath));
}

function looksLikePath(value) {
  return value.includes("/") || value.includes(".");
}

function validateTargetProtectedFiles(profilePath, profile, row) {
  for (const protectedFile of profile.protectedFiles) {
    if (!protectedPathExists(row.localPath, protectedFile)) {
      addWarning(`${profilePath}: protected path not found in target repo: ${protectedFile}`);
    }
  }
}

function validateTargetForbiddenPaths(profilePath, profile, row) {
  for (const forbidden of profile.forbidden) {
    if (!looksLikePath(forbidden)) continue;

    if (protectedPathExists(row.localPath, forbidden)) {
      addError(`${profilePath}: forbidden path exists in target repo: ${forbidden}`);
    }
  }
}

function validateInherits(path, text) {
  let inInherits = false;
  let section = "";

  for (const line of text.split("\n")) {
    if (line.match(/^inherits:/)) {
      inInherits = true;
      continue;
    }

    if (inInherits && line.match(/^[a-z_]+:/)) {
      inInherits = false;
      section = "";
    }

    if (!inInherits) continue;

    const sectionMatch = line.match(/^\s{2}(core|stacks|domains|skills):/);
    if (sectionMatch) {
      section = sectionMatch[1];
      continue;
    }

    const itemMatch = line.match(/^\s{4}- ([a-z0-9-]+)$/);
    if (!itemMatch || !section) continue;

    const name = itemMatch[1];
    const folder = section === "core" ? "core" : section;
    const extension = section === "skills" ? "yml" : "md";
    assertExists(`solo-founder-os/${folder}/${name}.${extension}`, `${path} ${section}`);
  }
}

function validateSkillRequirements() {
  const skillDir = "solo-founder-os/skills";
  const skills = readdirSync(skillDir)
    .filter((file) => file.endsWith(".yml"))
    .sort();

  for (const file of skills) {
    const skillPath = join(skillDir, file);
    const text = read(skillPath);
    let inRequires = false;
    let section = "";

    for (const line of text.split("\n")) {
      if (line.match(/^requires:/)) {
        inRequires = true;
        continue;
      }
      if (inRequires && line.match(/^[a-z_]+:/)) {
        inRequires = false;
        section = "";
      }
      if (!inRequires) continue;

      const sectionMatch = line.match(/^\s{2}(core|stacks|domains|skills):/);
      if (sectionMatch) {
        section = sectionMatch[1];
        continue;
      }

      const itemMatch = line.match(/^\s{4}- ([a-z0-9-]+)$/);
      if (!itemMatch || !section) continue;

      const name = itemMatch[1];
      const folder = section === "core" ? "core" : section;
      const extension = section === "skills" ? "yml" : "md";
      assertExists(`solo-founder-os/${folder}/${name}.${extension}`, `${skillPath} requires`);
    }
  }
}

function inventoryRemotes() {
  const inventoryPath = "docs/18_AGENT_REPO_INVENTORY.md";
  if (!existsSync(inventoryPath)) return new Set();

  const remotes = new Set();
  for (const line of read(inventoryPath).split("\n")) {
    if (!line.startsWith("| ") || line.includes("---")) continue;

    const cells = line.split("|").map((cell) => cell.trim());
    const remote = cells.at(-2);
    if (!remote || remote === "Remote" || remote === "none") continue;

    const slug = repoSlugFromRemote(remote);
    if (slug) remotes.add(slug);
  }

  return remotes;
}

function validateSyncConfig() {
  const syncPath = ".github/agent-policy-sync.yml";
  if (!existsSync(syncPath)) return;

  const sync = read(syncPath);
  const sources = captureList(sync, /^\s+- source: (.+)$/gm);
  const targets = sync
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("kulikman/"));
  const remotes = inventoryRemotes();

  for (const source of sources) {
    assertExists(source, "agent-policy-sync source");
  }

  if (remotes.size === 0) return;

  for (const target of targets) {
    if (!remotes.has(target)) {
      addError(`agent-policy-sync target is not present in inventory remotes: ${target}`);
    }
  }
}

validateVersion();
validateManifestPaths();
validatePolicyPacks();
validateProjectProfiles();
validateSkillRequirements();
validateSyncConfig();

if (errors.length > 0) {
  console.error("Agent policy check failed:");
  for (const error of errors) console.error(`- ${error}`);
  if (warnings.length > 0) {
    console.error("Warnings:");
    for (const warning of warnings) console.error(`- ${warning}`);
  }
  process.exit(1);
}

if (warnings.length > 0) {
  console.warn("Agent policy check warnings:");
  for (const warning of warnings) console.warn(`- ${warning}`);
}

console.log("Agent policy check passed");
