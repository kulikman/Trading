import { NextResponse } from "next/server";

import { requireUser } from "@/lib/auth";
import { createAdminClient } from "@/lib/supabase/admin";
import { getStripe } from "@/lib/stripe";
import { getServerEnv } from "@/lib/env";
import { logger } from "@/lib/logger";

/**
 * POST /api/stripe/portal
 *
 * Creates a Stripe Customer Portal session and returns the URL.
 * Users are redirected there to manage their subscription, invoices,
 * and payment methods — no custom billing UI needed.
 */
export async function POST(): Promise<NextResponse> {
  const user = await requireUser();
  const env = getServerEnv();

  try {
    const supabase = createAdminClient();
    const { data: profile } = await supabase
      .from("profiles")
      .select("stripe_customer_id")
      .eq("id", user.id)
      .single();

    if (!profile?.stripe_customer_id) {
      return NextResponse.json({ error: "No billing account found" }, { status: 404 });
    }

    const stripe = getStripe();
    const session = await stripe.billingPortal.sessions.create({
      customer: profile.stripe_customer_id,
      return_url: `${env.NEXT_PUBLIC_APP_URL}/settings/billing`,
    });

    return NextResponse.json({ url: session.url });
  } catch (error) {
    logger.error("stripe portal failed", error);
    return NextResponse.json({ error: "Failed to open billing portal" }, { status: 500 });
  }
}
