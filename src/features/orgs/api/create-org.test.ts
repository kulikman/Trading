import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

// No vi.mock() for lib/org, @/lib/audit, or @/lib/logger.
// The use case accepts deps as a parameter — inject stubs directly.
import { createOrgForUser, getCreateOrgErrorResponse, type CreateOrgDeps } from "./create-org";

function makeStubs(): CreateOrgDeps {
  return {
    createOrg: vi.fn().mockResolvedValue({ id: "org-1", slug: "acme" }),
    writeAuditLog: vi.fn().mockResolvedValue(undefined),
    log: vi.fn(),
  };
}

describe("createOrgForUser()", () => {
  let deps: CreateOrgDeps;

  beforeEach(() => {
    deps = makeStubs();
  });

  it("creates org and returns id + slug", async () => {
    const result = await createOrgForUser({ name: "Acme", slug: "acme", userId: "user-1" }, deps);

    expect(result).toEqual({ id: "org-1", slug: "acme" });
    expect(deps.createOrg).toHaveBeenCalledWith({
      name: "Acme",
      slug: "acme",
      userId: "user-1",
    });
  });

  it("writes audit log with org resource reference", async () => {
    await createOrgForUser({ name: "Acme", slug: "acme", userId: "user-1" }, deps);

    expect(deps.writeAuditLog).toHaveBeenCalledWith(
      expect.objectContaining({
        userId: "user-1",
        resource: "organization:org-1",
        metadata: expect.objectContaining({ event: "org_created", slug: "acme" }),
      })
    );
  });

  it("emits a log line with orgId and userId", async () => {
    await createOrgForUser({ name: "Acme", slug: "acme", userId: "user-1" }, deps);

    expect(deps.log).toHaveBeenCalledWith("org created", {
      orgId: "org-1",
      userId: "user-1",
    });
  });

  it("propagates errors from createOrg without swallowing", async () => {
    (deps.createOrg as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("db down"));

    await expect(
      createOrgForUser({ name: "Acme", slug: "acme", userId: "user-1" }, deps)
    ).rejects.toThrow("db down");
  });
});

describe("getCreateOrgErrorResponse()", () => {
  it("normalizes duplicate slug errors to 409", () => {
    expect(getCreateOrgErrorResponse(new Error("duplicate key value violates unique"))).toEqual({
      error: "That slug is already taken.",
      status: 409,
    });
  });

  it("normalizes 'unique' keyword variant", () => {
    expect(getCreateOrgErrorResponse(new Error("unique constraint failed"))).toEqual({
      error: "That slug is already taken.",
      status: 409,
    });
  });

  it("passes unknown errors through as 500", () => {
    expect(getCreateOrgErrorResponse(new Error("database unavailable"))).toEqual({
      error: "database unavailable",
      status: 500,
    });
  });

  it("handles non-Error thrown values", () => {
    expect(getCreateOrgErrorResponse("oops")).toEqual({
      error: "Failed to create organization",
      status: 500,
    });
  });
});
