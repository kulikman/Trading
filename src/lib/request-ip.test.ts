import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { getClientIpFromHeaders } from "./request-ip";

describe("getClientIpFromHeaders()", () => {
  it("uses the first x-forwarded-for address", () => {
    const headers = new Headers({
      "x-forwarded-for": "203.0.113.10, 10.0.0.1",
      "x-real-ip": "198.51.100.20",
    });

    expect(getClientIpFromHeaders(headers)).toBe("203.0.113.10");
  });

  it("falls back to x-real-ip", () => {
    const headers = new Headers({ "x-real-ip": "198.51.100.20" });

    expect(getClientIpFromHeaders(headers)).toBe("198.51.100.20");
  });

  it("returns unknown when no proxy headers are present", () => {
    expect(getClientIpFromHeaders(new Headers())).toBe("unknown");
  });
});
