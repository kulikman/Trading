"use client";

import Link from "next/link";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { logger } from "@/lib/logger";

/**
 * Global error boundary.
 *
 * Catches unhandled errors in the component tree. Next.js renders this
 * automatically when a Server Component or Client Component throws.
 *
 * In production, wire `reportError` to your error tracking service
 * (Sentry, LogRocket, etc.) to get alerts.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): React.ReactElement {
  useEffect(() => {
    logger.error("unhandled error in client tree", error, { digest: error.digest });

    // Report to Sentry when configured.
    import("@sentry/nextjs")
      .then(({ captureException }) => captureException(error))
      .catch(() => void 0);
  }, [error]);

  return (
    <div className="flex flex-1 items-center justify-center px-6 py-24">
      <div className="text-center">
        <p className="text-destructive text-sm font-semibold tracking-wider uppercase">Error</p>
        <h1 className="text-foreground mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Something went wrong
        </h1>
        <p className="text-muted-foreground mt-4 max-w-md text-base leading-7">
          An unexpected error occurred. Our team has been notified. You can try again or go back to
          the home page.
        </p>
        {error.digest && (
          <p className="text-muted-foreground/60 mt-2 font-mono text-xs">
            Error ID: {error.digest}
          </p>
        )}
        <div className="mt-8 flex items-center justify-center gap-3">
          <Button onClick={reset} variant="default">
            Try again
          </Button>
          <Button variant="outline" asChild>
            <Link href="/">Back to home</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
