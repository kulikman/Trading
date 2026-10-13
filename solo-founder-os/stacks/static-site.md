# Stack: Static Site

id: stack/static-site
version: 1.0.0

## Rules

- This is a static site, not an app framework project.
- Do not add Next.js, Vite, React build tooling, a bundler or new framework unless explicitly requested.
- Preserve static HTML/CSS/JS architecture.
- Keep changes lightweight and marketing-focused when the site is a landing or personal-brand site.
- Do not invent build steps, routes, APIs or dependencies.

## Checks

Preferred checks:

```bash
pnpm check
pnpm format:check
```

Use only commands that exist in the project.

## Conflicts

- Conflicts with Next.js app-router rules.
- Conflicts with backend-only rules.
