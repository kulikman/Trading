import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const mocks = vi.hoisted(() => ({
  createClient: vi.fn(),
  getRequestIp: vi.fn(),
  getServerEnv: vi.fn(),
  limit: vi.fn(),
  logger: {
    warn: vi.fn(),
  },
  redirect: vi.fn((url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  }),
  sendEmail: vi.fn(),
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

vi.mock("@/lib/env", () => ({
  getServerEnv: mocks.getServerEnv,
}));

vi.mock("@/lib/logger", () => ({
  logger: mocks.logger,
}));

vi.mock("@/lib/email", () => ({
  sendEmail: mocks.sendEmail,
}));

vi.mock("@/lib/audit", () => ({
  writeAuditLog: mocks.writeAuditLog,
}));

vi.mock("next/navigation", () => ({
  redirect: mocks.redirect,
}));

import { signUp } from "./actions";

function signupForm(
  email = "user@example.com",
  password = "password1",
  confirmPassword = "password1"
): FormData {
  const formData = new FormData();
  formData.set("email", email);
  formData.set("password", password);
  formData.set("confirmPassword", confirmPassword);
  return formData;
}

describe("signUp()", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getRequestIp.mockResolvedValue("203.0.113.10");
    mocks.getServerEnv.mockReturnValue({ NEXT_PUBLIC_APP_URL: "https://example.com" });
    mocks.limit.mockResolvedValue({ success: true, remaining: 2, reset: Date.now() + 60_000 });
    mocks.sendEmail.mockResolvedValue(undefined);
    mocks.createClient.mockResolvedValue({
      auth: {
        signUp: vi.fn().mockResolvedValue({
          data: { session: null, user: { id: "user-1" } },
          error: null,
        }),
      },
    });
  });

  it("rejects mismatched passwords before rate limiting", async () => {
    await expect(
      signUp({}, signupForm("user@example.com", "password1", "password2"))
    ).resolves.toEqual({
      error: "Passwords do not match",
    });

    expect(mocks.limit).not.toHaveBeenCalled();
  });

  it("returns a friendly duplicate-account error", async () => {
    mocks.createClient.mockResolvedValueOnce({
      auth: {
        signUp: vi.fn().mockResolvedValue({
          data: { session: null, user: null },
          error: new Error("User already registered"),
        }),
      },
    });

    await expect(signUp({}, signupForm())).resolves.toEqual({
      error: "An account with this email already exists.",
    });
  });

  it("audits, emails, and returns success when confirmation is required", async () => {
    await expect(signUp({}, signupForm())).resolves.toEqual({ success: true });

    expect(mocks.writeAuditLog).toHaveBeenCalledWith({
      userId: "user-1",
      action: "auth.signup",
      metadata: { ip: "203.0.113.10" },
    });
    expect(mocks.sendEmail).toHaveBeenCalledTimes(1);
  });

  it("redirects when Supabase returns an active session", async () => {
    mocks.createClient.mockResolvedValueOnce({
      auth: {
        signUp: vi.fn().mockResolvedValue({
          data: { session: { access_token: "token" }, user: { id: "user-1" } },
          error: null,
        }),
      },
    });

    await expect(signUp({}, signupForm())).rejects.toThrow("NEXT_REDIRECT:/dashboard");
  });
});
