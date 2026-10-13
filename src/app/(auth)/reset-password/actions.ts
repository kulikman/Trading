"use server";

import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { resetPasswordSchema } from "@/lib/validations";
import { logger } from "@/lib/logger";
import { ROUTES } from "@/lib/constants";

export interface ResetPasswordState {
  error?: string;
}

export async function resetPassword(
  _prev: ResetPasswordState,
  formData: FormData
): Promise<ResetPasswordState> {
  const parsed = resetPasswordSchema.safeParse({
    password: formData.get("password"),
    confirmPassword: formData.get("confirmPassword"),
  });

  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid input" };
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.updateUser({ password: parsed.data.password });

  if (error) {
    logger.warn("password reset failed", { reason: error.message });
    return { error: "Could not update password. The reset link may have expired." };
  }

  logger.info("password reset success");
  redirect(ROUTES.dashboard);
}
