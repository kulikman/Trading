/**
 * Onboarding wizard step definitions.
 *
 * Add / remove / reorder steps here — the wizard renders them in order.
 * Each step defines its own validation (optional) so the Next button is
 * disabled until the user fills in required fields.
 */
export interface OnboardingStep {
  /** Unique key used as the URL hash and stored in `profiles.onboarding_step`. */
  id: string;
  /** Short label shown in the progress indicator. */
  title: string;
  /** Optional longer description shown below the title. */
  description?: string;
}

export const ONBOARDING_STEPS: OnboardingStep[] = [
  {
    id: "welcome",
    title: "Welcome",
    description: "Let's get you set up in under 2 minutes.",
  },
  {
    id: "profile",
    title: "Your profile",
    description: "Tell us a bit about yourself.",
  },
  {
    id: "workspace",
    title: "Workspace",
    description: "Name your workspace — you can change this later.",
  },
  {
    id: "plan",
    title: "Choose a plan",
    description: "Start free, upgrade any time.",
  },
  {
    id: "done",
    title: "You're all set!",
    description: "Your account is ready.",
  },
];

export const TOTAL_STEPS = ONBOARDING_STEPS.length;
