import "server-only";

import { createAdminClient } from "@/lib/supabase/admin";
import type { Notification, NotificationKind } from "../lib/types";

const notificationKinds = new Set<NotificationKind>(["info", "success", "warning", "error"]);

function toNotificationKind(kind: string): NotificationKind {
  return notificationKinds.has(kind as NotificationKind) ? (kind as NotificationKind) : "info";
}

export async function getRecentNotifications(userId: string): Promise<Notification[]> {
  const supabase = createAdminClient();
  const { data } = await supabase
    .from("notifications")
    .select("id, user_id, title, body, href, read, kind, created_at")
    .eq("user_id", userId)
    .order("created_at", { ascending: false })
    .limit(20);

  return (data ?? []).map((notification) => ({
    ...notification,
    kind: toNotificationKind(notification.kind),
  }));
}
