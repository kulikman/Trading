"use client";

import posthog from "posthog-js";
import { PostHogProvider as PHProvider, usePostHog } from "posthog-js/react";
import { useEffect } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import { getPublicAnalyticsEnv } from "@/lib/env";

/**
 * Tracks SPA page views on every route change.
 * Must be rendered inside <Suspense> because useSearchParams suspends.
 */
function PageviewTracker(): null {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const ph = usePostHog();

  useEffect(() => {
    if (pathname) {
      const url = `${window.location.origin}${pathname}${searchParams?.toString() ? `?${searchParams.toString()}` : ""}`;
      ph.capture("$pageview", { $current_url: url });
    }
  }, [pathname, searchParams, ph]);

  return null;
}

/**
 * PostHog product-analytics provider.
 *
 * Initialised once on mount. Set NEXT_PUBLIC_POSTHOG_KEY to enable.
 * If the key is absent the provider is still rendered but PostHog stays
 * uninitialised — safe for local dev without a key.
 *
 * Usage:
 *   // Track an event anywhere in client code
 *   const ph = usePostHog()
 *   ph.capture("clicked_upgrade", { plan: "pro" })
 *
 *   // Identify after auth
 *   ph.identify(user.id, { email: user.email, plan: "free" })
 *
 *   // Reset on sign-out
 *   ph.reset()
 */
export function PostHogProvider({ children }: { children: React.ReactNode }): React.ReactElement {
  const env = getPublicAnalyticsEnv();
  const key = env.NEXT_PUBLIC_POSTHOG_KEY;
  const host = env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://app.posthog.com";

  useEffect(() => {
    if (!key) return;

    posthog.init(key, {
      api_host: host,
      // Capture pageviews manually via PageviewTracker so Next.js SPA
      // navigations are tracked correctly (not just hard reloads).
      capture_pageview: false,
      // Respect user privacy — disable session recording in dev.
      disable_session_recording: !key,
      // Persist cross-session identity in localStorage.
      persistence: "localStorage",
    });
  }, [key, host]);

  return <PHProvider client={posthog}>{children}</PHProvider>;
}

export { PageviewTracker };
