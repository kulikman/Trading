# Stack: Next.js 15

id: stack/next15
version: 1.0.0
compatible_with:

- react19
- tailwind4

## Rules

- This stack is Next.js 15, not Next.js 16.
- Do not automatically migrate to Next.js 16 conventions.
- If the project uses `src/middleware.ts`, keep it.
- Do not rename `middleware.ts` to `proxy.ts` unless the project is explicitly upgraded to Next.js 16.
- `params`, `searchParams`, `cookies()` and `headers()` may be async depending on the exact project version; follow the local project rules.
- Tailwind v4 theme usually lives in `src/app/globals.css` under `@theme`.

## Checks

Preferred checks:

```bash
pnpm check
pnpm test
pnpm build
pnpm knip
```

Use only commands that exist in the project.

## Conflicts

- Conflicts with `stack/next16` proxy-only rule.
- Conflicts with Flutter-only repositories.
- Conflicts with Hono-only backend repositories.
