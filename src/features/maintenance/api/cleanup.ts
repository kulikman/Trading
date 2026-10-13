import "server-only";

import { createAdminClient } from "@/lib/supabase/admin";
import { logger } from "@/lib/logger";

export interface CleanupResult {
  notificationsDeleted?: number;
  expiredInvitesDeleted?: number;
}

/**
 * Delete stale records owned by feature tables.
 * Intended for trusted cron routes only.
 */
export async function runScheduledCleanup(now = new Date()): Promise<CleanupResult> {
  const supabase = createAdminClient();
  const results: CleanupResult = {};

  const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString();
  const { error: notifError, count: notifCount } = await supabase
    .from("notifications")
    .delete({ count: "exact" })
    .eq("read", true)
    .lt("created_at", thirtyDaysAgo);

  if (notifError) {
    logger.error("cron/cleanup: notifications delete failed", notifError);
  } else {
    results.notificationsDeleted = notifCount ?? 0;
  }

  const { error: inviteError, count: inviteCount } = await supabase
    .from("org_invites")
    .delete({ count: "exact" })
    .lt("expires_at", now.toISOString())
    .is("accepted_at", null);

  if (inviteError) {
    logger.error("cron/cleanup: org_invites delete failed", inviteError);
  } else {
    results.expiredInvitesDeleted = inviteCount ?? 0;
  }

  logger.info("cron/cleanup: complete", { ...results });
  return results;
}
