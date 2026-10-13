import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

const mocks = vi.hoisted(() => ({
  getServerEnv: vi.fn(),
  logger: {
    warn: vi.fn(),
  },
  runScheduledCleanup: vi.fn(),
}));

vi.mock("@/lib/env", () => ({
  getServerEnv: mocks.getServerEnv,
}));

vi.mock("@/lib/logger", () => ({
  logger: mocks.logger,
}));

vi.mock("@/features/maintenance", () => ({
  runScheduledCleanup: mocks.runScheduledCleanup,
}));

import { GET } from "./route";

describe("GET /api/cron/cleanup", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getServerEnv.mockReturnValue({ CRON_SECRET: "secret" });
  });

  it("rejects unauthorized requests before cleanup work", async () => {
    const response = await GET(
      new Request("http://localhost/api/cron/cleanup") as unknown as NextRequest
    );

    await expect(response.json()).resolves.toEqual({ error: "Unauthorized" });
    expect(response.status).toBe(401);
    expect(mocks.runScheduledCleanup).not.toHaveBeenCalled();
  });

  it("runs cleanup for authorized cron requests", async () => {
    mocks.runScheduledCleanup.mockResolvedValueOnce({
      notificationsDeleted: 2,
      expiredInvitesDeleted: 1,
    });

    const response = await GET(
      new Request("http://localhost/api/cron/cleanup", {
        headers: { authorization: "Bearer secret" },
      }) as unknown as NextRequest
    );

    await expect(response.json()).resolves.toEqual({
      ok: true,
      notificationsDeleted: 2,
      expiredInvitesDeleted: 1,
    });
    expect(response.status).toBe(200);
    expect(mocks.runScheduledCleanup).toHaveBeenCalledTimes(1);
  });
});
