export type NotificationKind = "info" | "success" | "warning" | "error";

export interface Notification {
  id: string;
  user_id: string;
  title: string;
  body: string | null;
  href: string | null;
  read: boolean;
  kind: NotificationKind;
  created_at: string;
}

export const KIND_ICON: Record<NotificationKind, string> = {
  info: "ℹ️",
  success: "✅",
  warning: "⚠️",
  error: "❌",
};
