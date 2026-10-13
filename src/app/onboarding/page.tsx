import { redirect } from "next/navigation";

import { getOnboardingStatus, OnboardingWizard } from "@/features/onboarding";
import { createClient } from "@/lib/supabase/server";

/**
 * /onboarding — multi-step setup wizard for new users.
 *
 * Access rules:
 *   - Unauthenticated → redirect to /login
 *   - Already completed → redirect to /dashboard
 */
export const dynamic = "force-dynamic";

export default async function OnboardingPage(): Promise<React.ReactElement> {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const onboarding = await getOnboardingStatus(user.id);

  if (onboarding.completed) redirect("/dashboard");

  return (
    <div className="bg-background flex min-h-screen items-center justify-center p-4">
      <OnboardingWizard currentStep={onboarding.step} />
    </div>
  );
}
