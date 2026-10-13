# Agent Policy Status

Generated: 2026-06-26T16:33:47.446Z

Source inventory: `docs/18_AGENT_REPO_INVENTORY.md`

## Summary

- Local repositories in inventory: 23
- Active sync targets: 19
- Excluded local repositories: 4
- Missing policy version marker: 19
- Repositories with dirty working tree: 4
- Missing AGENTS.md: 3
- Missing CLAUDE.md: 7
- Missing Cursor rules: 3

## Active Sync Targets

| Repo | Remote | Stack signals | Policy | Dirty |
| --- | --- | --- | --- | --- |
| 2Skymobile-CRM | kulikman/2Skymobile-CRM | Next.js 16.2.6, React, Supabase, Supabase local | missing | 0 |
| 2SkyMobile-Partner | kulikman/2SkyMobile-Partner | Next.js ^16.2.6, React, Supabase, Supabase local | missing | 0 |
| 2Skymobile-web | kulikman/2Skymobile-web | Next.js 16.2.6, React, Supabase, Supabase local | missing | 0 |
| 2SkyVC | kulikman/sky-ventures | React, Vite, Supabase, Supabase local | missing | 0 |
| Elaurion-Brain | kulikman/elaurion_brain | Hono, MCP, verify script | missing | 0 |
| Elaurion-Options | kulikman/Elaurion-Options | Next.js 16.2.6, React, Vite, Docker, Supabase local, verify script | missing | 0 |
| Elliott-wave | kulikman/Elliott-wave | unknown | missing | 12 |
| Elurion-finance | kulikman/elaurion-finance | Next.js 16.2.6, React, Supabase, Stripe, Docker, Supabase local, verify script | missing | 0 |
| Founder-OS | kulikman/Founder-OS | Next.js 15.5.18, React, MCP, Supabase, Stripe, Supabase local | missing | 1 |
| Kulikov-world | kulikman/kulikov-world | unknown | current (1.0.0) | 0 |
| My-Alfred | kulikman/my-alfred | Next.js 16.2.7, React, Supabase, Docker | missing | 0 |
| Neo Map | kulikman/neo-map | Next.js 16.2.4, React | missing | 0 |
| neosim-admin | kulikman/neosim-admin | Next.js 16.2.6, React, Supabase, Supabase local | missing | 1 |
| neosim-backend | kulikman/neosim-backend | unknown | missing | 0 |
| neosim-mobile | kulikman/neosim-mobile | Flutter/Dart | current (1.0.0) | 0 |
| neosim-web | kulikman/neosim-web | Next.js 16.2.6, React, Supabase, verify script | missing | 1 |
| Secret-project | kulikman/Secret-project | Next.js 16.2.6, React, Supabase, Docker, Supabase local, verify script | missing | 0 |
| Open-design-kit | kulikman/open-design-kit | unknown | current (1.0.0) | 0 |
| Theta Aurion | kulikman/theta-aurion | Next.js 16.2.6, React, Supabase, Stripe, Docker, Supabase local, verify script | missing | 0 |

## Attention Needed

| Repo | Path | Policy | Dirty | AGENTS | CLAUDE | Cursor rules |
| --- | --- | --- | --- | --- | --- | --- |
| Elliott-wave | Elliott-wave | missing | 12 | yes | yes | 1 |
| Founder-OS | Founder-OS | missing | 1 | yes | yes | 3 |
| neosim-admin | Neosim/neosim-admin | missing | 1 | yes | yes | 1 |
| neosim-web | Neosim/neosim-web | missing | 1 | yes | yes | 1 |
| 2Skymobile-CRM | 2Skymobile-CRM | missing | 0 | yes | yes | 3 |
| 2SkyMobile-Partner | 2SkyMobile-Partner | missing | 0 | yes | yes | 1 |
| 2Skymobile-web | 2Skymobile-web | missing | 0 | yes | yes | 2 |
| 2SkyVC | 2SkyVC | missing | 0 | yes | no | 1 |
| Elaurion-Brain | Elaurion-Brain | missing | 0 | yes | yes | 2 |
| Elaurion-Options | Elaurion-Options | missing | 0 | yes | yes | 2 |
| Elurion-finance | Elurion-finance | missing | 0 | yes | yes | 2 |
| My-Alfred | My-Alfred | missing | 0 | yes | yes | 1 |
| Neo Map | Neosim/Neo Map | missing | 0 | yes | yes | 1 |
| neosim-backend | Neosim/neosim-backend | missing | 0 | yes | no | 1 |
| Secret-project | Secret-project | missing | 0 | yes | yes | 2 |
| Theta Aurion | Theta Aurion | missing | 0 | yes | yes | 2 |
| 2SkyCRM | Архив/2SkyCRM | missing | 0 | no | no | 0 |
| polymarket-edge | Архив/Polymarket/polymarket-edge | missing | 0 | no | yes | 0 |
| Chip | Разное/KAHURA/Chip | missing | 0 | no | no | 0 |
| Kulikov-world | Kulikov-world | current (1.0.0) | 0 | yes | no | 2 |
| neosim-mobile | Neosim/neosim-mobile | current (1.0.0) | 0 | yes | no | 1 |
| Open-design-kit | TEMLATES/Open-design-kit | current (1.0.0) | 0 | yes | no | 1 |

## Excluded Local Repositories

| Repo | Path | Remote | Stack signals |
| --- | --- | --- | --- |
| Template-Projects | TEMLATES/Template-Projects | https://github.com/kulikman/Template-Projects.git | Next.js 16.2.6, React, Supabase, Stripe, Docker, Supabase local, verify script |
| 2SkyCRM | Архив/2SkyCRM | https://github.com/kulikman/crm-2skymobile.git | React, Vite, Supabase, Supabase local |
| polymarket-edge | Архив/Polymarket/polymarket-edge | https://github.com/kulikman/polymarket-edge.git | Next.js 15.3.1, React, Docker |
| Chip | Разное/KAHURA/Chip | none | unknown |

## Next Actions

1. Review dirty repositories before applying sync PRs.
2. Run the manual sync workflow in dry-run mode first.
3. Merge policy marker PRs only after target repo checks pass.
4. Add generated-block merge support before syncing live `AGENTS.md`, `CLAUDE.md`, `.claude/` or `.cursor/` files.
