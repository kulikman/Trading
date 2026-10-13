# Project Documentation

This `/docs` folder is the **single source of truth** for your project.
Fill it in when starting a new project. Keep it updated as the project evolves.

**AI agents (Claude Code, Cursor, Copilot) should read this folder before writing any code.**

---

## Files

| File | Purpose | Fill in when |
|---|---|---|
| `00_PROJECT_OVERVIEW.md` | Project name, type, stage, links | Day 1 |
| `01_PRODUCT_BRIEF.md` | Problem, solution, UVP, metrics | Day 1 |
| `02_MVP_SCOPE.md` | What's in/out of scope, release criteria | Day 1 |
| `03_USER_ROLES.md` | Roles, permissions, RLS patterns | Day 1 |
| `04_ARCHITECTURE.md` | System design, folder structure, critical flows | Day 1 (pre-filled for this stack) |
| `05_DATABASE_SCHEMA.md` | Tables, fields, indexes, RLS policies | As tables are created |
| `06_API_CONTRACTS.md` | Route Handlers, Server Actions, webhooks | As endpoints are added |
| `07_EPICS.md` | Feature epics with status | Sprint planning |
| `08_BACKLOG.md` | Task list with IDs and priorities | Ongoing |
| `09_CURRENT_STATUS.md` | Live project status — updated after every task | After every task |
| `12_TEST_PLAN.md` | Test flows, unit test checklist | Before MVP launch |
| `13_SECURITY_CHECKLIST.md` | Security audit checklist | Before production deploy |
| `14_CHANGELOG.md` | Product-level changelog | After each release |
| `15_DECISIONS_LOG.md` | Architectural decision records | When a meaningful choice is made |
| `17_AGENT_POLICY_SOURCE.md` | Canonical Solo Founder Agent OS policy source | When agent rules or policy packs change |
| `18_AGENT_REPO_INVENTORY.md` | Generated local repository policy inventory | After scanning local repositories |
| `19_AGENT_POLICY_SYNC.md` | Manual PR-only policy sync workflow | Before syncing policy to other repositories |
| `20_AGENT_POLICY_VALIDATION.md` | Agent policy anti-hallucination checks | When policy validation changes |
| `21_AGENT_POLICY_STATUS.md` | Generated policy rollout dashboard | After inventory or sync target changes |
| `22_DEPENDENCY_AUTOMATION.md` | Renovate dependency update policy | When dependency automation changes |
| `23_AGENT_POLICY_ROLLOUT.md` | Review and rollout protocol for policy sync PRs | Before merging sync PRs |
| `24_TEMPLATE_UPGRADE_SYSTEM.md` | Future Copier/Cruft template update strategy | Before adopting template-managed updates |
| `25_ROUTE_CONTRACT.md` | Canonical URL, breadcrumb, redirect, and sitemap rules | Before adding nested or SEO-sensitive routes |

---

## Recommended First Prompt (new session)

```text
Read all files in /docs.

Do not write code yet.

Analyze the project documentation and tell me:
1. What the project is
2. What is the MVP scope
3. What is the current status (from 09_CURRENT_STATUS.md)
4. What the next task should be (from 08_BACKLOG.md)
5. What risks you see
```

## Workflow

1. Start session → read `09_CURRENT_STATUS.md` + `08_BACKLOG.md`
2. Pick one task → implement it
3. After completion → update `09_CURRENT_STATUS.md`
4. Commit with Conventional Commits message
5. Update `14_CHANGELOG.md` if user-visible change

See `.claude/prompts.md` for structured prompts for each scenario.
