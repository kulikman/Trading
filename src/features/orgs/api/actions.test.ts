import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createOrgForUser: vi.fn(),
  getCreateOrgErrorResponse: vi.fn(),
  requireUser: vi.fn(),
}));

vi.mock("server-only", () => ({}));

vi.mock("@/lib/auth", () => ({
  requireUser: mocks.requireUser,
}));

// Mock the use-case layer, not the repository — actions.ts now goes through
// createOrgForUser which handles audit logging internally.
vi.mock("./create-org", () => ({
  createOrgForUser: mocks.createOrgForUser,
  getCreateOrgErrorResponse: mocks.getCreateOrgErrorResponse,
}));

vi.mock("@/lib/logger", () => ({
  logger: { error: vi.fn() },
}));

import { createOrgAction } from "./actions";

describe("createOrgAction()", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.requireUser.mockResolvedValue({ id: "server-user-id" });
    mocks.createOrgForUser.mockResolvedValue({ id: "org-1", slug: "acme" });
    mocks.getCreateOrgErrorResponse.mockReturnValue({
      error: "That slug is already taken.",
      status: 409,
    });
  });

  it("derives userId from the server session instead of client input", async () => {
    await expect(createOrgAction({ name: "Acme", slug: "acme" })).resolves.toEqual({ ok: true });

    expect(mocks.requireUser).toHaveBeenCalledTimes(1);
    expect(mocks.createOrgForUser).toHaveBeenCalledWith({
      name: "Acme",
      slug: "acme",
      userId: "server-user-id",
    });
  });

  it("rejects invalid name before calling the use case", async () => {
    await expect(createOrgAction({ name: "", slug: "acme" })).resolves.toEqual({
      ok: false,
      error: "Name must be 1–100 characters.",
    });

    expect(mocks.createOrgForUser).not.toHaveBeenCalled();
  });

  it("rejects invalid slug before calling the use case", async () => {
    await expect(createOrgAction({ name: "Acme", slug: "x" })).resolves.toEqual({
      ok: false,
      error: "Slug must be 2–48 lowercase letters, numbers, or hyphens.",
    });

    expect(mocks.createOrgForUser).not.toHaveBeenCalled();
  });

  it("returns duplicate-slug error when use case throws unique violation", async () => {
    mocks.createOrgForUser.mockRejectedValueOnce(
      new Error("duplicate key value violates unique constraint")
    );

    await expect(createOrgAction({ name: "Acme", slug: "acme" })).resolves.toEqual({
      ok: false,
      error: "That slug is already taken.",
    });
  });
});
