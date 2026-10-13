import * as Sentry from "@sentry/nextjs";

/**
 * Next.js instrumentation hook — runs once per server start.
 * Validates env vars on startup and initialises Sentry server-side.
 *
 * @see https://nextjs.org/docs/app/api-reference/file-conventions/instrumentation
 */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  const { getServerEnv } = await import("@/lib/env");
  getServerEnv();

  if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
    await import("../sentry.server.config");
  }
}

/**
 * Next.js hook called on every server-side request error (RSC, Route Handlers, etc.).
 * Forwards to Sentry when DSN is configured.
 *
 * @see https://nextjs.org/docs/app/api-reference/file-conventions/instrumentation#onrequesterror
 */
export async function onRequestError(
  error: { digest?: string } & Error,
  request: { path: string; method: string },
  context: { routeType: string }
): Promise<void> {
  if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
    Sentry.captureException(error, {
      extra: { path: request.path, method: request.method, routeType: context.routeType },
    });
  }
}
