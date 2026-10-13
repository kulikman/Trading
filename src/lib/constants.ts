import { siteConfig } from "@/config/site";
import { routes } from "@/config/routes";

/**
 * Static display-name fallback for places that can't await `getClientEnv()`
 * (inline copy in default metadata, error pages, etc.). For runtime-tunable
 * values read `getClientEnv().NEXT_PUBLIC_APP_NAME` instead.
 *
 * @public
 */
export const APP_NAME: string = siteConfig.name;

/**
 * Canonical route map.
 *
 * Only routes that physically exist in `src/app/` belong here — Next 16
 * typed routes will fail `tsc` if you reference a non-existent path.
 * When you add a new route, register it first in `src/config/routes.ts`.
 *
 * Rules:
 *   - Every nested route must have a navigable parent (no dead intermediate URLs).
 *   - Use descriptive nouns as segments, not abbreviations or numeric IDs alone.
 *   - Dynamic segments: `/projects/[id]`, never `/p/[id]`.
 */
export const ROUTES = {
  home: routes.home.href,
  pricing: routes.pricing.href,
  login: routes.login.href,
  signup: routes.signup.href,
  forgotPassword: routes.forgotPassword.href,
  resetPassword: routes.resetPassword.href,
  dashboard: routes.dashboard.href,
  onboarding: routes.onboarding.href,
  settings: routes.settings.href,
  settingsBilling: routes.settings.children.billing.href,
  settingsUsage: routes.settings.children.usage.href,
  settingsApiKeys: routes.settings.children.apiKeys.href,
  settingsOrganization: routes.settings.children.organization.href,
} as const;

/** @public */
export type AppRoute = (typeof ROUTES)[keyof typeof ROUTES];
