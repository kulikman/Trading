import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV,
    // Capture 10% of transactions for performance monitoring in production.
    tracesSampleRate: process.env.NODE_ENV === "production" ? 0.1 : 1.0,
    // Capture 100% of sessions with errors.
    replaysOnErrorSampleRate: 1.0,
    // Capture 1% of sessions for session replay.
    replaysSessionSampleRate: 0.01,
    integrations: [
      Sentry.replayIntegration({
        maskAllText: true,
        blockAllMedia: true,
      }),
    ],
    // Filter out noisy browser errors.
    ignoreErrors: [
      "ResizeObserver loop limit exceeded",
      "ResizeObserver loop completed with undelivered notifications",
      /^No error$/,
    ],
  });
}
