import { NextResponse, type NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/middleware";
import { buildSecurityHeaders } from "@/lib/security-headers";

/**
 * Next.js 16 Proxy (replaces deprecated middleware.ts).
 *
 * Runs on the Node.js runtime before any route is rendered. Does two things:
 *   1. Refreshes the Supabase auth session cookie so server components see a
 *      valid user. Without this, sessions expire silently and RLS queries
 *      start failing in a hard-to-debug way.
 *   2. Attaches security headers (CSP, HSTS, X-Frame-Options, etc.) to every
 *      response. Centralized here so individual routes can't forget them.
 *
 * Do NOT do heavy auth logic here — that belongs in Server Components,
 * Server Actions, or Route Handlers via `supabase.auth.getUser()`.
 */
export async function proxy(request: NextRequest): Promise<NextResponse> {
  const response = await updateSession(request);
  const headers = buildSecurityHeaders({
    isDev: process.env.NODE_ENV !== "production",
  });

  for (const [key, value] of Object.entries(headers)) {
    response.headers.set(key, value);
  }

  return response;
}

export const config = {
  /**
   * Match everything except:
   *   - _next/static, _next/image  — static assets / image optimization
   *   - favicon.ico, sitemap.xml, robots.txt, opengraph-image, icon — file conventions
   *   - api/webhooks/*             — external webhooks have no cookies; refreshing
   *                                  Supabase session on every Stripe event wastes
   *                                  a roundtrip and can race with the cookie store
   *   - api/cron/*                 — internal scheduled jobs use CRON_SECRET, not session
   *   - common static file extensions
   *
   * Auth-bearing API routes (`/api/auth/*`, `/api/me/*`, etc.) **are** matched —
   * they need the session refresh.
   *
   * @see https://supabase.com/docs/guides/auth/server-side/nextjs
   */
  matcher: [
    "/((?!_next/static|_next/image|favicon\\.ico|sitemap\\.xml|robots\\.txt|opengraph-image|icon|api/webhooks|api/cron|.*\\.(?:svg|png|jpg|jpeg|gif|webp|avif|ico|woff|woff2|ttf)$).*)",
  ],
};
