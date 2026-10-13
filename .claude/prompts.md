# AI Prompt Library

Structured prompts for standard development scenarios.
Copy the relevant prompt into your Claude Code session.

---

## 1. Start New Session

```text
Read the following files before doing anything:
- docs/09_CURRENT_STATUS.md
- docs/08_BACKLOG.md
- CLAUDE.md

Do not write code yet.

Tell me:
1. Current project status
2. What was last completed
3. What the next recommended task is
4. Any blockers or risks you notice
```

---

## 2. Start New Project (from template)

```text
You are a senior full-stack architect.

I am building a new product using this Next.js SaaS template.

Read:
- docs/00_PROJECT_OVERVIEW.md (fill this in first)
- CLAUDE.md

My product:
[DESCRIBE YOUR PRODUCT IN 2-3 SENTENCES]

Your task:
1. Help me fill in docs/01_PRODUCT_BRIEF.md
2. Help me fill in docs/02_MVP_SCOPE.md
3. Propose the first 5 backlog tasks for docs/08_BACKLOG.md
4. Identify what template features I need to configure first

Do not write code. Output the filled doc sections.
```

---

## 3. Implement One Task

```text
You are a senior developer working in this repository.

Before coding, read:
- docs/09_CURRENT_STATUS.md
- docs/08_BACKLOG.md
- docs/04_ARCHITECTURE.md
- CLAUDE.md

Task to implement:
[TASK ID AND DESCRIPTION — e.g., "TASK-005: Add user profile edit form"]

Rules:
- Implement only this task
- Do not change unrelated files
- Do not add libraries without stating why in the commit message
- Do not change architecture without explaining why
- After implementation, explain how to test it

First, show your implementation plan (files to change, approach, risks).
Wait for my confirmation before writing code.
```

---

## 4. Code Review

```text
You are a strict senior code reviewer.

Review the recent changes (run `git diff main` to see them).

Check:
1. Does the code match the task in docs/08_BACKLOG.md?
2. TypeScript: no `any`, no `@ts-ignore`, explicit return types?
3. Security: auth checked, inputs validated with Zod, no secrets?
4. Supabase: `getUser()` not `getSession()`, RLS policies written?
5. Performance: no request waterfalls, parallel fetches where possible?
6. React: Server Components by default, `"use client"` justified?
7. Error handling: no silent catches?
8. Tests: are new utilities tested?
9. Naming: follows conventions in CLAUDE.md?
10. Breadcrumbs: present on nested routes?

Output:
- Summary (1-2 sentences)
- Critical issues (must fix before merge)
- Important issues (should fix)
- Minor issues (nice to fix)
- Final verdict: ✅ approve / ⚠️ approve with changes / ❌ reject
```

---

## 5. Bug Fix

```text
You are a senior debugging engineer.

Bug:
[DESCRIBE THE BUG — what happens, what should happen]

Error (paste if available):
[ERROR MESSAGE / STACK TRACE]

Steps to reproduce:
1. [step]
2. [step]

Rules:
- Find the root cause first — do not patch symptoms
- Do not rewrite unrelated code
- Propose the minimal safe fix
- Add a test if possible

Output:
1. Root cause
2. Fix plan (files to change, approach)
3. Risks of the fix
4. How to verify the fix works
```

---

## 6. Refactor

```text
You are a senior refactoring engineer.

Target: [FILE OR FEATURE TO REFACTOR]

Goal: improve readability, structure, or maintainability — without changing behavior.

Rules:
- Do not change product behavior
- Do not change API contracts (docs/06_API_CONTRACTS.md)
- Do not change database schema
- Do not remove features
- Keep changes small and reviewable

Before touching code, output:
1. Problems found
2. Refactoring plan
3. Files that will change
4. How to verify behavior stays the same
```

---

## 7. Security Audit

```text
You are a security reviewer.

Audit this project (or the specified module: [MODULE]) for:

Authentication:
- Is auth checked on every protected Server Action and Route Handler?
- Is `getUser()` used (not `getSession()`)?

Authorization:
- Does every table have RLS enabled?
- Can users access other users' data?

Input validation:
- Is every external input validated with Zod?
- Are IDs sanitized in DB queries?

Secrets:
- Are there any hardcoded secrets or API keys?
- Is `service_role` client imported from client-side code?

Payments:
- Is the Stripe webhook signature verified?
- Is payment status derived from webhooks, not client payloads?

Output:
- Critical vulnerabilities (fix immediately)
- High risk (fix before next deploy)
- Medium risk (fix within sprint)
- Low risk (track as backlog item)
- Recommended fixes in priority order
```

---

## 8. Update Project Memory

```text
Update docs/09_CURRENT_STATUS.md based on the current state of the codebase.

Do not invent progress. Only write what is confirmed from actual files.

Include:
- What was recently completed (check git log)
- What is currently in progress
- Any blockers
- The next recommended task
- Any areas that should not be touched

Then verify docs/08_BACKLOG.md task statuses are accurate.
```

---

## 9. Add New Feature (full flow)

```text
You are a senior full-stack developer.

I want to add: [FEATURE DESCRIPTION]

Read:
- docs/04_ARCHITECTURE.md
- docs/05_DATABASE_SCHEMA.md
- docs/06_API_CONTRACTS.md
- CLAUDE.md

Plan the full implementation:
1. Database changes needed (new tables? new columns? migrations?)
2. Server Actions or Route Handlers to add
3. UI components and pages
4. Tests to write
5. Docs to update (05, 06, 07, 08)
6. Feature flag needed? (check src/lib/env.ts pattern)

Do not write code yet. Output the plan. I will confirm before you start.
```
