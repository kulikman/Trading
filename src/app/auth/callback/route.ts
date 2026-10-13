import { NextResponse, type NextRequest } from "next/server";

import { getOnboardingStatus } from "@/features/onboarding";
import { createClient } from "@/lib/supabase/server";
import { logger } from "@/lib/logger";
import { ROUTES } from "@/lib/constants";

/**
 * Supabase Auth callback handler.
 *
 * Supabase redirects here after:
 *   - Email confirmation (signup)  → redirected to /onboarding when not completed
 *   - Password reset (magic link)  → `next` param is set, onboarding check skipped
 *   - OAuth flows (if added later)
 *
 * The `code` param is exchanged for a session; the user is then
 * redirected to `next` (default: dashboard).
 *
 * Onboarding redirect logic:
 *   - If `next` was NOT explicitly provided the caller is a signup flow.
 *     In that case we check `profiles.onboarding_completed` and redirect
 *     to /onboarding for new users. Password-reset flows always pass
 *     `next=/` or another explicit path, so they bypass this check.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  // `next` is only set by password-reset / explicit redirects — signup flows omit it.
  const explicitNext = searchParams.get("next");
  const next = explicitNext ?? ROUTES.dashboard;

  if (!code) {
    logger.warn("auth callback missing code param");
    return NextResponse.redirect(`${origin}${ROUTES.login}?error=auth_callback_failed`);
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    logger.warn("auth callback exchange failed", { reason: error.message });
    return NextResponse.redirect(`${origin}${ROUTES.login}?error=auth_callback_failed`);
  }

  // For signup flows (no explicit `next`): redirect new users to onboarding.
  if (!explicitNext) {
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (user) {
      const onboarding = await getOnboardingStatus(user.id);

      if (!onboarding.completed) {
        logger.info("auth callback: new user, redirecting to onboarding", { userId: user.id });
        return NextResponse.redirect(`${origin}${ROUTES.onboarding}`);
      }
    }
  }

  logger.info("auth callback success", { next });
  return NextResponse.redirect(`${origin}${next}`);
}
