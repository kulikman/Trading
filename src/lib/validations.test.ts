import { describe, expect, it } from "vitest";

import { emailSchema, paginationSchema, uuidParamSchema } from "./validations";

describe("emailSchema", () => {
  it("accepts a valid email", () => {
    expect(emailSchema.parse("user@example.com")).toBe("user@example.com");
  });

  it("rejects malformed input with a readable message", () => {
    const result = emailSchema.safeParse("not-an-email");
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.message).toBe("Invalid email address");
    }
  });
});

describe("paginationSchema", () => {
  it("applies defaults when both fields are missing", () => {
    expect(paginationSchema.parse({})).toEqual({ page: 1, limit: 20 });
  });

  it("coerces string query params to integers", () => {
    expect(paginationSchema.parse({ page: "3", limit: "50" })).toEqual({
      page: 3,
      limit: 50,
    });
  });

  it("rejects non-positive page", () => {
    expect(paginationSchema.safeParse({ page: 0 }).success).toBe(false);
    expect(paginationSchema.safeParse({ page: -1 }).success).toBe(false);
  });

  it("clamps invalid limit values", () => {
    // limit must be in [1, 100]
    expect(paginationSchema.safeParse({ limit: 0 }).success).toBe(false);
    expect(paginationSchema.safeParse({ limit: 101 }).success).toBe(false);
  });
});

describe("uuidParamSchema", () => {
  it("accepts a v4 UUID", () => {
    const id = "550e8400-e29b-41d4-a716-446655440000";
    expect(uuidParamSchema.parse({ id })).toEqual({ id });
  });

  it("rejects non-UUID strings with a readable message", () => {
    const result = uuidParamSchema.safeParse({ id: "abc-123" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.message).toBe("Invalid ID format");
    }
  });
});
