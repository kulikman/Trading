import { requireUser } from "@/lib/auth";
import { createAdminClient } from "@/lib/supabase/admin";
import { getServerEnv } from "@/lib/env";
import { BillingCard } from "@/features/billing";

export default async function BillingPage(): Promise<React.ReactElement> {
  const user = await requireUser();
  const supabase = createAdminClient();

  const [{ data: subscription }, env] = await Promise.all([
    supabase
      .from("subscriptions")
      .select("id, status, current_period_end, cancel_at_period_end")
      .eq("user_id", user.id)
      .in("status", ["active", "trialing"])
      .order("created_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
    Promise.resolve(getServerEnv()),
  ]);

  return (
    <section className="flex flex-col gap-6">
      <div>
        <h1 className="text-foreground text-2xl font-semibold tracking-tight">Billing</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Manage your subscription and payment methods.
        </p>
      </div>

      <BillingCard subscription={subscription} priceId={env.STRIPE_PRICE_ID_PRO} />
    </section>
  );
}
