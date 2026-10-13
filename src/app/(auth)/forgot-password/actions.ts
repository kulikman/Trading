"use server";

import { createClient } from "@/lib/supabase/server";
import { forgotPasswordSchema } from "@/lib/validations";
import { logger } from "@/lib/logger";
import { limit } from "@/lib/rate-limit";
import { getServerEnv } from "@/lib/env";
import { getRequestIp } from "@/lib/request-ip";

export interface ForgotPasswordState {
  error?: string;
  success?: boolean;
}

export async function sendPasswordReset(
  _prev: ForgotPasswordState,
  formData: FormData
): Promise<ForgotPasswordState> {
  const parsed = forgotPasswordSchema.safeParse({
    email: formData.get("email"),
  });

  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid email" };
  }

  const ip = await getRequestIp();

  const { success } = await limit(`reset:${ip}`, { limit: 3, windowMs: 300_000 });
  if (!success) {
    logger.warn("password reset rate-limited", { ip });
    return { error: "Too many attempts. Try again in 5 minutes." };
  }

  const supabase = await createClient();
  const env = getServerEnv();

  const { error } = await supabase.auth.resetPasswordForEmail(parsed.data.email, {
    redirectTo: `${env.NEXT_PUBLIC_APP_URL}/auth/callback?next=/reset-password`,
  });

  if (error) {
    logger.warn("password reset email failed", { reason: error.message });
  }

  // Always return success to avoid email enumeration.
  return { success: true };
}
