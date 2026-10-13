import type { MetadataRoute } from "next";

import { getPublicMetadataEnv } from "@/lib/env";

/**
 * Dynamic robots.txt. Stays in sync with `sitemap.ts` because both read
 * the canonical app URL via `getPublicMetadataEnv()`.
 *
 * @see https://nextjs.org/docs/app/api-reference/file-conventions/metadata/robots
 */
export default function robots(): MetadataRoute.Robots {
  const { NEXT_PUBLIC_APP_URL: baseUrl } = getPublicMetadataEnv();

  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/", "/dashboard/"],
      },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
  };
}
