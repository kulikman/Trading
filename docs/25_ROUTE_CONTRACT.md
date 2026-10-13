# Route Contract And Breadcrumbs

`src/config/routes.ts` is the canonical source for project URLs, route labels,
page titles, aliases, and sitemap visibility.

## Pre-Refactor URL Audit

| Current URL | Current Breadcrumb | Problems Found | Recommended URL | Recommended Breadcrumb |
| --- | --- | --- | --- | --- |
| `/` | none | OK public landing page | `/` | none |
| `/pricing` | none | OK public first-level page | `/pricing` | none |
| `/dashboard` | none | OK protected app root | `/dashboard` | none |
| `/settings` | previously hidden | Settings layout should expose hierarchy | `/settings` | Dashboard > Settings |
| `/settings/billing` | previously hidden | Breadcrumb hidden by old `/settings*` rule | `/settings/billing` | Dashboard > Settings > Billing |
| `/settings/usage` | previously hidden | Breadcrumb hidden by old `/settings*` rule | `/settings/usage` | Dashboard > Settings > Usage |
| `/settings/api-keys` | previously hidden | Breadcrumb hidden by old `/settings*` rule | `/settings/api-keys` | Dashboard > Settings > API Keys |
| `/settings/org` | Dashboard > Settings > Org fallback risk | Abbreviation is technical and less readable | `/settings/organization` | Dashboard > Settings > Organization |

## URL Rules

- Use semantic nouns: `/settings/organization`, not `/settings/org`.
- Public SEO pages must use human-readable slugs, not opaque IDs.
- Protected internal detail pages may use IDs, but breadcrumbs must resolve IDs
  to user-facing names.
- New navigation links should use `ROUTES` or `routes`, not raw string hrefs.
- Changed URLs need aliases in `src/config/routes.ts` and redirects in
  `next.config.ts`.

## Implemented Redirects

| Source | Destination | Status |
| --- | --- | --- |
| `/settings/org` | `/settings/organization` | 301 |

## Final URL Map

| Route | Purpose | Sitemap |
| --- | --- | --- |
| `/` | Public landing page | yes |
| `/pricing` | Public pricing page | yes |
| `/login` | Auth sign-in | no |
| `/signup` | Auth sign-up | no |
| `/forgot-password` | Password reset request | no |
| `/reset-password` | Password reset form | no |
| `/dashboard` | Protected app root | no |
| `/onboarding` | Protected onboarding flow | no |
| `/settings` | Protected settings root | no |
| `/settings/billing` | Billing settings | no |
| `/settings/usage` | Usage settings | no |
| `/settings/api-keys` | API key management | no |
| `/settings/organization` | Organization management | no |

## Final Breadcrumb Map

| URL | Breadcrumb |
| --- | --- |
| `/settings` | Dashboard > Settings |
| `/settings/billing` | Dashboard > Settings > Billing |
| `/settings/usage` | Dashboard > Settings > Usage |
| `/settings/api-keys` | Dashboard > Settings > API Keys |
| `/settings/organization` | Dashboard > Settings > Organization |

## Validation

- `src/lib/navigation/routes.test.ts` guards duplicate canonical URLs.
- Route labels and titles are required for every registered route.
- Aliases must map to canonical paths.
- Sitemap routes are generated from the route contract.
- Breadcrumb UI emits Schema.org `BreadcrumbList` JSON-LD when a base URL is
  provided by the server layout.
