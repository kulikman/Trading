import { z } from "zod";

/**
 * Server-side environment variables.
 *
 * Validated at build time and app startup. If any required variable is missing
 * or malformed, the build will fail with a clear error message rather than
 * silently producing broken behavior at runtime.
 *
 * Add new env vars here BEFORE using them in code.
 */
const serverSchema = z.object({
  // Supabase
  NEXT_PUBLIC_SUPABASE_URL: z.string().url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(1),
  SUPABASE_SERVICE_ROLE_KEY: z.string().min(1),

  // App
  NEXT_PUBLIC_APP_URL: z.string().url().default("http://localhost:3000"),
  NEXT_PUBLIC_APP_NAME: z.string().default("Template-Projects"),
  NODE_ENV: z.enum(["development", "production", "test"]).default("development"),

  // Analytics (optional)
  NEXT_PUBLIC_GA_MEASUREMENT_ID: z.string().optional(),
  NEXT_PUBLIC_GTM_ID: z.string().optional(),

  // Payments (optional)
  STRIPE_SECRET_KEY: z.string().optional(),
  NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY: z.string().optional(),
  STRIPE_WEBHOOK_SECRET: z.string().optional(),
  // Stripe product IDs — map to plan tiers in plan-limits.ts
  STRIPE_PRODUCT_ID_PRO: z.string().optional(),
  STRIPE_PRODUCT_ID_TEAM: z.string().optional(),
  // Price IDs — used by BillingCard checkout buttons
  STRIPE_PRICE_ID_PRO: z.string().optional(),
  STRIPE_PRICE_ID_TEAM: z.string().optional(),

  // AI (optional)
  ANTHROPIC_API_KEY: z.string().optional(),
  OPENAI_API_KEY: z.string().optional(),

  // Email (optional)
  RESEND_API_KEY: z.string().optional(),
  RESEND_FROM_EMAIL: z.string().email().optional(),

  // Cron jobs (required when you wire scheduled routes)
  CRON_SECRET: z.string().min(16).optional(),

  // Rate limiting in production (optional — falls back to in-memory limiter)
  UPSTASH_REDIS_REST_URL: z.string().url().optional(),
  UPSTASH_REDIS_REST_TOKEN: z.string().optional(),

  // Error tracking (optional)
  NEXT_PUBLIC_SENTRY_DSN: z.string().url().optional(),
  SENTRY_AUTH_TOKEN: z.string().optional(),
  SENTRY_ORG: z.string().optional(),
  SENTRY_PROJECT: z.string().optional(),

  // Product analytics — PostHog (optional)
  NEXT_PUBLIC_POSTHOG_KEY: z.string().optional(),
  NEXT_PUBLIC_POSTHOG_HOST: z.string().url().optional(),

  // Feature flags (optional)
  NEXT_PUBLIC_FF_ONBOARDING: z.string().optional(),
  NEXT_PUBLIC_FF_NOTIFICATIONS: z.string().optional(),
  NEXT_PUBLIC_FF_API_KEYS: z.string().optional(),
});

/**
 * Client-side environment variables.
 *
 * Only variables prefixed with `NEXT_PUBLIC_` are available on the client.
 * This schema is a subset of the server schema — never add secrets here.
 */
const clientSchema = z.object({
  NEXT_PUBLIC_SUPABASE_URL: z.string().url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(1),
  NEXT_PUBLIC_APP_URL: z.string().url().default("http://localhost:3000"),
  NEXT_PUBLIC_APP_NAME: z.string().default("Template-Projects"),
  NEXT_PUBLIC_GA_MEASUREMENT_ID: z.string().optional(),
  NEXT_PUBLIC_GTM_ID: z.string().optional(),
  NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY: z.string().optional(),
  NEXT_PUBLIC_SENTRY_DSN: z.string().url().optional(),
  NEXT_PUBLIC_POSTHOG_KEY: z.string().optional(),
  NEXT_PUBLIC_POSTHOG_HOST: z.string().url().optional(),
});

/** Public site URL/name only — for `robots.ts`, `sitemap.ts`, and other metadata that must build without Supabase keys. */
const publicMetadataSchema = z.object({
  NEXT_PUBLIC_APP_URL: z.string().url().default("http://localhost:3000"),
  NEXT_PUBLIC_APP_NAME: z.string().default("Template-Projects"),
});

const publicAnalyticsSchema = z.object({
  NEXT_PUBLIC_POSTHOG_KEY: z.string().optional(),
  NEXT_PUBLIC_POSTHOG_HOST: z.string().url().optional(),
});

export type ServerEnv = z.infer<typeof serverSchema>;
export type ClientEnv = z.infer<typeof clientSchema>;
export type PublicMetadataEnv = z.infer<typeof publicMetadataSchema>;
export type PublicAnalyticsEnv = z.infer<typeof publicAnalyticsSchema>;

/**
 * Validate and return typed server env.
 *
 * Call this once at app startup (e.g. in `instrumentation.ts` or a
 * Server Component that runs early). Throws with a descriptive error
 * if any required variable is missing.
 *
 * @example
 *   const env = getServerEnv()
 *   console.log(env.SUPABASE_SERVICE_ROLE_KEY) // typed, validated
 */
export function getServerEnv(): ServerEnv {
  const result = serverSchema.safeParse(process.env);

  if (!result.success) {
    const formatted = result.error.issues
      .map((issue) => `  ${issue.path.join(".")}: ${issue.message}`)
      .join("\n");

    throw new Error(
      `❌ Invalid environment variables:\n${formatted}\n\nCheck .env.local against .env.example.`
    );
  }

  return result.data;
}

/**
 * Validated public URL and app name for server-side metadata routes.
 *
 * Does not require Supabase or service-role keys, so `next build` can prerender
 * `robots.txt` / `sitemap.xml` in CI before secrets are injected.
 */
export function getPublicMetadataEnv(): PublicMetadataEnv {
  const result = publicMetadataSchema.safeParse({
    NEXT_PUBLIC_APP_URL: process.env.NEXT_PUBLIC_APP_URL,
    NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME,
  });

  if (!result.success) {
    const formatted = result.error.issues
      .map((issue) => `  ${issue.path.join(".")}: ${issue.message}`)
      .join("\n");

    throw new Error(
      `❌ Invalid public metadata environment:\n${formatted}\n\nCheck NEXT_PUBLIC_APP_URL / NEXT_PUBLIC_APP_NAME against .env.example.`
    );
  }

  return result.data;
}

/**
 * Optional public analytics env for global client providers.
 *
 * Does not require Supabase keys, so static pages can prerender in template QA
 * before a real project's backend env is connected.
 */
export function getPublicAnalyticsEnv(): PublicAnalyticsEnv {
  const result = publicAnalyticsSchema.safeParse({
    NEXT_PUBLIC_POSTHOG_KEY: process.env.NEXT_PUBLIC_POSTHOG_KEY,
    NEXT_PUBLIC_POSTHOG_HOST: process.env.NEXT_PUBLIC_POSTHOG_HOST,
  });

  if (!result.success) {
    const formatted = result.error.issues
      .map((issue) => `  ${issue.path.join(".")}: ${issue.message}`)
      .join("\n");

    throw new Error(
      `❌ Invalid public analytics environment:\n${formatted}\n\nCheck NEXT_PUBLIC_POSTHOG_HOST against .env.example.`
    );
  }

  return result.data;
}

/**
 * Validate and return typed client env.
 *
 * Safe to call anywhere — only exposes NEXT_PUBLIC_ variables.
 */
export function getClientEnv(): ClientEnv {
  const result = clientSchema.safeParse({
    NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    NEXT_PUBLIC_APP_URL: process.env.NEXT_PUBLIC_APP_URL,
    NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME,
    NEXT_PUBLIC_GA_MEASUREMENT_ID: process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID,
    NEXT_PUBLIC_GTM_ID: process.env.NEXT_PUBLIC_GTM_ID,
    NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY: process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY,
    NEXT_PUBLIC_SENTRY_DSN: process.env.NEXT_PUBLIC_SENTRY_DSN,
    NEXT_PUBLIC_POSTHOG_KEY: process.env.NEXT_PUBLIC_POSTHOG_KEY,
    NEXT_PUBLIC_POSTHOG_HOST: process.env.NEXT_PUBLIC_POSTHOG_HOST,
  });

  if (!result.success) {
    const formatted = result.error.issues
      .map((issue) => `  ${issue.path.join(".")}: ${issue.message}`)
      .join("\n");

    throw new Error(
      `❌ Invalid client environment variables:\n${formatted}\n\nCheck .env.local against .env.example.`
    );
  }

  return result.data;
}
