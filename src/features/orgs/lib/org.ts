import "server-only";

import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { ROUTES } from "@/lib/constants";
import type { OrgMembership, OrgRole } from "@/domain/org";

// Re-export domain types so existing imports via `@/features/orgs` keep working.
export type { OrgMembership, OrgRole };

/**
 * Return all orgs the current user belongs to, or [] when signed out.
 *
 * Pass `userId` when the caller has already authenticated (e.g. a Route Handler
 * that called `requireUser()`) to avoid a second `auth.getUser()` round-trip.
 */
export async function getUserOrgs(userId?: string): Promise<OrgMembership[]> {
  const supabase = await createClient();
  let resolvedUserId = userId;
  if (!resolvedUserId) {
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) return [];
    resolvedUserId = user.id;
  }

  const { data } = await supabase
    .from("org_members")
    .select("role, organizations(id, name, slug)")
    .eq("user_id", resolvedUserId);

  if (!data) return [];

  return data.flatMap((row) => {
    const org = Array.isArray(row.organizations) ? row.organizations[0] : row.organizations;
    if (!org) return [];
    return [{ orgId: org.id, orgName: org.name, orgSlug: org.slug, role: row.role }];
  });
}

/**
 * Return the current user's membership for a specific org slug.
 * Returns null if the user is not a member.
 */
export async function getOrgMembership(slug: string): Promise<OrgMembership | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const { data } = await supabase
    .from("org_members")
    .select("role, organizations!inner(id, name, slug)")
    .eq("user_id", user.id)
    .eq("organizations.slug", slug)
    .maybeSingle();

  if (!data) return null;

  const org = Array.isArray(data.organizations) ? data.organizations[0] : data.organizations;
  if (!org) return null;

  return { orgId: org.id, orgName: org.name, orgSlug: org.slug, role: data.role };
}

/**
 * Assert membership. Redirects to dashboard if not a member.
 */
export async function requireOrgMember(slug: string): Promise<OrgMembership> {
  const membership = await getOrgMembership(slug);
  if (!membership) redirect(ROUTES.dashboard);
  return membership;
}

/**
 * Assert owner or admin role.
 *
 * @public
 */
export async function requireOrgAdmin(slug: string): Promise<OrgMembership> {
  const membership = await requireOrgMember(slug);
  if (membership.role === "member") redirect(ROUTES.dashboard);
  return membership;
}

/**
 * Assert owner role.
 *
 * @public
 */
export async function requireOrgOwner(slug: string): Promise<OrgMembership> {
  const membership = await requireOrgMember(slug);
  if (membership.role !== "owner") redirect(ROUTES.dashboard);
  return membership;
}

/**
 * Create an org and auto-assign the creator as owner.
 * Uses admin client so the trigger fires with correct auth.uid().
 */
export async function createOrg(params: {
  name: string;
  slug: string;
  userId: string;
}): Promise<{ id: string; slug: string }> {
  const supabase = createAdminClient();

  const { data, error } = await supabase
    .from("organizations")
    .insert({ name: params.name, slug: params.slug })
    .select("id, slug")
    .single();

  if (error) throw error;

  // Manually insert owner membership (trigger runs as service role,
  // auth.uid() is null there — insert explicitly).
  const { error: membershipError } = await supabase
    .from("org_members")
    .insert({ org_id: data.id, user_id: params.userId, role: "owner" });

  if (membershipError) {
    await supabase.from("organizations").delete().eq("id", data.id);
    throw membershipError;
  }

  return data;
}
