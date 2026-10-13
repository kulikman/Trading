import { test, expect } from "@playwright/test";

import { skipWithoutE2EBackend } from "./env";

/**
 * Navigation and protected-route redirect tests.
 *
 * Some tests require a real Supabase backend to verify redirect behavior —
 * the proxy's session check calls Supabase Auth and only works with real cookies.
 * UI-only checks (page structure, links) run without a backend.
 */

test.describe("Protected route redirects (requires backend)", () => {
  test("visiting /dashboard while signed out redirects to /login", async ({ page }) => {
    skipWithoutE2EBackend();
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });

  test("visiting /settings while signed out redirects to /login", async ({ page }) => {
    skipWithoutE2EBackend();
    await page.goto("/settings");
    await expect(page).toHaveURL(/\/login/);
  });

  test("visiting /settings/billing while signed out redirects to /login", async ({ page }) => {
    skipWithoutE2EBackend();
    await page.goto("/settings/billing");
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe("Health check", () => {
  test("GET /api/health returns 200 with status: ok", async ({ request }) => {
    const response = await request.get("/api/health");
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toMatchObject({ status: "ok" });
  });
});

test.describe("API auth guards", () => {
  test("GET /api/orgs without session does not return 500", async ({ request }) => {
    skipWithoutE2EBackend();
    const status = (await request.get("/api/orgs")).status();
    // requireUser() redirects unauthenticated callers; Playwright follows redirects.
    // Accept any redirect/auth error — just ensure the server doesn't crash.
    expect(status).not.toBe(500);
  });
});

test.describe("404 page", () => {
  test("unknown routes render the 404 page", async ({ page }) => {
    await page.goto("/this-route-does-not-exist-xyz");
    await expect(page.getByRole("heading")).toBeVisible();
    await expect(page).toHaveURL("/this-route-does-not-exist-xyz");
  });
});
