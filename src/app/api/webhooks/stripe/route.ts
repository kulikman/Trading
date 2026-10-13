import { NextResponse, type NextRequest } from "next/server";
import type Stripe from "stripe";

import { getStripe } from "@/lib/stripe";
import { createAdminClient } from "@/lib/supabase/admin";
import { getServerEnv } from "@/lib/env";
import { getPlanLimits } from "@/lib/plan-limits";
import { sendEmail } from "@/lib/email";
import { subscriptionConfirmedEmail, paymentFailedEmail } from "@/lib/email/templates";
import { logger } from "@/lib/logger";

/**
 * Stripe webhook receiver.
 *
 * Excluded from proxy matcher (no session refresh needed — Stripe uses
 * its own signature, not cookies).
 *
 * Handled events:
 *   - checkout.session.completed      → provision subscription + send confirmation email
 *   - customer.subscription.created   → sync (idempotent with updated)
 *   - customer.subscription.updated   → sync status changes
 *   - customer.subscription.deleted   → mark canceled
 *   - invoice.payment_failed          → send dunning email
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const env = getServerEnv();
  const signature = request.headers.get("stripe-signature");

  if (!signature) {
    logger.warn("stripe webhook: missing signature");
    return NextResponse.json({ error: "Missing signature" }, { status: 400 });
  }

  if (!env.STRIPE_WEBHOOK_SECRET) {
    logger.error("STRIPE_WEBHOOK_SECRET not configured");
    return NextResponse.json({ error: "Webhook not configured" }, { status: 500 });
  }

  let event: Stripe.Event;
  try {
    const body = await request.text();
    const stripe = getStripe();
    event = stripe.webhooks.constructEvent(body, signature, env.STRIPE_WEBHOOK_SECRET);
  } catch (error) {
    logger.warn("stripe webhook: signature verification failed", { error });
    return NextResponse.json({ error: "Invalid signature" }, { status: 400 });
  }

  try {
    await handleEvent(event);
  } catch (error) {
    logger.error("stripe webhook: handler failed", error, { type: event.type });
    return NextResponse.json({ error: "Handler failed" }, { status: 500 });
  }

  return NextResponse.json({ received: true });
}

async function handleEvent(event: Stripe.Event): Promise<void> {
  const supabase = createAdminClient();

  switch (event.type) {
    case "checkout.session.completed": {
      const session = event.data.object as Stripe.Checkout.Session;
      if (session.mode !== "subscription" || !session.subscription) break;

      const stripe = getStripe();
      const subscription = await stripe.subscriptions.retrieve(session.subscription as string);
      await upsertSubscription(subscription, supabase);
      logger.info("stripe: subscription created", { id: subscription.id });

      // Send subscription confirmation email.
      const userId = subscription.metadata["supabase_user_id"];
      if (userId) {
        const { data: profile } = await supabase
          .from("profiles")
          .select("full_name")
          .eq("id", userId)
          .maybeSingle();
        const { data: authUser } = await supabase.auth.admin.getUserById(userId);
        const email = authUser.user?.email;
        if (email) {
          const item = subscription.items.data[0];
          const periodEnd = item?.current_period_end;
          const renewalDate = periodEnd
            ? new Date(periodEnd * 1000).toLocaleDateString("en-US", {
                month: "long",
                day: "numeric",
                year: "numeric",
              })
            : "—";
          const planLimits = getPlanLimits(
            typeof item?.price.product === "string" ? item.price.product : null
          );
          const env = getServerEnv();
          const portalUrl = `${env.NEXT_PUBLIC_APP_URL}/settings/billing`;
          const tpl = subscriptionConfirmedEmail({
            name: profile?.full_name ?? email,
            planName: planLimits.name,
            renewalDate,
            portalUrl,
          });
          await sendEmail({ to: email, ...tpl });
        }
      }
      break;
    }

    case "customer.subscription.created":
    case "customer.subscription.updated": {
      // Both events deliver a fully-formed Stripe.Subscription. Treat them
      // identically — upsert is idempotent and lets us survive event reordering
      // (Stripe doesn't guarantee delivery order across event types).
      const subscription = event.data.object as Stripe.Subscription;
      await upsertSubscription(subscription, supabase);
      logger.info("stripe: subscription synced", {
        id: subscription.id,
        type: event.type,
        status: subscription.status,
      });
      break;
    }

    case "customer.subscription.deleted": {
      const subscription = event.data.object as Stripe.Subscription;
      await upsertSubscription(subscription, supabase);
      logger.info("stripe: subscription deleted", { id: subscription.id });
      break;
    }

    case "invoice.payment_failed": {
      const invoice = event.data.object as Stripe.Invoice;
      const customerId =
        typeof invoice.customer === "string" ? invoice.customer : invoice.customer?.id;
      if (!customerId) break;

      // Look up user by Stripe customer ID.
      const { data: profile } = await supabase
        .from("profiles")
        .select("id, full_name")
        .eq("stripe_customer_id", customerId)
        .maybeSingle();
      if (!profile) break;

      const { data: authUser } = await supabase.auth.admin.getUserById(profile.id);
      const email = authUser.user?.email;
      if (email) {
        const env = getServerEnv();
        const portalUrl = `${env.NEXT_PUBLIC_APP_URL}/settings/billing`;
        const tpl = paymentFailedEmail({ name: profile.full_name ?? email, portalUrl });
        await sendEmail({ to: email, ...tpl });
        logger.info("stripe: payment failed email sent", { customerId });
      }
      break;
    }

    default:
      logger.info("stripe: unhandled event", { type: event.type });
  }
}

async function upsertSubscription(
  subscription: Stripe.Subscription,
  supabase: ReturnType<typeof createAdminClient>
): Promise<void> {
  const userId = subscription.metadata["supabase_user_id"];
  if (!userId) {
    logger.warn("stripe: subscription missing supabase_user_id metadata", { id: subscription.id });
    return;
  }

  const item = subscription.items.data[0];
  // In Stripe v22 (dahlia), period fields live on SubscriptionItem, not Subscription.
  const periodStart = item?.current_period_start;
  const periodEnd = item?.current_period_end;

  const row = {
    id: subscription.id,
    user_id: userId,
    status: subscription.status,
    price_id: item?.price.id ?? null,
    product_id: typeof item?.price.product === "string" ? item.price.product : null,
    quantity: item?.quantity ?? 1,
    cancel_at_period_end: subscription.cancel_at_period_end,
    current_period_start: periodStart ? new Date(periodStart * 1000).toISOString() : null,
    current_period_end: periodEnd ? new Date(periodEnd * 1000).toISOString() : null,
    trial_start: subscription.trial_start
      ? new Date(subscription.trial_start * 1000).toISOString()
      : null,
    trial_end: subscription.trial_end
      ? new Date(subscription.trial_end * 1000).toISOString()
      : null,
    canceled_at: subscription.canceled_at
      ? new Date(subscription.canceled_at * 1000).toISOString()
      : null,
  };

  const { error } = await supabase.from("subscriptions").upsert(row);

  if (error) throw error;
}
