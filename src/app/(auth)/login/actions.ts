"use server";

import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { ROUTES } from "@/lib/constants";
import { loginSchema } from "@/lib/validations";
import { logger } from "@/lib/logger";
import { limit } from "@/lib/rate-limit";
import { writeAuditLog } from "@/lib/audit";
import { getRequestIp } from "@/lib/request-ip";

/**
 * Canonical Server Action pattern for the template:
 *   - Validate the FormData with Zod at the boundary.
 *   - Rate-limit per client IP — login is the #1 brute-force target.
 *   - Call Supabase Auth on the server (cookies wired via the proxy).
 *   - Return `{ error }` for the form to render via `useActionState`.
 *   - Redirect on success (does not return — throws `NEXT_REDIRECT`).
 */

export interface LoginState {
  error?: string;
}

export async function signInWithPassword(
  _prev: LoginState,
  formData: FormData
): Promise<LoginState> {
  const parsed = loginSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });

  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid input" };
  }

  // Rate-limit by client IP (or by email if you want to slow targeted attacks).
  const ip = await getRequestIp();
  const { success } = await limit(`login:${ip}`, { limit: 5, windowMs: 60_000 });
  if (!success) {
    logger.warn("login rate-limited", { ip });
    return { error: "Too many attempts. Try again in a minute." };
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword(parsed.data);

  if (error) {
    logger.warn("login failed", { reason: error.message });
    return { error: "Invalid email or password." };
  }

  const {
    data: { user },
  } = await supabase.auth.getUser();
  await writeAuditLog({
    userId: user?.id ?? null,
    action: "auth.login",
    metadata: { ip },
  });

  redirect(ROUTES.dashboard);
}
