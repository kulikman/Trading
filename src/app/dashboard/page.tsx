/**
 * Placeholder dashboard route — referenced from `siteConfig.nav`.
 * Replace with your protected app shell when you add auth.
 *
 * Layout (`./layout.tsx`) already provides padding, breadcrumbs, and
 * the auth gate — this file is product content only.
 */
export default function DashboardPage(): React.ReactElement {
  return (
    <section>
      <h1 className="text-foreground text-2xl font-semibold tracking-tight">Dashboard</h1>
      <p className="text-muted-foreground mt-2 text-sm">
        Connect Supabase and build your product here.
      </p>
    </section>
  );
}
