import "server-only";

import { getServerEnv } from "@/lib/env";
import { logger } from "@/lib/logger";

interface SendEmailParams {
  to: string;
  subject: string;
  html: string;
  text?: string;
}

/**
 * Send a transactional email via Resend.
 *
 * Returns `{ ok: true }` on success or `{ ok: false, error }` on failure
 * (never throws — outbound email failure should not crash a Server Action).
 *
 * In dev (no RESEND_API_KEY) emails are logged and the call resolves
 * `{ ok: true, dryRun: true }` so flows like signup work locally.
 */
export async function sendEmail(
  params: SendEmailParams
): Promise<{ ok: true; dryRun?: boolean } | { ok: false; error: string }> {
  const env = getServerEnv();

  if (!env.RESEND_API_KEY || !env.RESEND_FROM_EMAIL) {
    logger.info("email dry-run (RESEND_API_KEY / RESEND_FROM_EMAIL not set)", {
      to: params.to,
      subject: params.subject,
    });
    return { ok: true, dryRun: true };
  }

  try {
    const response = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: env.RESEND_FROM_EMAIL,
        to: params.to,
        subject: params.subject,
        html: params.html,
        text: params.text,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      logger.error("resend send failed", new Error(error), { status: response.status });
      return { ok: false, error: `Resend ${response.status}` };
    }

    return { ok: true };
  } catch (error) {
    logger.error("resend network error", error);
    return { ok: false, error: "Network error" };
  }
}
