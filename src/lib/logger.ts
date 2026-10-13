/**
 * Minimal typed logger.
 *
 * Why not `console` directly?
 *   - `console.log` is silently dropped on Vercel production.
 *   - Stack traces from `console.error` lose `digest` correlation.
 *   - Switching to Sentry / Axiom / Logtail later means touching one file
 *     instead of hunting `console.*` calls across the codebase.
 *
 * Drop-in replace this file's body with `Sentry.captureException(...)` or
 * a structured logger (pino, winston) when you wire production tracking.
 *
 * Isomorphic: safe to import from both server and client code. The `error`
 * boundary in `src/app/error.tsx` forwards client-side throws here from
 * within `useEffect`.
 */

export interface LogContext {
  [key: string]: unknown;
}

interface LogEntry {
  level: "info" | "warn" | "error";
  message: string;
  context?: LogContext;
  error?: unknown;
  timestamp: string;
}

function emit(entry: LogEntry): void {
  // Stable JSON shape — easy to grep and easy to ship to a log aggregator.
  const payload = {
    level: entry.level,
    message: entry.message,
    timestamp: entry.timestamp,
    ...(entry.context && { context: entry.context }),
    ...(entry.error instanceof Error && {
      error: {
        name: entry.error.name,
        message: entry.error.message,
        stack: entry.error.stack,
      },
    }),
  };

  if (entry.level === "error") {
    console.error(JSON.stringify(payload));
  } else if (entry.level === "warn") {
    console.warn(JSON.stringify(payload));
  } else {
    // Info goes to stderr too in production — Vercel preserves it.
    console.warn(JSON.stringify(payload));
  }
}

export const logger = {
  info(message: string, context?: LogContext): void {
    emit({ level: "info", message, context, timestamp: new Date().toISOString() });
  },
  warn(message: string, context?: LogContext): void {
    emit({ level: "warn", message, context, timestamp: new Date().toISOString() });
  },
  error(message: string, error?: unknown, context?: LogContext): void {
    emit({ level: "error", message, context, error, timestamp: new Date().toISOString() });
    // TODO: when Sentry is wired:
    //   if (error instanceof Error) Sentry.captureException(error, { extra: context })
  },
};
