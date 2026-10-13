/**
 * Tiny env-driven feature flags.
 *
 * Solo-founder pattern: ship half-finished features behind a `false`
 * flag, flip via Vercel env in seconds without redeploying.
 *
 * Usage:
 *   import { flags } from "@/lib/flags"
 *   if (flags.billing) return <BillingPanel />
 *
 * Each flag reads its own `NEXT_PUBLIC_FF_<NAME>` env var. Keys are
 * spelled out literally so Next.js can statically inline them on the
 * client at build time — dynamic `process.env[key]` access is NOT
 * inlined and would silently always be `false` in the browser.
 *
 * `"true"` or `"1"` enables the flag; anything else (including unset)
 * disables it.
 *
 * For complex rollouts (% gates, user-targeted) swap to GrowthBook
 * or Vercel Edge Config / Flags.
 */
function isOn(value: string | undefined): boolean {
  return value === "true" || value === "1";
}

export const flags = {
  billing: isOn(process.env.NEXT_PUBLIC_FF_BILLING),
  ai: isOn(process.env.NEXT_PUBLIC_FF_AI),
  analytics: isOn(process.env.NEXT_PUBLIC_FF_ANALYTICS),
  onboarding: isOn(process.env.NEXT_PUBLIC_FF_ONBOARDING),
  notifications: isOn(process.env.NEXT_PUBLIC_FF_NOTIFICATIONS),
  apiKeys: isOn(process.env.NEXT_PUBLIC_FF_API_KEYS),
} as const;

/** @public */
export type FeatureFlag = keyof typeof flags;
