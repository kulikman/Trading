import type { MetadataRoute } from "next";

import { getSitemapRoutes } from "@/lib/navigation/routes";
import { getPublicMetadataEnv } from "@/lib/env";

/**
 * Dynamic sitemap generator.
 *
 * Next.js calls this at build time (or on request if ISR/dynamic) to produce
 * `/sitemap.xml`. Static routes come from `src/config/routes.ts`; fetch
 * dynamic routes (blog posts, docs, products) from Supabase.
 *
 * @see https://nextjs.org/docs/app/api-reference/file-conventions/metadata/sitemap
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Public URL only — does not require Supabase keys at build time.
  const { NEXT_PUBLIC_APP_URL: baseUrl } = getPublicMetadataEnv();

  // ── Static routes from the route contract ────────────────────────────────
  const staticRoutes: MetadataRoute.Sitemap = getSitemapRoutes().map((route) => ({
    url: route.href === "/" ? baseUrl : `${baseUrl}${route.href}`,
    lastModified: new Date(),
    changeFrequency: route.href === "/" ? "monthly" : "weekly",
    priority: route.href === "/" ? 1 : 0.8,
  }));

  // ── Dynamic routes (example) ─────────────────────────────────────────────
  // Keep this file build-safe. If dynamic sitemap entries need database data,
  // fetch them through a server-only feature helper instead of importing
  // Supabase clients directly here.
  //
  // const posts = await getPublishedPostsForSitemap()
  //
  // const postRoutes: MetadataRoute.Sitemap = (posts ?? []).map((post) => ({
  //   url: `${baseUrl}/blog/${post.slug}`,
  //   lastModified: new Date(post.updated_at),
  //   changeFrequency: "weekly" as const,
  //   priority: 0.6,
  // }))

  return [
    ...staticRoutes,
    // ...postRoutes,
  ];
}
