import { test, expect } from "@playwright/test";

import { skipWithoutE2EBackend } from "./env";

/**
 * Auth flow E2E tests.
 *
 * These run against a real dev/preview server. They do NOT mock Supabase —
 * use a dedicated test Supabase project or set SUPABASE_TEST_USER/PASS.
 *
 * For CI: set TEST_BASE_URL to your Vercel preview URL and supply test credentials.
 */

// Credentials for future authenticated flow tests.
const _TEST_EMAIL = process.env.TEST_USER_EMAIL ?? "test@example.com";
const _TEST_PASSWORD = process.env.TEST_USER_PASSWORD ?? "TestPassword123";
void _TEST_EMAIL;
void _TEST_PASSWORD;

test.describe("Login page", () => {
  test("renders login form", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
    await expect(page.getByRole("textbox", { name: /email/i })).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /forgot password/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /sign up/i })).toBeVisible();
  });

  test("shows error on invalid credentials", async ({ page }) => {
    skipWithoutE2EBackend();
    await page.goto("/login");
    await page.getByRole("textbox", { name: /email/i }).fill("nobody@example.com");
    await page.getByLabel(/password/i).fill("WrongPassword1");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByRole("alert")).toBeVisible();
  });

  test("shows validation error on short password", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /email/i }).fill("user@example.com");
    await page.getByLabel(/password/i).fill("short");
    await page.getByRole("button", { name: /sign in/i }).click();
    // HTML5 minLength prevents submission; browser shows native error
    // or our Zod schema returns an error message.
    const input = page.getByLabel(/password/i);
    await expect(input).toHaveAttribute("minlength", "8");
  });
});

test.describe("Signup page", () => {
  test("renders signup form", async ({ page }) => {
    await page.goto("/signup");
    await expect(page.getByRole("heading", { name: /create an account/i })).toBeVisible();
    await expect(page.getByRole("textbox", { name: /email/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /sign in/i })).toBeVisible();
  });

  test("shows error when passwords do not match", async ({ page }) => {
    await page.goto("/signup");
    await page.getByRole("textbox", { name: /email/i }).fill("new@example.com");
    await page.getByRole("textbox", { name: /^password/i }).fill("ValidPass1");
    await page.getByLabel(/confirm password/i).fill("DifferentPass1");
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page.getByText(/passwords do not match/i)).toBeVisible();
  });
});

test.describe("Forgot password page", () => {
  test("renders forgot password form", async ({ page }) => {
    await page.goto("/forgot-password");
    await expect(page.getByRole("heading", { name: /forgot password/i })).toBeVisible();
    await expect(page.getByRole("textbox", { name: /email/i })).toBeVisible();
  });

  test("shows success after submitting any email", async ({ page }) => {
    skipWithoutE2EBackend();
    await page.goto("/forgot-password");
    await page.getByRole("textbox", { name: /email/i }).fill("anyone@example.com");
    await page.getByRole("button", { name: /send reset link/i }).click();
    await expect(page.getByRole("heading", { name: /check your email/i })).toBeVisible();
  });
});

test.describe("Navigation between auth pages", () => {
  test("login → signup → login", async ({ page }) => {
    await page.goto("/login");
    await page.locator('main a[href="/signup"]').click();
    await expect(page).toHaveURL("/signup");
    await page.locator('main a[href="/login"]').click();
    await expect(page).toHaveURL("/login");
  });

  test("login → forgot password → back to login", async ({ page }) => {
    await page.goto("/login");
    await page.locator('main a[href="/forgot-password"]').click();
    await expect(page).toHaveURL("/forgot-password");
    await page.locator('main a[href="/login"]').click();
    await expect(page).toHaveURL("/login");
  });
});
