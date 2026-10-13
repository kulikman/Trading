import { describe, expect, it } from "vitest";

import { getBreadcrumbItems } from "./breadcrumbs";

describe("getBreadcrumbItems()", () => {
  it("does not render on home and dashboard", () => {
    expect(getBreadcrumbItems("/")).toEqual([]);
    expect(getBreadcrumbItems("/dashboard")).toEqual([]);
  });

  it("does not render on first-level list pages", () => {
    expect(getBreadcrumbItems("/companies")).toEqual([]);
    expect(getBreadcrumbItems("/projects")).toEqual([]);
  });

  it("starts with Dashboard and marks last item as current", () => {
    const items = getBreadcrumbItems("/companies/123");

    expect(items[0]).toEqual({
      href: "/dashboard",
      label: "Dashboard",
      isCurrent: false,
    });

    expect(items.at(-1)?.isCurrent).toBe(true);
  });

  it("uses special labels for edit and new", () => {
    const editItems = getBreadcrumbItems("/companies/123/edit");
    expect(editItems.at(-1)?.label).toBe("Edit");

    const newItems = getBreadcrumbItems("/companies/new");
    expect(newItems.at(-1)?.label).toBe("New Company");
  });

  it("supports resolveLabel for dynamic segments", () => {
    const items = getBreadcrumbItems("/companies/abc123", {
      resolveLabel: (segment) => (segment === "abc123" ? "Acme Inc" : null),
    });

    expect(items.at(-1)?.label).toBe("Acme Inc");
  });

  it("uses route contract labels for settings routes", () => {
    expect(getBreadcrumbItems("/settings/billing")).toEqual([
      { href: "/dashboard", label: "Dashboard", isCurrent: false },
      { href: "/settings", label: "Settings", isCurrent: false },
      { href: "/settings/billing", label: "Billing", isCurrent: true },
    ]);

    expect(getBreadcrumbItems("/settings/org").at(-1)).toEqual({
      href: "/settings/organization",
      label: "Organization",
      isCurrent: true,
    });
  });
});
