/**
 * Dashboard loading skeleton. Used by Next.js Suspense during navigation
 * and during streaming Server Component data.
 *
 * Replace the placeholder cards with real shapes that match your UI —
 * skeletons that look like the eventual content reduce CLS.
 */
export default function DashboardLoading(): React.ReactElement {
  return (
    <div className="space-y-4">
      <div className="bg-muted h-8 w-48 animate-pulse rounded-md" />
      <div className="bg-muted h-4 w-72 animate-pulse rounded" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="border-border bg-card rounded-xl border p-6">
            <div className="bg-muted mb-3 h-4 w-24 animate-pulse rounded" />
            <div className="bg-muted h-8 w-32 animate-pulse rounded" />
          </div>
        ))}
      </div>
    </div>
  );
}
