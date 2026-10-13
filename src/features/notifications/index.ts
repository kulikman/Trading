/**
 * Notifications feature — public API.
 */
export { NotificationsBell } from "./components/notifications-bell";
export { markAsRead, markAllAsRead } from "./api/actions";
export { getRecentNotifications } from "./api/queries";
export { sendNotification } from "./api/send-notification";
export type { Notification, NotificationKind } from "./lib/types";
export { KIND_ICON } from "./lib/types";
