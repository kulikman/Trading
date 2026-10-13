import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import eslintConfigPrettier from "eslint-config-prettier/flat";
import boundaries from "eslint-plugin-boundaries";
import importPlugin from "eslint-plugin-import";

/** Restricted import patterns for cross-feature / deep feature paths (see ARCHITECTURE.md). */
const featureIsolationPatterns = [
  {
    group: [
      "**/features/*/lib/**",
      "**/features/*/_internal/**",
      "**/features/*/api/**",
    ],
    message:
      "Импорт внутренних путей чужого модуля запрещён. Используй публичный API: `@/features/<name>`.",
  },
  {
    group: ["../../features/**", "../../../features/**", "../../../../features/**"],
    message:
      "Относительные импорты между фичами запрещены. Используй `@/features/<name>`.",
  },
];

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  eslintConfigPrettier,
  {
    plugins: {
      boundaries,
      import: importPlugin,
    },
    settings: {
      "boundaries/elements": [
        { type: "app", pattern: "src/app/**" },
        // Domain: pure TypeScript interfaces — zero external deps, imported by all layers.
        { type: "domain", pattern: "src/domain/**" },
        {
          type: "foundation",
          pattern: "src/{components,lib,hooks,types,config}/**",
        },
        { type: "foundation", pattern: "src/proxy.ts" },
        {
          type: "feature",
          pattern: "src/features/*/**",
          capture: ["featureName"],
        },
      ],
    },
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/no-explicit-any": "error",
      "prefer-const": "error",
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["**/index", "**/index.ts", "**/index.tsx"],
              message:
                "Barrel files break tree-shaking in shared code. Import from the source file. Exception: feature public API is `src/features/<name>/index.ts` — import via `@/features/<name>` only (not `.../index`).",
            },
            ...featureIsolationPatterns,
          ],
        },
      ],
      "boundaries/dependencies": [
        "error",
        {
          default: "allow",
          rules: [
            {
              allow: {
                dependency: { relationship: { to: "internal" } },
              },
            },
            {
              from: { type: "feature" },
              disallow: { to: { type: "feature" } },
            },
            {
              from: { type: "feature" },
              allow: {
                to: {
                  type: "feature",
                  captured: { featureName: "{{from.captured.featureName}}" },
                },
              },
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/features/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": ["error", { patterns: [...featureIsolationPatterns] }],
    },
  },
  {
    files: ["src/components/**/*.tsx", "src/hooks/**/*.ts", "src/lib/**/*.ts"],
    rules: {
      "import/no-default-export": "error",
    },
  },
  {
    files: ["solo-founder-os/cli/**/*.ts"],
    rules: {
      "no-console": "off",
    },
  },
  // Ban raw `process.env` access — must go through `getServerEnv()` /
  // `getClientEnv()` from `@/lib/env`. Deliberate exceptions are listed
  // in `ignores` (they document why they need raw access).
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: [
      "src/lib/env.ts",
      "src/lib/flags.ts",
      "src/instrumentation.ts",
      "src/proxy.ts",
      "src/lib/security-headers.ts",
      "src/**/*.test.{ts,tsx}",
    ],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "MemberExpression[object.type='MemberExpression'][object.object.name='process'][object.property.name='env']",
          message:
            "Не используй raw `process.env`. Импортируй `getServerEnv()` / `getClientEnv()` из `@/lib/env`.",
        },
        {
          selector:
            "MemberExpression[object.name='process'][property.name='env']",
          message:
            "Не используй raw `process.env`. Импортируй `getServerEnv()` / `getClientEnv()` из `@/lib/env`.",
        },
      ],
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    ".sprint-backups/**",
    "scripts/**", // standalone Node scripts — console.log is intentional
  ]),
]);

export default eslintConfig;
