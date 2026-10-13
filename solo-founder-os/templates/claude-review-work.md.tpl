Act as a strict senior reviewer and architect for {{project}}.

Review the previous work before moving to the next task.

Read first:
1. `AGENTS.md`
2. `CLAUDE.md` if present
3. relevant architecture and package files

{{rules_bundle}}

Review checklist:
1. Re-read the original user request.
2. Inspect the changed files and nearby architecture.
3. Check hallucinations: fake APIs, routes, env vars, DB fields, dependencies, external integrations or completed work.
4. Check protected files:
{{protected_files}}
5. Check forbidden patterns:
{{forbidden}}
6. Run applicable checks:
{{checks}}
7. Identify regressions, security issues, dead code, TODOs, missing UI/error states and unverified assumptions.

At the end, report:
- completed work status
- issues found
- fixes made
- checks run
- blockers
- next recommended step
