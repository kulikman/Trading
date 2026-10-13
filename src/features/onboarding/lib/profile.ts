import "server-only";

import { createClient } from "@/lib/supabase/server";

export interface OnboardingStatus {
  completed: boolean;
  step: number;
}

export async function getOnboardingStatus(userId: string): Promise<OnboardingStatus> {
  const supabase = await createClient();
  const { data: profile } = await supabase
    .from("profiles")
    .select("onboarding_completed, onboarding_step")
    .eq("id", userId)
    .single();

  return {
    completed: profile?.onboarding_completed ?? false,
    step: profile?.onboarding_step ?? 0,
  };
}

export async function setOnboardingStep(params: {
  userId: string;
  step: number;
  completed: boolean;
}): Promise<void> {
  const supabase = await createClient();
  await supabase
    .from("profiles")
    .update({
      onboarding_step: params.step,
      ...(params.completed ? { onboarding_completed: true } : {}),
    })
    .eq("id", params.userId);
}

export async function completeOnboarding(userId: string): Promise<void> {
  const supabase = await createClient();
  await supabase.from("profiles").update({ onboarding_completed: true }).eq("id", userId);
}

export async function updateOnboardingProfile(
  userId: string,
  profile: {
    fullName: string;
    username: string;
  }
): Promise<void> {
  const supabase = await createClient();
  await supabase
    .from("profiles")
    .update({ full_name: profile.fullName, username: profile.username })
    .eq("id", userId);
}
