# Stack: Hono + MCP

id: stack/hono-mcp
version: 1.0.0

## Rules

- This is a backend/platform stack, not Next.js or React.
- Preserve API, SDK, CLI and MCP contracts.
- Do not invent routes, MCP tools, schemas, migrations, env vars, AI providers, embedding dimensions or database tables.
- Keep shared contracts as the source of truth when API and MCP expose the same behavior.
- Do not use Supabase Auth/Storage assumptions unless the project explicitly uses them.
- Use UUIDs when the project requires UUID identity.

## Checks

Preferred checks:

```bash
pnpm verify
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Use only commands that exist in the project.

## Conflicts

- Conflicts with Next.js page/app router assumptions.
- Conflicts with Flutter rules.
