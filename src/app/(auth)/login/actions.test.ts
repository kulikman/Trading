import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createClient: vi.fn(),
  getRequestIp: vi.fn(),
  limit: vi.fn(),
  logger: {
    warn: vi.fn(),
  },
  redirect: vi.fn((url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  }),
  writeAuditLog: vi.fn(),
}));

vi.mock("@/lib/supabase/server", () => ({
  createClient: mocks.createClient,
}));

vi.mock("@/lib/request-ip", () => ({
  getRequestIp: mocks.getRequestIp,
}));

vi.mock("@/lib/rate-limit", () => ({
  limit: mocks.limit,
}));

vi.mock("@/lib/logger", () => ({
  logger: mocks.logger,
}));

vi.mock("@/lib/audit", () => ({
  writeAuditLog: mocks.writeAuditLog,
}));

vi.mock("next/navigation", () => ({
  redirect: mocks.redirect,
}));

import { signInWithPassword } from "./actions";

function loginForm(email = "user@example.com", password = "password1"): FormData {
  const formData = new FormData();
  formData.set("email", email);
  formData.set("password", password);
  return formData;
}

describe("signInWithPassword()", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getRequestIp.mockResolvedValue("203.0.113.10");
    mocks.limit.mockResolvedValue({ success: true, remaining: 4, reset: Date.now() + 60_000 });
    mocks.createClient.mockResolvedValue({
      auth: {
        getUser: vi.fn().mockResolvedValue({ data: { user: { id: "user-1" } } }),
        signInWithPassword: vi.fn().mockResolvedValue({ error: null }),
      },
    });
  });

  it("rejects invalid form data before rate limiting", async () => {
    await expect(signInWithPassword({}, loginForm("bad", "short"))).resolves.toEqual({
      error: "Invalid email address",
    });

    expect(mocks.limit).not.toHaveBeenCalled();
  });

  it("returns a rate limit error before auth work", async () => {
    mocks.limit.mockResolvedValueOnce({ success: false, remaining: 0, reset: Date.now() + 60_000 });

    await expect(signInWithPassword({}, loginForm())).resolves.toEqual({
      error: "Too many attempts. Try again in a minute.",
    });

    expect(mocks.limit).toHaveBeenCalledWith("login:203.0.113.10", {
      limit: 5,
      windowMs: 60_000,
    });
    expect(mocks.createClient).not.toHaveBeenCalled();
  });

  it("audits and redirects successful logins", async () => {
    await expect(signInWithPassword({}, loginForm())).rejects.toThrow("NEXT_REDIRECT:/dashboard");

    expect(mocks.writeAuditLog).toHaveBeenCalledWith({
      userId: "user-1",
      action: "auth.login",
      metadata: { ip: "203.0.113.10" },
    });
  });
});
