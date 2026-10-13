import "server-only";

import { getServerEnv } from "@/lib/env";

/**
 * Server-side PostHog helper.
 *
 * Use this in Server Actions and Route Handlers to track events that
 * shouldn't be faked by users (e.g. subscription upgrades, payment events).
 *
 * Requires NEXT_PUBLIC_POSTHOG_KEY to be set. If absent, all calls are
 * no-ops — safe in dev/test.
 *
 * @public
 *
 * @example
 *   import { trackServerEvent } from "@/lib/analytics"
 *   await trackServerEvent("subscription_upgraded", userId, { plan: "pro" })
 */
export async function trackServerEvent(
  event: string,
  distinctId: string,
  properties?: Record<string, unknown>
): Promise<void> {
  const env = getServerEnv();
  const key = env.NEXT_PUBLIC_POSTHOG_KEY;
  const host = env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://app.posthog.com";

  if (!key) return;

  try {
    await fetch(`${host}/capture/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_key: key,
        event,
        distinct_id: distinctId,
        properties: {
          ...properties,
          $lib: "posthog-node",
        },
        timestamp: new Date().toISOString(),
      }),
      // Don't block the response — fire and forget with a short timeout.
      signal: AbortSignal.timeout(3000),
    });
  } catch {
    // Analytics must never break the app.
  }
}
