import { test, expect } from "@playwright/test";

/**
 * Landing page smoke tests — no backend needed.
 *
 * Verifies that the public entry point renders correctly and links point
 * to the right destinations. Runs fully headless with placeholder env vars.
 */

test.describe("Landing page", () => {
  test("renders hero heading and description", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Next.js");
  });

  test("has a call-to-action link to the dashboard", async ({ page }) => {
    await page.goto("/");
    const cta = page.getByRole("link", { name: /open dashboard/i });
    await expect(cta).toBeVisible();
    await expect(cta).toHaveAttribute("href", "/dashboard");
  });

  test("has a repository link", async ({ page }) => {
    await page.goto("/");
    const repoLink = page.getByRole("link", { name: /repository/i });
    await expect(repoLink).toBeVisible();
    await expect(repoLink).toHaveAttribute("target", "_blank");
  });

  test("returns 200 status", async ({ request }) => {
    const response = await request.get("/");
    expect(response.status()).toBe(200);
  });
});
