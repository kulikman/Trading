import { Users, Shield, Crown } from "lucide-react";

import { requireUser } from "@/lib/auth";
import { getUserOrgs, OrgCreateForm } from "@/features/orgs";
import { createClient } from "@/lib/supabase/server";

export const metadata = {
  title: "Organizations",
  alternates: {
    canonical: "/settings/organization",
  },
};

const ROLE_LABEL: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
};

const ROLE_ICON: Record<string, React.ReactNode> = {
  owner: <Crown className="h-3 w-3" />,
  admin: <Shield className="h-3 w-3" />,
  member: <Users className="h-3 w-3" />,
};

export default async function OrganizationPage(): Promise<React.ReactElement> {
  await requireUser();
  const orgs = await getUserOrgs();

  // Load member counts for each org.
  const supabase = await createClient();
  const memberCounts = await Promise.all(
    orgs.map(async (org) => {
      const { count } = await supabase
        .from("org_members")
        .select("id", { count: "exact", head: true })
        .eq("org_id", org.orgId);
      return { orgId: org.orgId, count: count ?? 0 };
    })
  );
  const countMap = Object.fromEntries(memberCounts.map((m) => [m.orgId, m.count]));

  return (
    <section className="flex flex-col gap-8">
      <div>
        <h1 className="text-foreground text-2xl font-semibold tracking-tight">Organizations</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Manage your teams. Each org has its own members and billing.
        </p>
      </div>

      {orgs.length > 0 && (
        <div className="flex flex-col gap-3">
          {orgs.map((org) => (
            <div
              key={org.orgId}
              className="border-border flex items-center justify-between rounded-xl border px-5 py-4"
            >
              <div className="flex flex-col gap-0.5">
                <p className="text-foreground font-medium">{org.orgName}</p>
                <p className="text-muted-foreground text-xs">
                  /{org.orgSlug} · {countMap[org.orgId] ?? 0} member
                  {(countMap[org.orgId] ?? 0) === 1 ? "" : "s"}
                </p>
              </div>
              <span className="text-muted-foreground bg-muted flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium">
                {ROLE_ICON[org.role]}
                {ROLE_LABEL[org.role] ?? org.role}
              </span>
            </div>
          ))}
        </div>
      )}

      {orgs.length === 0 && (
        <div className="border-border bg-muted/30 rounded-xl border border-dashed px-6 py-10 text-center">
          <Users className="text-muted-foreground mx-auto mb-3 h-8 w-8" />
          <p className="text-foreground text-sm font-medium">No organizations yet</p>
          <p className="text-muted-foreground mt-1 text-xs">
            Create one to collaborate with your team.
          </p>
        </div>
      )}

      <div className="border-border rounded-xl border p-6">
        <h2 className="text-foreground mb-4 text-base font-semibold">Create organization</h2>
        <OrgCreateForm />
      </div>
    </section>
  );
}
