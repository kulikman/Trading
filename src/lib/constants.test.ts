import { describe, it, expect } from "vitest";

import { ROUTES } from "./constants";

describe("ROUTES route contract", () => {
  it("exposes the semantic organization settings route", () => {
    expect(ROUTES.settingsOrganization).toBe("/settings/organization");
    expect(Object.values(ROUTES)).not.toContain("/settings/org");
  });
});
