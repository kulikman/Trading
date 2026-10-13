import "server-only";

import { createAdminClient } from "@/lib/supabase/admin";
import { logger } from "@/lib/logger";
import type { Json } from "@/types/database";

export type AuditAction =
  | "auth.login"
  | "auth.logout"
  | "auth.signup"
  | "auth.password_reset_requested"
  | "auth.password_reset_completed"
  | "billing.checkout_started"
  | "billing.subscription_created"
  | "billing.subscription_updated"
  | "billing.subscription_canceled"
  | "profile.updated"
  | "profile.deleted"
  | "org.created"
  | "org.deleted";

interface AuditParams {
  userId: string | null;
  action: AuditAction;
  /** e.g. "subscription:sub_xxx", "profile:uuid" */
  resource?: string;
  /** Extra structured data: IP, user-agent, diff, etc. */
  metadata?: Json;
}

/**
 * Write an immutable audit log entry via the service-role client.
 *
 * Never throws — a failed audit write must not crash the caller.
 * The entry is best-effort; callers should not depend on it for correctness.
 *
 * @example
 *   await writeAuditLog({ userId: user.id, action: "auth.login", metadata: { ip } })
 */
export async function writeAuditLog({
  userId,
  action,
  resource,
  metadata = {},
}: AuditParams): Promise<void> {
  try {
    const supabase = createAdminClient();
    const { error } = await supabase.from("audit_logs").insert({
      user_id: userId,
      action,
      resource: resource ?? null,
      metadata,
    });
    if (error) throw error;
  } catch (error) {
    // Audit failure must never crash the caller.
    logger.error("audit log write failed", error, { action, userId });
  }
}
