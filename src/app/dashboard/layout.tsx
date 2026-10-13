import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { requireUser } from "@/lib/auth";
import { getPublicMetadataEnv } from "@/lib/env";
import { getRecentNotifications, NotificationsBell } from "@/features/notifications";

/**
 * Dashboard shell — guards every nested route behind a valid Supabase session.
 *
 * `requireUser()` calls `supabase.auth.getUser()` (revalidates against
 * Supabase Auth, not the cookie) and `redirect(ROUTES.login)` when the
 * user is signed out. The redirect throws `NEXT_REDIRECT`, so children
 * never render for unauthenticated requests.
 *
 * Also renders `<Breadcrumbs />` once — canonical place per CLAUDE.md
 * (#URL hierarchy).
 *
 * `dynamic = "force-dynamic"`: a protected route must never be statically
 * prerendered. Without this, `next build` tries to evaluate `requireUser()`
 * at build time and crashes when Supabase env vars are absent (CI,
 * placeholder envs). Auth-gated routes are inherently per-request.
 */
export const dynamic = "force-dynamic";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}): Promise<React.ReactElement> {
  const user = await requireUser();
  const notifications = await getRecentNotifications(user.id);
  const { NEXT_PUBLIC_APP_URL: baseUrl } = getPublicMetadataEnv();

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-4 py-6 sm:px-6 lg:px-8">
      <div className="mb-6 flex items-center justify-between">
        <Breadcrumbs baseUrl={baseUrl} />
        <NotificationsBell initialNotifications={notifications} userId={user.id} />
      </div>
      {children}
    </div>
  );
}
