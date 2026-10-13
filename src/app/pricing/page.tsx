import type { Metadata, Route } from "next";
import Link from "next/link";
import { Check } from "lucide-react";

import { siteConfig } from "@/config/site";
import { ROUTES } from "@/lib/constants";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Pricing",
  description: `Simple, transparent pricing for ${siteConfig.name}.`,
  alternates: {
    canonical: "/pricing",
  },
};

/**
 * Pricing tiers.
 *
 * SETUP: Replace `priceId` with your real Stripe price IDs before going live.
 * Each priceId is passed to POST /api/stripe/checkout — the route handles the rest.
 *
 * Keep `priceId: null` for the Free tier (no checkout needed).
 */
const TIERS = [
  {
    name: "Free",
    price: 0,
    description: "Everything you need to get started.",
    priceId: null,
    cta: "Get started",
    href: ROUTES.signup,
    features: ["Up to 3 projects", "1 team member", "Community support", "Basic analytics"],
    highlighted: false,
  },
  {
    name: "Pro",
    price: 29,
    description: "For teams shipping at full speed.",
    // SETUP: replace with your Stripe price ID (e.g. price_1Abc123...)
    priceId: "PRICE_ID_PRO_MONTHLY",
    cta: "Upgrade to Pro",
    href: ROUTES.dashboard,
    features: [
      "Unlimited projects",
      "Up to 10 team members",
      "Priority support",
      "Advanced analytics",
      "Custom domain",
      "API access",
    ],
    highlighted: true,
  },
  {
    name: "Enterprise",
    price: null,
    description: "Compliance, SLAs, and dedicated support.",
    priceId: null,
    cta: "Contact us",
    href: "mailto:hello@example.com",
    features: [
      "Everything in Pro",
      "Unlimited team members",
      "SSO / SAML",
      "99.99% SLA",
      "Dedicated success manager",
      "Custom contract",
    ],
    highlighted: false,
  },
] as const;

export default function PricingPage(): React.ReactElement {
  return (
    <div className="bg-background flex flex-1 flex-col items-center px-6 py-20">
      <div className="w-full max-w-5xl">
        {/* Header */}
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h1 className="text-foreground text-4xl font-semibold tracking-tight sm:text-5xl">
            Simple, transparent pricing
          </h1>
          <p className="text-muted-foreground mt-4 text-lg leading-7">
            Start for free. Upgrade when you need more. No hidden fees.
          </p>
        </div>

        {/* Tier cards */}
        <div className="grid gap-8 sm:grid-cols-3">
          {TIERS.map((tier) => (
            <PricingCard key={tier.name} tier={tier} />
          ))}
        </div>

        {/* FAQ teaser */}
        <p className="text-muted-foreground mt-16 text-center text-sm">
          Questions?{" "}
          <a
            href="mailto:hello@example.com"
            className="text-foreground underline underline-offset-4 hover:no-underline"
          >
            Talk to us
          </a>{" "}
          — we usually reply within one business day.
        </p>
      </div>
    </div>
  );
}

interface Tier {
  name: string;
  price: number | null;
  description: string;
  priceId: string | null;
  cta: string;
  href: string;
  features: readonly string[];
  highlighted: boolean;
}

interface PricingCardProps {
  tier: Tier;
}

function PricingCard({ tier }: PricingCardProps): React.ReactElement {
  const isExternal = tier.href.startsWith("mailto:") || tier.href.startsWith("http");

  return (
    <div
      className={[
        "relative flex flex-col rounded-2xl border p-8",
        tier.highlighted
          ? "border-primary bg-primary text-primary-foreground shadow-lg"
          : "border-border bg-card text-card-foreground",
      ].join(" ")}
    >
      {tier.highlighted && (
        <span className="bg-primary-foreground text-primary absolute -top-3 left-1/2 -translate-x-1/2 rounded-full px-3 py-0.5 text-xs font-semibold">
          Most popular
        </span>
      )}

      <div className="mb-6">
        <h2 className="text-lg font-semibold">{tier.name}</h2>
        <p
          className={[
            "mt-1 text-sm",
            tier.highlighted ? "opacity-80" : "text-muted-foreground",
          ].join(" ")}
        >
          {tier.description}
        </p>
        <div className="mt-4 flex items-baseline gap-1">
          {tier.price === null ? (
            <span className="text-3xl font-bold">Custom</span>
          ) : (
            <>
              <span className="text-4xl font-bold">${tier.price}</span>
              <span
                className={[
                  "text-sm",
                  tier.highlighted ? "opacity-70" : "text-muted-foreground",
                ].join(" ")}
              >
                / month
              </span>
            </>
          )}
        </div>
      </div>

      <ul className="mb-8 flex flex-1 flex-col gap-3">
        {tier.features.map((feature) => (
          <li key={feature} className="flex items-center gap-2.5 text-sm">
            <Check
              className={["size-4 shrink-0", tier.highlighted ? "opacity-90" : "text-primary"].join(
                " "
              )}
              aria-hidden
            />
            {feature}
          </li>
        ))}
      </ul>

      {isExternal ? (
        <a href={tier.href}>
          <Button className="w-full" variant={tier.highlighted ? "secondary" : "default"}>
            {tier.cta}
          </Button>
        </a>
      ) : (
        <Link href={tier.href as Route}>
          <Button className="w-full" variant={tier.highlighted ? "secondary" : "default"}>
            {tier.cta}
          </Button>
        </Link>
      )}
    </div>
  );
}
