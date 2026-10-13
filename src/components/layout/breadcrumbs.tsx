"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

import { cn } from "@/lib/utils";
import { getBreadcrumbItemsFromRoutes } from "@/lib/navigation/routes";

export interface BreadcrumbItem {
  href: string;
  label: string;
  isCurrent: boolean;
}

interface BreadcrumbsProps {
  /**
   * Resolve a dynamic segment (e.g. `[slug]`) to a readable label.
   * Called only by the fallback path when a route is not yet registered.
   * Return `null` to use the raw segment as-is.
   */
  resolveLabel?: (segment: string, segments: string[]) => string | null;
  /** Additional CSS classes on the outer `<nav>`. */
  className?: string;
  /** Absolute site origin used for BreadcrumbList structured data. */
  baseUrl?: string;
}

/**
 * Breadcrumb navigation that auto-generates from the current URL path.
 *
 * Renders: Dashboard › Companies › Acme Inc › Edit
 *
 * Usage:
 *   - Drop `<Breadcrumbs />` into any layout or page.
 *   - For dynamic routes, pass `resolveLabel` to map slugs to titles.
 *
 * @example
 *   // /docs/getting-started → Dashboard › Docs › Getting Started
 *   <Breadcrumbs resolveLabel={(seg) => seg.replace(/-/g, " ")} />
 *
 * @example
 *   // /projects/abc123 → Dashboard › Projects › My Project
 *   <Breadcrumbs resolveLabel={(seg) => projectMap[seg] ?? null} />
 */
export function Breadcrumbs({
  resolveLabel,
  className,
  baseUrl,
}: BreadcrumbsProps): React.ReactElement | null {
  const pathname = usePathname();

  const items = getBreadcrumbItems(pathname, { resolveLabel });
  if (items.length === 0) return null;

  return (
    <>
      <BreadcrumbJsonLd items={items} baseUrl={baseUrl} />
      <nav
        aria-label="Breadcrumb"
        className={cn("text-muted-foreground flex items-center gap-1.5 text-sm", className)}
      >
        <ol className="flex items-center gap-1.5">
          {items.map(({ href, label, isCurrent }) => (
            <Fragment key={href}>
              <li>
                {isCurrent ? (
                  <span className="text-foreground font-medium" aria-current="page">
                    {label}
                  </span>
                ) : (
                  <Link
                    href={{ pathname: href }}
                    className="hover:text-foreground transition-colors"
                  >
                    {label}
                  </Link>
                )}
              </li>
              {!isCurrent && (
                <li aria-hidden="true" className="text-muted-foreground/40 select-none">
                  ›
                </li>
              )}
            </Fragment>
          ))}
        </ol>
      </nav>
    </>
  );
}

interface GetBreadcrumbItemsOptions {
  resolveLabel?: (segment: string, segments: string[]) => string | null;
}

/**
 * Build breadcrumb items from the canonical route contract.
 *
 * Known routes are resolved through `src/config/routes.ts`. Unknown dynamic
 * routes fall back to segment formatting so early feature work still has
 * usable crumbs until the route is registered.
 */
export function getBreadcrumbItems(
  pathname: string,
  { resolveLabel }: GetBreadcrumbItemsOptions = {}
): BreadcrumbItem[] {
  if (pathname === "/" || pathname === "/dashboard" || pathname.startsWith("/settings")) {
    const routeItems = getBreadcrumbItemsFromRoutes(pathname);
    if (routeItems.length > 0) return routeItems;
    if (pathname === "/" || pathname === "/dashboard") return [];
  }

  const routeItems = getBreadcrumbItemsFromRoutes(pathname);
  if (routeItems.length > 0) return routeItems;

  const segments = pathname.split("/").filter(Boolean);
  const visibleSegments = segments.filter((s) => !s.startsWith("("));

  // First-level pages (lists from the sidebar) don't render breadcrumbs.
  if (visibleSegments.length <= 1) return [];

  const items: BreadcrumbItem[] = [{ href: "/dashboard", label: "Dashboard", isCurrent: false }];

  for (let index = 0; index < visibleSegments.length; index += 1) {
    const segment = visibleSegments[index];
    if (!segment) continue;
    const href = "/" + visibleSegments.slice(0, index + 1).join("/");
    const isCurrent = index === visibleSegments.length - 1;

    const label =
      resolveSpecialLabel(segment, visibleSegments) ??
      resolveLabel?.(segment, visibleSegments) ??
      formatSegment(segment);

    items.push({ href, label, isCurrent });
  }

  // Mark the last item as current (no link in UI)
  const last = items[items.length - 1];
  if (last) {
    items[items.length - 1] = { ...last, isCurrent: true };
  }

  return items;
}

function resolveSpecialLabel(segment: string, segments: string[]): string | null {
  if (segment === "edit") return "Edit";

  if (segment === "new") {
    const section = segments[0] ?? "";
    const sectionLabel = formatSegment(section);
    return `New ${singularize(sectionLabel)}`;
  }

  return null;
}

function singularize(label: string): string {
  if (label.endsWith("ies")) return label.slice(0, -3) + "y";
  if (label.endsWith("s") && label.length > 1) return label.slice(0, -1);
  return label;
}

/**
 * Converts a URL segment to a human-readable label.
 * `getting-started` → `Getting Started`
 * UUIDs are left as-is (they should be resolved via `resolveLabel`).
 */
function formatSegment(segment: string): string {
  return segment.replace(/-/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function BreadcrumbJsonLd({
  items,
  baseUrl,
}: {
  items: BreadcrumbItem[];
  baseUrl?: string;
}): React.ReactElement | null {
  if (!baseUrl) return null;

  const origin = baseUrl.replace(/\/$/, "");
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.label,
      item: `${origin}${item.href}`,
    })),
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }}
    />
  );
}
