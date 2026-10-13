---
description: Safe AI coding workflow for {{project}}
alwaysApply: true
---

You are working in `{{repo}}`.

Read first:
1. `AGENTS.md`
2. `CLAUDE.md` if present
3. relevant architecture, package and project docs

{{rules_bundle}}

Before changing code:
- inspect nearby files
- preserve existing architecture
- do not invent files, APIs, dependencies or environment variables
- avoid placeholder logic unless explicitly requested
- respect protected files and forbidden patterns

Before git operations:
- inspect `git status` and the diff
- stage only intentional files
- run applicable checks
- keep secrets and generated junk out of git
- push only when explicitly requested

Protected files:
{{protected_files}}

Forbidden patterns:
{{forbidden}}

Checks:
{{checks}}

Never claim something works unless it was checked.
