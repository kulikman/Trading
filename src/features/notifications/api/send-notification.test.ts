import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { sendNotification } from "./send-notification";

const mocks = vi.hoisted(() => {
  const insert = vi.fn();
  const from = vi.fn(() => ({ insert }));
  const createAdminClient = vi.fn(() => ({ from }));

  return { createAdminClient, from, insert };
});

vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: mocks.createAdminClient,
}));

describe("sendNotification()", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses the admin client from a server-only module", async () => {
    mocks.insert.mockResolvedValueOnce({ error: null });

    await sendNotification("user-123", {
      title: "Welcome",
      body: "Your workspace is ready.",
      href: "/dashboard",
      kind: "success",
    });

    expect(mocks.createAdminClient).toHaveBeenCalledTimes(1);
    expect(mocks.from).toHaveBeenCalledWith("notifications");
    expect(mocks.insert).toHaveBeenCalledWith({
      user_id: "user-123",
      title: "Welcome",
      body: "Your workspace is ready.",
      href: "/dashboard",
      kind: "success",
    });
  });

  it("defaults optional notification fields", async () => {
    mocks.insert.mockResolvedValueOnce({ error: null });

    await sendNotification("user-123", { title: "Heads up" });

    expect(mocks.insert).toHaveBeenCalledWith({
      user_id: "user-123",
      title: "Heads up",
      body: null,
      href: null,
      kind: "info",
    });
  });
});
