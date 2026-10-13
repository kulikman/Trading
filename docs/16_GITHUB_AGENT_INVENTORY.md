# GitHub Agent Inventory

Updated: 2026-06-19

Scope: public repositories under `https://github.com/kulikman`

Source of truth for this inventory:

- GitHub profile repositories page
- GitHub public repository metadata API
- GitHub public repository tree API

## Summary

At the time of this audit, the `kulikman` profile exposes 5 public repositories:

1. `elaurion-finance`
2. `neosim-web`
3. `open-design-kit`
4. `Secret-project`
5. `Template-Projects`

Coverage status:

- 4 repositories already have a strong agent-tooling layer:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `.claude/*`
  - `.cursor/*`
- 0 repositories have a dedicated `.codex/` directory
- 1 repository (`open-design-kit`) currently has none of these agent artifacts

Important note:

- Codex-specific repo configuration is currently represented mainly through `AGENTS.md`
- no public repo in this inventory has a standalone `.codex/` folder

## Matrix

| Repo | Updated (UTC) | Main language | `AGENTS.md` | `CLAUDE.md` | Claude commands | Claude agents | Claude rules | Claude memory files | Claude skills | Cursor commands | Cursor rules | `.codex/` |
|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `elaurion-finance` | 2026-06-17 21:01 | TypeScript | yes | yes | 9 | 7 | 8 | 9 | 3 | 3 | 2 | no |
| `neosim-web` | 2026-06-17 19:53 | HTML | yes | yes | 10 | 6 | 8 | 7 | 3 | 3 | 1 | no |
| `open-design-kit` | 2026-05-18 09:28 | none | no | no | 0 | 0 | 0 | 0 | 0 | 0 | 0 | no |
| `Secret-project` | 2026-06-19 16:09 | TypeScript | yes | yes | 9 | 7 | 8 | 9 | 3 | 3 | 2 | no |
| `Template-Projects` | 2026-06-19 16:05 | TypeScript | yes | yes | 5 | 7 | 8 | 9 | 3 | 3 | 1 | no |

## Repository Details

### `elaurion-finance`

Repo: <https://github.com/kulikman/elaurion-finance>

Present:

- `AGENTS.md`
- `CLAUDE.md`
- `.claude/SKILLS.md`
- `.claude/agents/README.md`
- `.claude/agents/{architect,coder,orchestrator,reviewer,security,tester}.md`
- `.claude/commands/{agent,audit,check,commit,deploy-check,fix-issue,review,ship,test}.md`
- `.claude/instincts.md`
- `.claude/memory/{context,decisions,integration-map,known-issues,mistakes,patterns,product-decisions,project-state,quick-recipes}.md`
- `.claude/rules/{architecture,business-context,code-style,data-patterns,email,performance,security,testing}.md`
- `.claude/settings.json`
- `.claude/skills/{architect,memory,review}/SKILL.md`
- `.cursor/commands/{fix-all-critical,run-audit,show-rules}.md`
- `.cursor/rules/{agent-workflow,architecture}.mdc`

Notes:

- strongest public parity with `Secret-project`
- has both `agent-workflow.mdc` and `architecture.mdc` for Cursor
- no standalone `.codex/`

### `neosim-web`

Repo: <https://github.com/kulikman/neosim-web>

Present:

- `AGENTS.md`
- `CLAUDE.md`
- `.claude/SKILLS.md`
- `.claude/agents/{architect,coder,orchestrator,reviewer,security,tester}.md`
- `.claude/commands/{agent,audit,check,commit,deploy-check,fix-issue,qa-agent,review,ship,test}.md`
- `.claude/instincts.md`
- `.claude/launch.json`
- `.claude/memory/{decisions,integration-map,known-issues,mistakes,patterns,project-state,quick-recipes}.md`
- `.claude/rules/{architecture,business-context,code-style,data-patterns,email,performance,security,testing}.md`
- `.claude/settings.local.json`
- `.claude/skills/{architect,memory,review}/SKILL.md`
- `.cursor/commands/{fix-all-critical,run-audit,show-rules}.md`
- `.cursor/rules/agent-workflow.mdc`

Notes:

- the only public repo with `.claude/commands/qa-agent.md`
- lighter Claude layer than `elaurion-finance` and `Secret-project`
- no `.claude/prompts.md`
- no `.claude/settings.json`
- only 1 Cursor rule
- no standalone `.codex/`

### `open-design-kit`

Repo: <https://github.com/kulikman/open-design-kit>

Present:

- none of the audited agent artifacts were found:
  - no `AGENTS.md`
  - no `CLAUDE.md`
  - no `.claude/`
  - no `.cursor/`
  - no `.codex/`

Notes:

- this repo is the clearest gap in the portfolio
- if you want consistent agent behavior across all repos, this is the first repo to bootstrap

### `Secret-project`

Repo: <https://github.com/kulikman/Secret-project>

Present:

- `AGENTS.md`
- `CLAUDE.md`
- `.claude/SKILLS.md`
- `.claude/agents/README.md`
- `.claude/agents/{architect,coder,orchestrator,reviewer,security,tester}.md`
- `.claude/commands/{agent,audit,check,commit,deploy-check,fix-issue,review,ship,test}.md`
- `.claude/instincts.md`
- `.claude/memory/{context,decisions,integration-map,known-issues,mistakes,patterns,product-decisions,project-state,quick-recipes}.md`
- `.claude/prompts.md`
- `.claude/rules/{architecture,business-context,code-style,data-patterns,email,performance,security,testing}.md`
- `.claude/settings.json`
- `.claude/skills/{architect,memory,review}/SKILL.md`
- `.cursor/commands/{fix-all-critical,run-audit,show-rules}.md`
- `.cursor/rules/{agent-workflow,architecture}.mdc`

Notes:

- one of the two most complete public setups
- good candidate as a reference repo for Claude/Cursor standardization
- no standalone `.codex/`

### `Template-Projects`

Repo: <https://github.com/kulikman/Template-Projects>

Present:

- `AGENTS.md`
- `CLAUDE.md`
- `.claude/SKILLS.md`
- `.claude/agents/README.md`
- `.claude/agents/{architect,coder,orchestrator,reviewer,security,tester}.md`
- `.claude/commands/{agent,deploy-check,fix-issue,review,test}.md`
- `.claude/instincts.md`
- `.claude/memory/{context,decisions,integration-map,known-issues,mistakes,patterns,product-decisions,project-state,quick-recipes}.md`
- `.claude/prompts.md`
- `.claude/rules/{architecture,business-context,code-style,data-patterns,email,performance,security,testing}.md`
- `.claude/settings.json`
- `.claude/settings.local.json`
- `.claude/skills/{architect,memory,review}/SKILL.md`
- `.cursor/commands/{fix-all-critical,run-audit,show-rules}.md`
- `.cursor/rules/architecture.mdc`

Notes:

- template repo is intentionally narrower in commands than `Secret-project`
- only 1 Cursor rule at the moment
- likely the best place to define your future cross-repo standard
- no standalone `.codex/`

## Cross-Repo Patterns

### Present in all 4 configured repos

- `AGENTS.md`
- `CLAUDE.md`
- `.claude/SKILLS.md`
- `.claude/skills/{architect,memory,review}/SKILL.md`
- `.claude/rules` set with 8 rule files
- `.cursor/commands/{fix-all-critical,run-audit,show-rules}.md`

### Not present in any public repo

- `.codex/` directory
- dedicated Codex-local rules/instructions folder

### Most complete public setups

- `Secret-project`
- `elaurion-finance`

### Partial but strong setups

- `Template-Projects`
- `neosim-web`

### Main gap

- `open-design-kit`

## Recommended Next Moves

1. Decide whether `AGENTS.md` alone is enough for Codex, or whether you want a real `.codex/` layer across repos.
2. Pick one reference standard:
   - `Secret-project` if you want the richest current setup
   - `Template-Projects` if you want a clean template-first standard
3. Bootstrap `open-design-kit` with at least:
   - `AGENTS.md`
   - `CLAUDE.md`
   - `.claude/rules/*`
   - `.cursor/commands/*`
4. Normalize Cursor rules:
   - `agent-workflow.mdc`
   - `architecture.mdc`
5. Normalize Claude commands across repos if you want one shared operational surface.

## Follow-Up Applied In Template-Projects

After this inventory, `Template-Projects` was upgraded with the most reusable
cross-repo operational layer:

- Claude commands added:
  - `.claude/commands/audit.md`
  - `.claude/commands/check.md`
  - `.claude/commands/commit.md`
  - `.claude/commands/ship.md`
- Claude skills added:
  - `.claude/skills/supabase-architect/SKILL.md`
  - `.claude/skills/security-hardening/SKILL.md`
  - `.claude/skills/github-workflow/SKILL.md`
  - `.claude/skills/premium-animated-ui/SKILL.md`
- Cursor rule added:
  - `.cursor/rules/agent-workflow.mdc`

These were chosen because they are the most template-safe and reusable across
multiple product repositories without pulling in narrow domain assumptions.

## Source Links

- GitHub profile: <https://github.com/kulikman?tab=repositories>
- `elaurion-finance`: <https://github.com/kulikman/elaurion-finance>
- `neosim-web`: <https://github.com/kulikman/neosim-web>
- `open-design-kit`: <https://github.com/kulikman/open-design-kit>
- `Secret-project`: <https://github.com/kulikman/Secret-project>
- `Template-Projects`: <https://github.com/kulikman/Template-Projects>
