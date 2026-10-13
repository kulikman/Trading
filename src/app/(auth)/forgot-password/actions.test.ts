import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createClient: vi.fn(),
  getRequestIp: vi.fn(),
  getServerEnv: vi.fn(),
  limit: vi.fn(),
  logger: {
    warn: vi.fn(),
  },
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

import { sendPasswordReset } from "./actions";

function resetForm(email = "user@example.com"): FormData {
  const formData = new FormData();
  formData.set("email", email);
  return formData;
}

describe("sendPasswordReset()", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getRequestIp.mockResolvedValue("203.0.113.10");
    mocks.getServerEnv.mockReturnValue({ NEXT_PUBLIC_APP_URL: "https://example.com" });
    mocks.limit.mockResolvedValue({ success: true, remaining: 2, reset: Date.now() + 300_000 });
    mocks.createClient.mockResolvedValue({
      auth: {
        resetPasswordForEmail: vi.fn().mockResolvedValue({ error: null }),
      },
    });
  });

  it("rejects invalid email before rate limiting", async () => {
    await expect(sendPasswordReset({}, resetForm("bad"))).resolves.toEqual({
      error: "Invalid email address",
    });

    expect(mocks.limit).not.toHaveBeenCalled();
  });

  it("returns rate limit errors", async () => {
    mocks.limit.mockResolvedValueOnce({
      success: false,
      remaining: 0,
      reset: Date.now() + 300_000,
    });

    await expect(sendPasswordReset({}, resetForm())).resolves.toEqual({
      error: "Too many attempts. Try again in 5 minutes.",
    });
  });

  it("always returns success after Supabase reset attempt", async () => {
    mocks.createClient.mockResolvedValueOnce({
      auth: {
        resetPasswordForEmail: vi.fn().mockResolvedValue({ error: new Error("smtp down") }),
      },
    });

    await expect(sendPasswordReset({}, resetForm())).resolves.toEqual({ success: true });
    expect(mocks.logger.warn).toHaveBeenCalledWith("password reset email failed", {
      reason: "smtp down",
    });
  });
});
