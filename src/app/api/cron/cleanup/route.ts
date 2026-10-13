import { NextResponse, type NextRequest } from "next/server";

import { runScheduledCleanup } from "@/features/maintenance";
import { getServerEnv } from "@/lib/env";
import { logger } from "@/lib/logger";

/**
 * Scheduled cleanup job — runs daily via Vercel Cron.
 *
 * Tasks:
 *   1. Delete read notifications older than 30 days.
 *   2. Delete expired org invites.
 *
 * Schedule: daily at 03:00 UTC (low-traffic window).
 * Vercel cron entry (vercel.json):
 *   { "path": "/api/cron/cleanup", "schedule": "0 3 * * *" }
 *
 * Authorization: Vercel sends `Authorization: Bearer ${CRON_SECRET}` on
 * every cron-triggered request. Set CRON_SECRET in your Vercel project env.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const env = getServerEnv();
  const auth = request.headers.get("authorization");

  if (!env.CRON_SECRET || auth !== `Bearer ${env.CRON_SECRET}`) {
    logger.warn("cron/cleanup: unauthorized request");
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const results = await runScheduledCleanup();
  return NextResponse.json({ ok: true, ...results });
}
