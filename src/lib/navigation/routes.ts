import { routes, type RouteDefinition, type RouteTree } from "@/config/routes";

export interface FlatRoute extends Omit<RouteDefinition, "children"> {
  key: string;
  parentHref: string | null;
}

export interface BreadcrumbRouteItem {
  href: string;
  label: string;
  isCurrent: boolean;
}

export function flattenRoutes(tree: RouteTree = routes): FlatRoute[] {
  return flattenRouteTree(tree);
}

export function getRouteByHref(href: string): FlatRoute | null {
  return flattenRoutes().find((route) => route.href === href) ?? null;
}

export function getCanonicalPathname(pathname: string): string {
  const aliasOwner = flattenRoutes().find((route) => route.aliases?.includes(pathname));
  return aliasOwner?.href ?? pathname;
}

export function getRouteRedirects(): Array<{
  source: string;
  destination: string;
  statusCode: 301;
}> {
  return flattenRoutes().flatMap((route) =>
    (route.aliases ?? []).map((source) => ({
      source,
      destination: route.href,
      statusCode: 301 as const,
    }))
  );
}

export function getSitemapRoutes(): FlatRoute[] {
  return flattenRoutes().filter((route) => route.public && route.sitemap);
}

export function getBreadcrumbItemsFromRoutes(pathname: string): BreadcrumbRouteItem[] {
  const canonicalPathname = getCanonicalPathname(pathname);

  if (canonicalPathname === "/" || canonicalPathname === "/dashboard") {
    return [];
  }

  const route = getRouteByHref(canonicalPathname);
  if (!route) return [];

  const trail = buildTrail(route);
  if (trail.length <= 1) return [];

  return trail.map((item, index) => ({
    href: item.href,
    label: item.label,
    isCurrent: index === trail.length - 1,
  }));
}

function buildTrail(route: FlatRoute): FlatRoute[] {
  const trail: FlatRoute[] = [];
  let current: FlatRoute | null = route;

  while (current) {
    trail.unshift(current);
    current = current.parentHref ? getRouteByHref(current.parentHref) : null;
  }

  if (trail[0]?.href !== "/dashboard" && route.href.startsWith("/settings")) {
    const dashboard = getRouteByHref("/dashboard");
    if (dashboard) trail.unshift(dashboard);
  }

  return trail;
}

function flattenRouteTree(
  tree: RouteTree,
  parentHref: string | null = null,
  parentKey = ""
): FlatRoute[] {
  return Object.entries(tree).flatMap(([key, route]) => {
    const fullKey = parentKey ? `${parentKey}.${key}` : key;
    const { children, ...flatRoute } = route;
    const current: FlatRoute = {
      ...flatRoute,
      key: fullKey,
      parentHref,
    };

    return [current, ...(children ? flattenRouteTree(children, route.href, fullKey) : [])];
  });
}
