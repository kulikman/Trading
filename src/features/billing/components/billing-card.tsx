"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ROUTES } from "@/lib/constants";

interface Subscription {
  id: string;
  status: string;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
}

interface BillingCardProps {
  subscription: Subscription | null;
  /** Stripe price ID for the Pro plan (from STRIPE_PRICE_ID_PRO env var). */
  priceId?: string;
}

export function BillingCard({ subscription, priceId }: BillingCardProps): React.ReactElement {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function openPortal(): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/stripe/portal", { method: "POST" });
      const data = (await res.json()) as { url?: string; error?: string };
      if (!res.ok || !data.url) throw new Error(data.error ?? "Failed to open portal");
      window.location.href = data.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setLoading(false);
    }
  }

  async function openCheckout(priceId: string): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/stripe/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ priceId }),
      });
      const data = (await res.json()) as { url?: string; error?: string };
      if (!res.ok || !data.url) throw new Error(data.error ?? "Failed to start checkout");
      window.location.href = data.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setLoading(false);
    }
  }

  if (subscription) {
    const periodEnd = subscription.current_period_end
      ? new Date(subscription.current_period_end).toLocaleDateString()
      : null;

    return (
      <div className="border-border flex flex-col gap-4 rounded-xl border p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-foreground font-medium capitalize">{subscription.status} plan</p>
            {periodEnd && (
              <p className="text-muted-foreground text-sm">
                {subscription.cancel_at_period_end
                  ? `Cancels on ${periodEnd}`
                  : `Renews on ${periodEnd}`}
              </p>
            )}
          </div>
          <span className="bg-primary/10 text-primary rounded-full px-2.5 py-0.5 text-xs font-medium capitalize">
            {subscription.status}
          </span>
        </div>

        {error && <p className="text-destructive text-sm">{error}</p>}

        <Button onClick={openPortal} disabled={loading} variant="outline">
          {loading ? "Loading…" : "Manage subscription"}
        </Button>
      </div>
    );
  }

  return (
    <div className="border-border flex flex-col gap-4 rounded-xl border p-6">
      <div>
        <p className="text-foreground font-medium">Free plan</p>
        <p className="text-muted-foreground text-sm">Upgrade to unlock all features.</p>
      </div>

      {error && <p className="text-destructive text-sm">{error}</p>}

      {priceId ? (
        <Button onClick={() => openCheckout(priceId)} disabled={loading}>
          {loading ? "Loading…" : "Upgrade to Pro"}
        </Button>
      ) : (
        <Button asChild variant="outline">
          <Link href={ROUTES.pricing}>View plans →</Link>
        </Button>
      )}
    </div>
  );
}
