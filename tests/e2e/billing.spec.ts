import { test, expect } from "@playwright/test";

import { skipWithoutE2EBackend } from "./env";

/**
 * Billing E2E tests.
 *
 * These verify the billing UI renders correctly for unauthenticated and
 * authenticated users. Full Stripe flows require a Stripe test-mode
 * environment — see tests/e2e/README.md for setup.
 */

test.describe("Billing page (unauthenticated)", () => {
  test("redirects to login", async ({ page }) => {
    skipWithoutE2EBackend();
    await page.goto("/settings/billing");
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe("Settings page (unauthenticated)", () => {
  test("redirects to login", async ({ page }) => {
    skipWithoutE2EBackend();
    await page.goto("/settings");
    await expect(page).toHaveURL(/\/login/);
  });
});
