/**
 * Static site metadata. Build-time only — anything user-tunable belongs
 * in env vars consumed via `getServerEnv()` / `getClientEnv()`.
 *
 * `siteConfig.url` is just a fallback for build-time `metadataBase` and
 * deterministic OG image URLs in tests; runtime origin should be read
 * from `getClientEnv().NEXT_PUBLIC_APP_URL`.
 *
 * `nav[].href` is intentionally `string`. `<Link href={...}>` consumers
 * widen it to `Route` automatically (Next 16 typed routes are enabled
 * in `next.config.ts`), so a typo in a path will fail `tsc` at the call
 * site without forcing a `Route` import here.
 */
export interface NavItem {
  title: string;
  href: string;
}

export interface SiteConfig {
  name: string;
  description: string;
  url: string;
  ogImage: string;
  links: { github: string };
  nav: readonly NavItem[];
}

export const siteConfig = {
  name: "Template-Projects",
  description: "Template-Projects — Next.js 16 + Supabase SaaS starter.",
  url: "http://localhost:3000",
  // Generated dynamically at /opengraph-image (see src/app/opengraph-image.tsx).
  // Override per-route by adding app/<route>/opengraph-image.tsx.
  ogImage: "/opengraph-image",
  links: {
    github: "https://github.com/kulikman/Template-Projects",
  },
  nav: [
    { title: routes.home.label, href: routes.home.href },
    { title: routes.pricing.label, href: routes.pricing.href },
    { title: routes.dashboard.label, href: routes.dashboard.href },
  ],
} as const satisfies SiteConfig;
import { routes } from "@/config/routes";
