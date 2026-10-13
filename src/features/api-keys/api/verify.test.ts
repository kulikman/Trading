import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { verifyApiKey } from "./verify";

const mocks = vi.hoisted(() => {
  const maybeSingle = vi.fn();
  const eq = vi.fn(() => ({ maybeSingle }));
  const select = vi.fn(() => ({ eq }));
  const updateEq = vi.fn();
  const update = vi.fn(() => ({ eq: updateEq }));
  const from = vi.fn(() => ({ select, update }));
  const createAdminClient = vi.fn(() => ({ from }));

  return { createAdminClient, eq, from, maybeSingle, select, update };
});

vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: mocks.createAdminClient,
}));

describe("verifyApiKey()", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses the admin client so API-key requests do not require a Supabase cookie", async () => {
    mocks.maybeSingle.mockResolvedValueOnce({
      data: { user_id: "user-123", expires_at: null },
    });

    await expect(verifyApiKey("sk_live_test")).resolves.toBe("user-123");

    expect(mocks.createAdminClient).toHaveBeenCalledTimes(1);
    expect(mocks.from).toHaveBeenNthCalledWith(1, "api_keys");
    expect(mocks.select).toHaveBeenCalledWith("user_id, expires_at");
    expect(mocks.update).toHaveBeenCalledWith({ last_used_at: expect.any(String) });
  });

  it("returns null for missing, unknown, or expired keys", async () => {
    await expect(verifyApiKey(null)).resolves.toBeNull();
    expect(mocks.createAdminClient).not.toHaveBeenCalled();

    mocks.maybeSingle.mockResolvedValueOnce({ data: null });
    await expect(verifyApiKey("sk_live_unknown")).resolves.toBeNull();

    mocks.maybeSingle.mockResolvedValueOnce({
      data: { user_id: "user-123", expires_at: "2000-01-01T00:00:00.000Z" },
    });
    await expect(verifyApiKey("sk_live_expired")).resolves.toBeNull();
  });
});
