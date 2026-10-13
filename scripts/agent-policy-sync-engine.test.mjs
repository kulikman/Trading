import { describe, expect, it } from "vitest";
import {
  parsePorcelainPath,
  parseSyncConfigText,
  selectRepos,
  validateFileMappings,
} from "./agent-policy-sync-engine.mjs";

describe("agent policy sync engine", () => {
  it("parses repositories and file mappings from sync config", () => {
    const config = parseSyncConfigText(`
group:
  - repos: |
      kulikman/one
      kulikman/two
    files:
      - source: .agent-policy-version
        dest: .agent-policy-version
      - source: solo-founder-os/core/
        dest: solo-founder-os/core/
`);

    expect(config.repos).toEqual(["kulikman/one", "kulikman/two"]);
    expect(config.files).toEqual([
      { source: ".agent-policy-version", dest: ".agent-policy-version" },
      { source: "solo-founder-os/core/", dest: "solo-founder-os/core/" },
    ]);
  });

  it("rejects live agent and workflow destinations", () => {
    const errors = validateFileMappings([
      { source: "solo-founder-os/templates/AGENTS.md.tpl", dest: "AGENTS.md" },
      { source: "solo-founder-os/templates/CLAUDE.md.tpl", dest: "CLAUDE.md" },
      { source: "solo-founder-os/templates/check.md", dest: ".claude/commands/check.md" },
      { source: "solo-founder-os/templates/workflow.yml", dest: ".github/workflows/sync.yml" },
    ]);

    expect(errors).toEqual([
      "refusing to sync live agent/workflow path: AGENTS.md",
      "refusing to sync live agent/workflow path: CLAUDE.md",
      "refusing to sync live agent/workflow path: .claude/commands/check.md",
      "refusing to sync live agent/workflow path: .github/workflows/sync.yml",
    ]);
  });

  it("rejects absolute and parent traversal paths", () => {
    expect(validateFileMappings([{ source: "../outside", dest: "/tmp/outside" }])).toEqual([
      "unsafe source path: ../outside",
      "unsafe dest path: /tmp/outside",
    ]);
  });

  it("selects explicit repositories before applying limit", () => {
    const repos = ["kulikman/one", "kulikman/two", "kulikman/three"];

    expect(selectRepos(repos, { limit: 1, repos: ["kulikman/two"] })).toEqual(["kulikman/two"]);
    expect(selectRepos(repos, { limit: 2, repos: [] })).toEqual(["kulikman/one", "kulikman/two"]);
  });

  it("parses git porcelain paths without dropping path characters", () => {
    expect(parsePorcelainPath(" M solo-founder-os/core/security.md")).toBe(
      "solo-founder-os/core/security.md"
    );
    expect(parsePorcelainPath("D solo-founder-os/project-profiles/old.yml")).toBe(
      "solo-founder-os/project-profiles/old.yml"
    );
    expect(parsePorcelainPath("?? solo-founder-os/skills/release.yml")).toBe(
      "solo-founder-os/skills/release.yml"
    );
    expect(parsePorcelainPath("R  old/path.yml -> solo-founder-os/project-profiles/new.yml")).toBe(
      "solo-founder-os/project-profiles/new.yml"
    );
  });
});
