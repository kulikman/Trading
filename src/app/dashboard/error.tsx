"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { logger } from "@/lib/logger";

/**
 * Dashboard-scoped error boundary. A throw in any dashboard route falls
 * here instead of bubbling to the global `app/error.tsx`, so the header
 * and shell stay rendered.
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): React.ReactElement {
  useEffect(() => {
    logger.error("dashboard error", error, { digest: error.digest });
  }, [error]);

  return (
    <div className="border-destructive/30 bg-destructive/5 rounded-xl border p-8 text-center">
      <h2 className="text-foreground text-xl font-semibold">Something broke in the dashboard</h2>
      <p className="text-muted-foreground mt-2 text-sm">
        {error.digest ? `Error ID: ${error.digest}` : "Try again, or refresh the page."}
      </p>
      <Button onClick={reset} variant="outline" className="mt-4">
        Try again
      </Button>
    </div>
  );
}
