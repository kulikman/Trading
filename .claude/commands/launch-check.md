Act as a launch readiness reviewer for a solo-founder SaaS project.

Do not commit. Do not push.

Before checking:

1. Read `AGENTS.md`
2. Read `CLAUDE.md`
3. Read `package.json`
4. Read `docs/09_CURRENT_STATUS.md`
5. Inspect relevant deployment, auth, payment, email, SEO, and analytics files

Check:

- `pnpm check`
- `pnpm verify`
- `pnpm build`
- required environment variables are documented and validated
- auth flows are protected
- Stripe/webhook flows verify signatures if enabled
- email sending uses verified sender config if enabled
- sitemap, robots, metadata, and `llms.txt` are present when relevant
- analytics and error reporting are configured or explicitly deferred
- error, not-found, loading, and security headers exist
- no secrets or `.env*` files are staged

Output:

```
## Launch Check

### Ready
- item

### Blockers
- item and fix

### Warnings
- item and follow-up

### Checks Run
- command: result

### Verdict
Ready / Not ready
```
