---
name: verification
description: Use before claiming work is complete, fixed, passing, ready to commit, or ready to push.
---

# Verification

Act as a strict verification engineer.

Core rule: evidence before claims.

Do not say work is complete, fixed, passing, ready, shipped or safe until you
have fresh verification evidence from this session.

## When To Use

Use this skill before:

- reporting a task as complete;
- committing or preparing a PR;
- pushing or shipping;
- saying tests, lint, typecheck or build pass;
- saying a bug is fixed;
- saying requirements are met.

## Workflow

1. Restate the claim that needs evidence.
2. Identify the smallest command or inspection that proves or disproves it.
3. Run the full command, not a partial substitute.
4. Read the output and exit code.
5. Compare evidence against the original request and touched files.
6. Report only what the evidence supports.

## Required Checks

Use the checks already available in the project.

For this repository, prefer:

```bash
pnpm check
pnpm verify
pnpm build
```

Use `pnpm build` for release-sensitive changes. Use focused tests first when
debugging, then run the broader verification suite.

## Anti-Hallucination Gate

Before reporting success, verify that you did not invent:

- commands not present in `package.json`;
- routes not present in `src/app` or documented route files;
- environment variables not present in documented configuration;
- database tables, columns, policies or migrations;
- completed work that is not visible in the diff;
- framework behavior that contradicts the installed version.

## Output

```markdown
## Verification

### Claim Checked
- claim

### Evidence
- command or file inspection: result

### Result
- supported / not supported

### Remaining Risk
- risk or none
```
