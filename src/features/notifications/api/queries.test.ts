import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { getRecentNotifications } from "./queries";

const mocks = vi.hoisted(() => {
  const limit = vi.fn();
  const order = vi.fn(() => ({ limit }));
  const eq = vi.fn(() => ({ order }));
  const select = vi.fn(() => ({ eq }));
  const from = vi.fn(() => ({ select }));
  const createAdminClient = vi.fn(() => ({ from }));

  return { createAdminClient, eq, from, limit, order, select };
});

vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: mocks.createAdminClient,
}));

describe("getRecentNotifications()", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads the latest notifications for one user through the admin client", async () => {
    const notifications = [
      {
        id: "notification-1",
        user_id: "user-123",
        title: "Welcome",
        body: null,
        href: "/dashboard",
        read: false,
        kind: "info",
        created_at: "2026-01-01T00:00:00.000Z",
      },
    ];
    mocks.limit.mockResolvedValueOnce({ data: notifications });

    await expect(getRecentNotifications("user-123")).resolves.toEqual(notifications);

    expect(mocks.createAdminClient).toHaveBeenCalledTimes(1);
    expect(mocks.from).toHaveBeenCalledWith("notifications");
    expect(mocks.select).toHaveBeenCalledWith(
      "id, user_id, title, body, href, read, kind, created_at"
    );
    expect(mocks.eq).toHaveBeenCalledWith("user_id", "user-123");
    expect(mocks.order).toHaveBeenCalledWith("created_at", { ascending: false });
    expect(mocks.limit).toHaveBeenCalledWith(20);
  });

  it("returns an empty list when there is no data", async () => {
    mocks.limit.mockResolvedValueOnce({ data: null });

    await expect(getRecentNotifications("user-123")).resolves.toEqual([]);
  });

  it("falls back to info when stored kind is outside the UI type", async () => {
    mocks.limit.mockResolvedValueOnce({
      data: [
        {
          id: "notification-1",
          user_id: "user-123",
          title: "Legacy",
          body: null,
          href: null,
          read: false,
          kind: "legacy",
          created_at: "2026-01-01T00:00:00.000Z",
        },
      ],
    });

    await expect(getRecentNotifications("user-123")).resolves.toEqual([
      {
        id: "notification-1",
        user_id: "user-123",
        title: "Legacy",
        body: null,
        href: null,
        read: false,
        kind: "info",
        created_at: "2026-01-01T00:00:00.000Z",
      },
    ]);
  });
});
