import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";

import { requireUser } from "@/lib/auth";
import { createAdminClient } from "@/lib/supabase/admin";
import { getOrCreateStripeCustomer, getStripe } from "@/lib/stripe";
import { getServerEnv } from "@/lib/env";
import { logger } from "@/lib/logger";
import { limit } from "@/lib/rate-limit";
import { getClientIpFromHeaders } from "@/lib/request-ip";

const bodySchema = z.object({
  priceId: z.string().min(1),
  quantity: z.number().int().positive().default(1),
});

/**
 * POST /api/stripe/checkout
 *
 * Creates a Stripe Checkout Session and returns the URL.
 * The client redirects the user to that URL.
 *
 * Body: { priceId: string, quantity?: number }
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const user = await requireUser();
  const env = getServerEnv();

  const ip = getClientIpFromHeaders(request.headers);
  const { success } = await limit(`stripe:checkout:${ip}`, { limit: 5, windowMs: 60_000 });
  if (!success) {
    return NextResponse.json(
      { error: "Too many requests. Try again in a minute." },
      { status: 429 }
    );
  }

  const rawBody = await request.json().catch(() => null);
  const parsed = bodySchema.safeParse(rawBody);
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0]?.message ?? "Invalid request" },
      { status: 400 }
    );
  }

  try {
    const supabase = createAdminClient();
    const { data: profile } = await supabase
      .from("profiles")
      .select("stripe_customer_id")
      .eq("id", user.id)
      .single();

    const customerId = await getOrCreateStripeCustomer({
      userId: user.id,
      email: user.email ?? "",
      existingCustomerId: profile?.stripe_customer_id,
    });

    // Persist customer ID if just created.
    if (!profile?.stripe_customer_id) {
      await supabase.from("profiles").update({ stripe_customer_id: customerId }).eq("id", user.id);
    }

    const stripe = getStripe();
    const session = await stripe.checkout.sessions.create({
      customer: customerId,
      mode: "subscription",
      payment_method_types: ["card"],
      line_items: [{ price: parsed.data.priceId, quantity: parsed.data.quantity }],
      success_url: `${env.NEXT_PUBLIC_APP_URL}/settings/billing?success=true`,
      cancel_url: `${env.NEXT_PUBLIC_APP_URL}/settings/billing?canceled=true`,
      subscription_data: {
        metadata: { supabase_user_id: user.id },
      },
    });

    return NextResponse.json({ url: session.url });
  } catch (error) {
    logger.error("stripe checkout failed", error);
    return NextResponse.json({ error: "Failed to create checkout session" }, { status: 500 });
  }
}
