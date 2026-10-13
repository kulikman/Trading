import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E configuration.
 *
 * Tests live in `tests/e2e/`. Run with:
 *   pnpm test:e2e            — headless
 *   pnpm test:e2e --ui       — interactive UI mode
 *   pnpm test:e2e --headed   — visible browser
 *
 * Requires a running dev server (started automatically via `webServer`).
 * Set TEST_BASE_URL to run against a deployed preview URL in CI.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",

  use: {
    baseURL: process.env.TEST_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["iPhone 14"], browserName: "chromium" } },
  ],

  webServer: process.env.TEST_BASE_URL
    ? undefined
    : {
        command: "pnpm dev",
        env: {
          ...process.env,
          TEMPLATE_DEV: process.env.TEMPLATE_DEV ?? "1",
          NEXT_PUBLIC_SUPABASE_URL:
            process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://127.0.0.1:54321",
          NEXT_PUBLIC_SUPABASE_ANON_KEY:
            process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "e2e-anon-key",
          SUPABASE_SERVICE_ROLE_KEY:
            process.env.SUPABASE_SERVICE_ROLE_KEY ?? "e2e-service-role-key",
        },
        url: "http://localhost:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
