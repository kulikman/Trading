import "server-only";

import { createAdminClient } from "@/lib/supabase/admin";
import type { NotificationKind } from "../lib/types";

/**
 * Send a notification to a specific user.
 * Server-side only — uses the service-role key to bypass RLS.
 *
 * @public
 *
 * @example
 *   await sendNotification(userId, {
 *     title: "Payment received",
 *     body: "Your subscription is now active.",
 *     kind: "success",
 *     href: "/settings/billing",
 *   })
 */
export async function sendNotification(
  userId: string,
  payload: {
    title: string;
    body?: string;
    href?: string;
    kind?: NotificationKind;
  }
): Promise<void> {
  const admin = createAdminClient();

  await admin.from("notifications").insert({
    user_id: userId,
    title: payload.title,
    body: payload.body ?? null,
    href: payload.href ?? null,
    kind: payload.kind ?? "info",
  });
}
