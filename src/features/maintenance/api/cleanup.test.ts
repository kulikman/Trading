import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { runScheduledCleanup } from "./cleanup";

const mocks = vi.hoisted(() => {
  const notificationsLt = vi.fn();
  const notificationsEq = vi.fn(() => ({ lt: notificationsLt }));
  const notificationsDelete = vi.fn(() => ({ eq: notificationsEq }));

  const invitesIs = vi.fn();
  const invitesLt = vi.fn(() => ({ is: invitesIs }));
  const invitesDelete = vi.fn(() => ({ lt: invitesLt }));

  const from = vi.fn();
  const createAdminClient = vi.fn(() => ({ from }));
  const logger = {
    error: vi.fn(),
    info: vi.fn(),
  };

  return {
    createAdminClient,
    from,
    invitesDelete,
    invitesIs,
    invitesLt,
    logger,
    notificationsDelete,
    notificationsEq,
    notificationsLt,
  };
});

vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: mocks.createAdminClient,
}));

vi.mock("@/lib/logger", () => ({
  logger: mocks.logger,
}));

describe("runScheduledCleanup()", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.from.mockImplementation((table: string) => {
      if (table === "notifications") {
        return { delete: mocks.notificationsDelete };
      }

      if (table === "org_invites") {
        return { delete: mocks.invitesDelete };
      }

      throw new Error(`Unexpected table: ${table}`);
    });
  });

  it("deletes stale notifications and expired invites", async () => {
    mocks.notificationsLt.mockResolvedValueOnce({ count: 2, error: null });
    mocks.invitesIs.mockResolvedValueOnce({ count: 3, error: null });

    const now = new Date("2026-05-27T12:00:00.000Z");

    await expect(runScheduledCleanup(now)).resolves.toEqual({
      notificationsDeleted: 2,
      expiredInvitesDeleted: 3,
    });

    expect(mocks.createAdminClient).toHaveBeenCalledTimes(1);
    expect(mocks.from).toHaveBeenCalledWith("notifications");
    expect(mocks.notificationsDelete).toHaveBeenCalledWith({ count: "exact" });
    expect(mocks.notificationsEq).toHaveBeenCalledWith("read", true);
    expect(mocks.notificationsLt).toHaveBeenCalledWith("created_at", "2026-04-27T12:00:00.000Z");

    expect(mocks.from).toHaveBeenCalledWith("org_invites");
    expect(mocks.invitesDelete).toHaveBeenCalledWith({ count: "exact" });
    expect(mocks.invitesLt).toHaveBeenCalledWith("expires_at", "2026-05-27T12:00:00.000Z");
    expect(mocks.invitesIs).toHaveBeenCalledWith("accepted_at", null);
  });

  it("logs failed deletes without throwing", async () => {
    const notifError = new Error("notifications failed");
    mocks.notificationsLt.mockResolvedValueOnce({ count: null, error: notifError });
    mocks.invitesIs.mockResolvedValueOnce({ count: 1, error: null });

    await expect(runScheduledCleanup(new Date("2026-05-27T12:00:00.000Z"))).resolves.toEqual({
      expiredInvitesDeleted: 1,
    });

    expect(mocks.logger.error).toHaveBeenCalledWith(
      "cron/cleanup: notifications delete failed",
      notifError
    );
  });
});
