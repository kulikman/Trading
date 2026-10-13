"use client";

import { useEffect, useRef, useState } from "react";
import type { Route } from "next";
import Link from "next/link";

import { createClient } from "@/lib/supabase/client";
import { markAsRead, markAllAsRead } from "../api/actions";
import { KIND_ICON } from "../lib/types";
import type { Notification } from "../lib/types";

interface Props {
  /** Pre-fetched notifications from the Server Component. */
  initialNotifications: Notification[];
  userId: string;
}

function timeAgo(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

/**
 * Notification bell with real-time badge updates via Supabase Realtime.
 *
 * The Server Component that renders this component should fetch initial
 * notifications and pass them as `initialNotifications`.
 */
export function NotificationsBell({ initialNotifications, userId }: Props): React.ReactElement {
  const [notifications, setNotifications] = useState<Notification[]>(initialNotifications);
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const unreadCount = notifications.filter((n) => !n.read).length;

  // ── Supabase Realtime subscription ──────────────────────────────────────────
  useEffect(() => {
    const supabase = createClient();

    const channel = supabase
      .channel(`notifications:${userId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "notifications",
          filter: `user_id=eq.${userId}`,
        },
        (payload) => {
          setNotifications((prev) => [payload.new as Notification, ...prev]);
        }
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [userId]);

  // ── Close on outside click ───────────────────────────────────────────────────
  useEffect(() => {
    function handleClick(e: MouseEvent): void {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  async function handleMarkRead(id: string): Promise<void> {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    await markAsRead(id);
  }

  async function handleMarkAll(): Promise<void> {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    await markAllAsRead();
  }

  return (
    <div ref={panelRef} className="relative">
      {/* Bell button */}
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label={`Notifications${unreadCount > 0 ? `, ${unreadCount} unread` : ""}`}
        className="text-muted-foreground hover:text-foreground relative rounded-md p-1.5 transition-colors"
      >
        <svg
          className="size-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0"
          />
        </svg>
        {unreadCount > 0 && (
          <span className="bg-primary text-primary-foreground absolute -top-0.5 -right-0.5 flex size-4 items-center justify-center rounded-full text-[10px] leading-none font-bold">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="border-border bg-popover absolute right-0 z-50 mt-2 w-80 overflow-hidden rounded-xl border shadow-md">
          <div className="flex items-center justify-between px-4 py-3">
            <span className="text-foreground text-sm font-semibold">Notifications</span>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={handleMarkAll}
                className="text-muted-foreground hover:text-foreground text-xs transition-colors"
              >
                Mark all read
              </button>
            )}
          </div>

          <div className="divide-border max-h-96 divide-y overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="text-muted-foreground px-4 py-8 text-center text-sm">
                No notifications yet.
              </p>
            ) : (
              notifications.slice(0, 20).map((n) => (
                <div
                  key={n.id}
                  className={[
                    "flex gap-3 px-4 py-3 transition-colors",
                    !n.read ? "bg-primary/5" : "",
                  ].join(" ")}
                >
                  <span className="mt-0.5 text-base">{KIND_ICON[n.kind]}</span>
                  <div className="min-w-0 flex-1">
                    {n.href ? (
                      <Link
                        href={n.href as Route}
                        onClick={() => {
                          void handleMarkRead(n.id);
                          setOpen(false);
                        }}
                        className="text-foreground block text-sm font-medium hover:underline"
                      >
                        {n.title}
                      </Link>
                    ) : (
                      <p className="text-foreground text-sm font-medium">{n.title}</p>
                    )}
                    {n.body && <p className="text-muted-foreground mt-0.5 text-xs">{n.body}</p>}
                    <p className="text-muted-foreground mt-1 text-xs">{timeAgo(n.created_at)}</p>
                  </div>
                  {!n.read && (
                    <button
                      type="button"
                      onClick={() => void handleMarkRead(n.id)}
                      aria-label="Mark as read"
                      className="bg-primary mt-1 size-2 shrink-0 rounded-full"
                    />
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
