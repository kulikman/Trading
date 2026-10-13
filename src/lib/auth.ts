import "server-only";

import { redirect } from "next/navigation";
import type { User } from "@supabase/supabase-js";

import { createClient } from "@/lib/supabase/server";
import { ROUTES } from "@/lib/constants";

/**
 * Resolve the current user, or `null` when signed out.
 *
 * Always uses `auth.getUser()` (not `getSession()`) — `getSession()` only
 * reads the cookie and can be forged or stale; `getUser()` revalidates
 * against Supabase Auth.
 */
export async function getUser(): Promise<User | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
}

/**
 * Use at the top of any protected Server Component, Server Action, or
 * Route Handler. Redirects to the login page when there is no session.
 *
 * @example
 *   export default async function DashboardPage() {
 *     const user = await requireUser()
 *     return <Welcome name={user.email} />
 *   }
 */
export async function requireUser(): Promise<User> {
  const user = await getUser();
  if (!user) redirect(ROUTES.login);
  return user;
}
