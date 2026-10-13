import { describe, it, expect, vi, beforeEach } from "vitest";

import { getServerEnv, getClientEnv, getPublicMetadataEnv, getPublicAnalyticsEnv } from "./env";

const VALID_ENV = {
  NEXT_PUBLIC_SUPABASE_URL: "https://test.supabase.co",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: "test-anon-key",
  SUPABASE_SERVICE_ROLE_KEY: "test-service-role-key",
  NEXT_PUBLIC_APP_URL: "http://localhost:3000",
  NEXT_PUBLIC_APP_NAME: "Test App",
  NODE_ENV: "test" as const,
};

describe("getServerEnv()", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_ENV.NEXT_PUBLIC_SUPABASE_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", VALID_ENV.NEXT_PUBLIC_SUPABASE_ANON_KEY);
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", VALID_ENV.SUPABASE_SERVICE_ROLE_KEY);
    vi.stubEnv("NEXT_PUBLIC_APP_URL", VALID_ENV.NEXT_PUBLIC_APP_URL);
    vi.stubEnv("NEXT_PUBLIC_APP_NAME", VALID_ENV.NEXT_PUBLIC_APP_NAME);
    vi.stubEnv("NODE_ENV", VALID_ENV.NODE_ENV);
  });

  it("returns typed env when all required vars are present", () => {
    const env = getServerEnv();
    expect(env.NEXT_PUBLIC_SUPABASE_URL).toBe(VALID_ENV.NEXT_PUBLIC_SUPABASE_URL);
    expect(env.SUPABASE_SERVICE_ROLE_KEY).toBe(VALID_ENV.SUPABASE_SERVICE_ROLE_KEY);
  });

  it("throws when SUPABASE_SERVICE_ROLE_KEY is missing", () => {
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "");
    expect(() => getServerEnv()).toThrow("Invalid environment variables");
  });

  it("throws when SUPABASE_URL is not a valid URL", () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "not-a-url");
    expect(() => getServerEnv()).toThrow("Invalid environment variables");
  });
});

describe("getClientEnv()", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_ENV.NEXT_PUBLIC_SUPABASE_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", VALID_ENV.NEXT_PUBLIC_SUPABASE_ANON_KEY);
    vi.stubEnv("NEXT_PUBLIC_APP_URL", VALID_ENV.NEXT_PUBLIC_APP_URL);
    vi.stubEnv("NEXT_PUBLIC_APP_NAME", VALID_ENV.NEXT_PUBLIC_APP_NAME);
  });

  it("returns only public env vars", () => {
    const env = getClientEnv();
    expect(env.NEXT_PUBLIC_SUPABASE_URL).toBe(VALID_ENV.NEXT_PUBLIC_SUPABASE_URL);
    // Service role should not exist on client env type
    expect(env).not.toHaveProperty("SUPABASE_SERVICE_ROLE_KEY");
  });

  it("exposes optional public analytics env vars to client code", () => {
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_KEY", "ph_test");
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_HOST", "https://us.i.posthog.com");

    const env = getClientEnv();

    expect(env.NEXT_PUBLIC_POSTHOG_KEY).toBe("ph_test");
    expect(env.NEXT_PUBLIC_POSTHOG_HOST).toBe("https://us.i.posthog.com");
  });
});

describe("getPublicMetadataEnv()", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns defaults when URL/name are unset (no Supabase vars required)", () => {
    const env = getPublicMetadataEnv();
    expect(env.NEXT_PUBLIC_APP_URL).toBe("http://localhost:3000");
    expect(env.NEXT_PUBLIC_APP_NAME).toBe("Template-Projects");
  });

  it("reads overrides when set", () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "https://example.com");
    vi.stubEnv("NEXT_PUBLIC_APP_NAME", "Example");
    const env = getPublicMetadataEnv();
    expect(env.NEXT_PUBLIC_APP_URL).toBe("https://example.com");
    expect(env.NEXT_PUBLIC_APP_NAME).toBe("Example");
  });

  it("throws when NEXT_PUBLIC_APP_URL is malformed", () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "not-a-url");
    expect(() => getPublicMetadataEnv()).toThrow("Invalid public metadata environment");
  });
});

describe("getPublicAnalyticsEnv()", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
  });

  it("does not require Supabase vars", () => {
    const env = getPublicAnalyticsEnv();
    expect(env.NEXT_PUBLIC_POSTHOG_KEY).toBeUndefined();
    expect(env.NEXT_PUBLIC_POSTHOG_HOST).toBeUndefined();
  });

  it("reads optional PostHog vars", () => {
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_KEY", "ph_test");
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_HOST", "https://us.i.posthog.com");

    const env = getPublicAnalyticsEnv();

    expect(env.NEXT_PUBLIC_POSTHOG_KEY).toBe("ph_test");
    expect(env.NEXT_PUBLIC_POSTHOG_HOST).toBe("https://us.i.posthog.com");
  });

  it("throws when NEXT_PUBLIC_POSTHOG_HOST is malformed", () => {
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_HOST", "not-a-url");
    expect(() => getPublicAnalyticsEnv()).toThrow("Invalid public analytics environment");
  });
});
