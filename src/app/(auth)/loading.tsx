/**
 * Auth-scoped loading state. Shown during navigation between login,
 * signup, password-reset etc. — keeps the centered card visible.
 */
export default function AuthLoading(): React.ReactElement {
  return (
    <div className="flex flex-col gap-4">
      <div className="bg-muted mx-auto h-7 w-40 animate-pulse rounded" />
      <div className="bg-muted mx-auto h-4 w-56 animate-pulse rounded" />
      <div className="bg-muted mt-4 h-10 w-full animate-pulse rounded-md" />
      <div className="bg-muted h-10 w-full animate-pulse rounded-md" />
      <div className="bg-muted mt-2 h-11 w-full animate-pulse rounded-md" />
    </div>
  );
}
