/**
 * Onboarding feature — public API.
 *
 * External code imports only from this barrel.
 * Do NOT import from internal paths like @/features/onboarding/lib/...
 */
export { OnboardingWizard } from "./components/onboarding-wizard";
export { advanceOnboardingStep, skipOnboarding, saveOnboardingProfile } from "./api/actions";
export { getOnboardingStatus } from "./lib/profile";
export type { OnboardingStatus } from "./lib/profile";
export { ONBOARDING_STEPS, TOTAL_STEPS } from "./lib/steps";
export type { OnboardingStep } from "./lib/steps";
