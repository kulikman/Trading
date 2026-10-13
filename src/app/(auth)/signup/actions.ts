"use server";

import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { ROUTES } from "@/lib/constants";
import { signupSchema } from "@/lib/validations";
import { logger } from "@/lib/logger";
import { limit } from "@/lib/rate-limit";
import { sendEmail } from "@/lib/email";
import { welcomeEmail } from "@/lib/email/templates";
import { getServerEnv } from "@/lib/env";
import { writeAuditLog } from "@/lib/audit";
import { getRequestIp } from "@/lib/request-ip";

export interface SignupState {
  error?: string;
  success?: boolean;
}

export async function signUp(_prev: SignupState, formData: FormData): Promise<SignupState> {
  const parsed = signupSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
    confirmPassword: formData.get("confirmPassword"),
  });

  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid input" };
  }

  const ip = await getRequestIp();

  const { success } = await limit(`signup:${ip}`, { limit: 3, windowMs: 60_000 });
  if (!success) {
    logger.warn("signup rate-limited", { ip });
    return { error: "Too many attempts. Try again in a minute." };
  }

  const supabase = await createClient();
  const env = getServerEnv();

  const { data, error } = await supabase.auth.signUp({
    email: parsed.data.email,
    password: parsed.data.password,
    options: {
      emailRedirectTo: `${env.NEXT_PUBLIC_APP_URL}/auth/callback`,
    },
  });

  if (error) {
    logger.warn("signup failed", { reason: error.message });
    if (error.message.toLowerCase().includes("already registered")) {
      return { error: "An account with this email already exists." };
    }
    return { error: "Could not create account. Please try again." };
  }

  // Send welcome email after successful signup.
  if (data.user) {
    await writeAuditLog({
      userId: data.user.id,
      action: "auth.signup",
      metadata: { ip },
    });

    await sendEmail({
      to: parsed.data.email,
      ...welcomeEmail({
        name: parsed.data.email.split("@")[0] ?? "there",
        appUrl: env.NEXT_PUBLIC_APP_URL,
      }),
    });
  }

  // If email confirmation is required, show a success message.
  // If auto-confirm is on in Supabase, redirect directly to dashboard.
  if (data.session) {
    redirect(ROUTES.dashboard);
  }

  return { success: true };
}
