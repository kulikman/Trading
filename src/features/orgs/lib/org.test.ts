import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { createOrg } from "./org";

const mocks = vi.hoisted(() => {
  const single = vi.fn();
  const select = vi.fn(() => ({ single }));
  const eq = vi.fn();
  const deleteQuery = vi.fn(() => ({ eq }));
  const insert = vi.fn();
  const from = vi.fn();
  const createAdminClient = vi.fn(() => ({ from }));

  return { createAdminClient, deleteQuery, eq, from, insert, select, single };
});

vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: mocks.createAdminClient,
}));

describe("createOrg()", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mocks.from.mockImplementation((table: string) => {
      if (table === "organizations") {
        return {
          insert: vi.fn(() => ({ select: mocks.select })),
          delete: mocks.deleteQuery,
        };
      }

      if (table === "org_members") {
        return { insert: mocks.insert };
      }

      throw new Error(`Unexpected table: ${table}`);
    });
  });

  it("removes the organization when owner membership creation fails", async () => {
    const membershipError = new Error("membership failed");
    mocks.single.mockResolvedValueOnce({ data: { id: "org-1", slug: "acme" }, error: null });
    mocks.insert.mockResolvedValueOnce({ error: membershipError });

    await expect(createOrg({ name: "Acme", slug: "acme", userId: "user-1" })).rejects.toThrow(
      membershipError
    );

    expect(mocks.deleteQuery).toHaveBeenCalledTimes(1);
    expect(mocks.eq).toHaveBeenCalledWith("id", "org-1");
  });
});
