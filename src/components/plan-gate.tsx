import type { Route } from "next";
import Link from "next/link";

/**
 * <PlanGate> — conditionally renders children based on whether the user's
 * plan satisfies a feature requirement.
 *
 * @public
 *
 * Server Component: receive the `allowed` boolean from the calling Server
 * Component (computed via `getPlanLimits()`), so this component stays
 * pure and testable without database calls.
 *
 * @example
 * // In a Server Component
 * const limits = getPlanLimits(subscription?.product_id)
 *
 * return (
 *   <PlanGate allowed={limits.aiEnabled} feature="AI assistant">
 *     <AiChatPanel />
 *   </PlanGate>
 * )
 */
interface PlanGateProps {
  /** Whether the current user's plan allows access. */
  allowed: boolean;
  /** Human-readable feature name shown in the upgrade prompt. */
  feature: string;
  /** Content shown when access is granted. */
  children: React.ReactNode;
  /** Optional: override the upgrade CTA href (default: /pricing). */
  upgradeHref?: string;
}

export function PlanGate({
  allowed,
  feature,
  children,
  upgradeHref = "/pricing",
}: PlanGateProps): React.ReactElement {
  if (allowed) return <>{children}</>;

  return (
    <div className="border-border bg-muted/30 flex flex-col items-center gap-3 rounded-lg border border-dashed px-6 py-10 text-center">
      <span className="text-3xl">🔒</span>
      <div className="space-y-1">
        <p className="text-foreground text-sm font-semibold">{feature} is a paid feature</p>
        <p className="text-muted-foreground text-xs">
          Upgrade your plan to unlock {feature.toLowerCase()}.
        </p>
      </div>
      <Link
        href={upgradeHref as Route}
        className="bg-primary text-primary-foreground hover:bg-primary/90 mt-1 rounded-md px-4 py-2 text-sm font-medium transition-colors"
      >
        View plans →
      </Link>
    </div>
  );
}
