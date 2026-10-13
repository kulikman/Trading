# Stack: Next.js 16

id: stack/next16
version: 1.0.0
compatible_with:

- react19
- tailwind4

## Rules

- This stack is Next.js 16, not Next.js 14/15.
- `params` and `searchParams` are async; await them.
- `cookies()`, `headers()` and `draftMode()` are async.
- Use `src/proxy.ts` for request interception.
- Do not create old `middleware.ts` patterns.
- Tailwind v4 theme lives in `src/app/globals.css` under `@theme`.
- Do not add `tailwind.config.ts` unless the repository explicitly requires it.
- Caching is opt-in; use explicit cache directives.
- Use `remotePatterns` for images; do not use removed `domains` config.

## Checks

Preferred checks:

```bash
pnpm check
pnpm verify
pnpm build
pnpm knip
```

Use only commands that exist in the project.

## Conflicts

- Conflicts with `stack/next15` if that project requires `src/middleware.ts`.
- Conflicts with Flutter-only repositories.
- Conflicts with Hono-only backend repositories.
