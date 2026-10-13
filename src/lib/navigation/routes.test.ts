import { describe, expect, it } from "vitest";

import {
  flattenRoutes,
  getBreadcrumbItemsFromRoutes,
  getCanonicalPathname,
  getRouteRedirects,
  getSitemapRoutes,
} from "./routes";

describe("route contract", () => {
  it("has unique canonical hrefs", () => {
    const hrefs = flattenRoutes().map((route) => route.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("has labels and titles for every route", () => {
    for (const route of flattenRoutes()) {
      expect(route.label, `${route.href} is missing label`).not.toBe("");
      expect(route.title, `${route.href} is missing title`).not.toBe("");
    }
  });

  it("maps aliases to canonical paths and redirects", () => {
    expect(getCanonicalPathname("/settings/org")).toBe("/settings/organization");
    expect(getRouteRedirects()).toContainEqual({
      source: "/settings/org",
      destination: "/settings/organization",
      statusCode: 301,
    });
  });

  it("builds semantic breadcrumbs from route definitions", () => {
    expect(getBreadcrumbItemsFromRoutes("/settings/organization")).toEqual([
      { href: "/dashboard", label: "Dashboard", isCurrent: false },
      { href: "/settings", label: "Settings", isCurrent: false },
      { href: "/settings/organization", label: "Organization", isCurrent: true },
    ]);
  });

  it("keeps public sitemap routes canonical", () => {
    const sitemapHrefs = getSitemapRoutes().map((route) => route.href);
    expect(sitemapHrefs).toEqual(["/", "/pricing"]);
    expect(sitemapHrefs).not.toContain("/settings/org");
  });
});
