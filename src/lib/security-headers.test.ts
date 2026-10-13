import { describe, expect, it, vi } from "vitest";

import { buildSecurityHeaders } from "./security-headers";

describe("buildSecurityHeaders()", () => {
  it("allows configured analytics endpoints without loosening script policy", () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://project.supabase.co");

    const csp = buildSecurityHeaders({ isDev: false })["Content-Security-Policy"];

    expect(csp).toContain("https://*.posthog.com");
    expect(csp).toContain("https://*.i.posthog.com");
    expect(csp).not.toContain("'unsafe-eval'");
  });
});
