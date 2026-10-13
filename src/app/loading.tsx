/**
 * Global loading skeleton.
 *
 * Shown by Next.js while a route segment is loading (e.g. during
 * `Suspense` boundaries or navigation with `loading.tsx` convention).
 *
 * Replace with a branded skeleton when customizing for your product.
 */
export default function Loading(): React.ReactElement {
  return (
    <div className="flex flex-1 items-center justify-center px-6 py-24">
      <div className="flex flex-col items-center gap-4">
        <div className="border-primary/30 border-t-primary size-8 animate-spin rounded-full border-2" />
        <p className="text-muted-foreground text-sm">Loading...</p>
      </div>
    </div>
  );
}
