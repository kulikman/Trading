import { test } from "@playwright/test";

/**
 * Backend-dependent e2e tests need a real Supabase project or preview URL.
 * Plain UI smoke tests can run with the dummy env from playwright.config.ts.
 */
export const hasE2EBackend =
  Boolean(process.env.TEST_BASE_URL) || process.env.E2E_USE_REAL_SUPABASE === "1";

export function skipWithoutE2EBackend(): void {
  test.skip(!hasE2EBackend, "requires TEST_BASE_URL or E2E_USE_REAL_SUPABASE=1");
}
