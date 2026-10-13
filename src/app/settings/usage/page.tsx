import { redirect } from "next/navigation";
import Link from "next/link";

import { createClient } from "@/lib/supabase/server";
import { ROUTES } from "@/lib/constants";
import { getPlanLimits, formatBytes, formatLimit } from "@/lib/plan-limits";

export const metadata = { title: "Usage" };

interface UsageRowProps {
  label: string;
  used: number | string;
  limit: number;
  formatFn?: (n: number) => string;
}

function UsageRow({
  label,
  used,
  limit,
  formatFn = formatLimit,
}: UsageRowProps): React.ReactElement {
  const usedNum = typeof used === "number" ? used : 0;
  const pct = isFinite(limit) && limit > 0 ? Math.min(100, (usedNum / limit) * 100) : 0;
  const isWarning = pct >= 80;
  const limitLabel = formatFn(limit);

  return (
    <div className="space-y-1.5 py-4 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between text-sm">
        <span className="text-foreground font-medium">{label}</span>
        <span className="text-muted-foreground">
          {typeof used === "number" ? formatFn(usedNum) : used} / {limitLabel}
        </span>
      </div>
      {isFinite(limit) && (
        <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
          <div
            className={[
              "h-full rounded-full transition-all",
              isWarning ? "bg-yellow-500" : "bg-primary",
            ].join(" ")}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

export default async function UsagePage(): Promise<React.ReactElement> {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  // Fetch active subscription
  const { data: subscription } = await supabase
    .from("subscriptions")
    .select("product_id, status, current_period_end")
    .eq("user_id", user.id)
    .in("status", ["active", "trialing"])
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  const limits = getPlanLimits(subscription?.product_id);

  // Real usage queries — expand as you add more resource tables.
  const [{ count: apiKeysCount }, { count: orgMembersCount }] = await Promise.all([
    // API keys owned by this user.
    supabase.from("api_keys").select("id", { count: "exact", head: true }).eq("user_id", user.id),
    // Team members: count members across all orgs the user owns.
    // Falls back to 1 (solo user) when no orgs exist.
    supabase
      .from("org_members")
      .select("id", { count: "exact", head: true })
      .eq("user_id", user.id),
  ]);

  const usage = {
    // Projects table not yet created — add real query when the table exists.
    projects: 0,
    // Org member count; 1 = just the user themselves (no team yet).
    members: Math.max(1, orgMembersCount ?? 1),
    // Storage tracked via Supabase Storage — add real query when buckets are wired.
    storageBytes: 0,
    // API key count is a proxy for active integrations; replace with a
    // dedicated api_calls log table for true per-month call tracking.
    apiCalls: apiKeysCount ?? 0,
  };

  const renewalDate = subscription?.current_period_end
    ? new Date(subscription.current_period_end).toLocaleDateString("en-US", {
        month: "long",
        day: "numeric",
        year: "numeric",
      })
    : null;

  return (
    <div className="mx-auto max-w-2xl space-y-8 px-4 py-10">
      <div>
        <h1 className="text-foreground text-2xl font-bold">Usage</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Current plan: <span className="text-foreground font-semibold">{limits.name}</span>
          {renewalDate && <span className="text-muted-foreground"> · Renews {renewalDate}</span>}
        </p>
      </div>

      <div className="border-border divide-border bg-card divide-y rounded-xl border p-6">
        <UsageRow label="Projects" used={usage.projects} limit={limits.maxProjects} />
        <UsageRow label="Team members" used={usage.members} limit={limits.maxMembers} />
        <UsageRow
          label="Storage"
          used={formatBytes(usage.storageBytes)}
          limit={limits.maxStorageBytes}
          formatFn={formatBytes}
        />
        <UsageRow
          label="API calls this month"
          used={usage.apiCalls}
          limit={limits.maxApiCallsPerMonth}
        />
      </div>

      {limits.name === "Free" && (
        <div className="border-primary/20 bg-primary/5 flex items-center justify-between rounded-lg border px-5 py-4">
          <div>
            <p className="text-foreground text-sm font-semibold">Unlock more with Pro</p>
            <p className="text-muted-foreground text-xs">
              Unlimited projects, 50 GB storage, AI features.
            </p>
          </div>
          <Link
            href={ROUTES.pricing}
            className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-4 py-2 text-sm font-medium transition-colors"
          >
            Upgrade →
          </Link>
        </div>
      )}
    </div>
  );
}
