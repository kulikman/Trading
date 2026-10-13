"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { logger } from "@/lib/logger";

export default function SettingsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): React.ReactElement {
  useEffect(() => {
    logger.error("settings error", error, { digest: error.digest });
  }, [error]);

  return (
    <div className="border-destructive/30 bg-destructive/5 rounded-xl border p-8 text-center">
      <h2 className="text-foreground text-xl font-semibold">Something broke in settings</h2>
      <p className="text-muted-foreground mt-2 text-sm">
        {error.digest ? `Error ID: ${error.digest}` : "Try again, or refresh the page."}
      </p>
      <Button onClick={reset} variant="outline" className="mt-4">
        Try again
      </Button>
    </div>
  );
}
