import type { KnipConfig } from "knip";

/**
 * Knip — dead code detector.
 *
 * Finds unused files, exports, and dependencies. Run: `pnpm knip`.
 *
 * Docs: https://knip.dev/overview/configuration
 *
 * The `ignore*` lists below cover **intentional** template-public APIs and
 * peer-dep style imports that knip can't statically resolve. Any new entry
 * here needs a one-line comment explaining why it's kept.
 */
const config: KnipConfig = {
  entry: [
    // Next.js App Router entry points
    "src/app/**/{page,layout,loading,error,not-found,route,opengraph-image,icon,sitemap,robots}.{ts,tsx}",
  ],
  project: ["src/**/*.{ts,tsx}"],
  ignore: [
    // template-public APIs: not imported by in-repo code but exported for consumers
    "src/components/plan-gate.tsx",
    "src/lib/analytics.ts",
    // domain-layer public barrel: re-exports @public-tagged types for
    // consumers; the @public tag exempts individual exports but not the
    // file itself from knip's "unused file" check.
    "src/domain/index.ts",
  ],
  ignoreDependencies: [
    "tailwindcss", // loaded via PostCSS plugin, not imported in TS
    "shadcn", // CLI: `pnpm dlx shadcn@latest add ...`
    "postcss", // peer dep of @tailwindcss/postcss, used in postcss.config.mjs
  ],
  ignoreExportsUsedInFile: true,
  ignoreIssues: {
    // generated Supabase helper types are public API for app/template consumers
    "src/types/database.ts": ["exports", "types"],
  },
  // Exports tagged with `@public` in JSDoc are template-public APIs —
  // exported on purpose for consumers, even if nothing in-repo imports them.
  tags: ["-public"],
  ignoreBinaries: [
    "supabase", // CLI used in pnpm scripts, installed globally / via npx
  ],
  paths: {
    "@/*": ["./src/*"],
  },
};

export default config;
