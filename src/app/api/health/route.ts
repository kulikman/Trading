import { NextResponse } from "next/server";

/**
 * Health-check endpoint — used by uptime monitors (UptimeRobot, BetterStack, etc.)
 * and Vercel deployment smoke tests.
 *
 * Returns 200 + JSON payload. No auth required — this must stay public.
 * Excluded from proxy.ts matcher (matches api/cron pattern, no session needed).
 *
 * Add deeper checks (DB ping, Redis ping) only if you have uptime SLAs that
 * depend on those services — otherwise keep it fast and stateless.
 *
 * @example GET /api/health
 * { "status": "ok", "ts": 1746441600000 }
 */
export async function GET(): Promise<NextResponse> {
  return NextResponse.json(
    { status: "ok", ts: Date.now() },
    {
      status: 200,
      headers: {
        // Tell CDNs and proxies: never cache this endpoint.
        "Cache-Control": "no-store, max-age=0",
      },
    }
  );
}
