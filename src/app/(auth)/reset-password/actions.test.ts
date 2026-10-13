import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createClient: vi.fn(),
  logger: {
    info: vi.fn(),
    warn: vi.fn(),
  },
  redirect: vi.fn((url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  }),
}));

vi.mock("@/lib/supabase/server", () => ({
  createClient: mocks.createClient,
}));

vi.mock("@/lib/logger", () => ({
  logger: mocks.logger,
}));

vi.mock("next/navigation", () => ({
  redirect: mocks.redirect,
}));

import { resetPassword } from "./actions";

function passwordForm(password = "password1", confirmPassword = "password1"): FormData {
  const formData = new FormData();
  formData.set("password", password);
  formData.set("confirmPassword", confirmPassword);
  return formData;
}

describe("resetPassword()", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.createClient.mockResolvedValue({
      auth: {
        updateUser: vi.fn().mockResolvedValue({ error: null }),
      },
    });
  });

  it("rejects mismatched passwords before auth work", async () => {
    await expect(resetPassword({}, passwordForm("password1", "password2"))).resolves.toEqual({
      error: "Passwords do not match",
    });

    expect(mocks.createClient).not.toHaveBeenCalled();
  });

  it("returns a safe error when the reset link is invalid", async () => {
    mocks.createClient.mockResolvedValueOnce({
      auth: {
        updateUser: vi.fn().mockResolvedValue({ error: new Error("expired token") }),
      },
    });

    await expect(resetPassword({}, passwordForm())).resolves.toEqual({
      error: "Could not update password. The reset link may have expired.",
    });
  });

  it("redirects after a successful password reset", async () => {
    await expect(resetPassword({}, passwordForm())).rejects.toThrow("NEXT_REDIRECT:/dashboard");
    expect(mocks.logger.info).toHaveBeenCalledWith("password reset success");
  });
});
