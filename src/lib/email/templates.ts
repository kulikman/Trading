import "server-only";

import { siteConfig } from "@/config/site";

interface WelcomeTemplateInput {
  name: string;
  appUrl: string;
}

/**
 * Plain-HTML email templates. Keep them ugly but functional — Gmail
 * strips most CSS, and tracking pixel/link rewriting from your sender
 * domain matters more than aesthetics.
 *
 * For richer templates use `react-email` and render to string here.
 *
 * Note: Verify-email and password-reset emails are sent by Supabase Auth
 * directly (configured in the Supabase dashboard → Authentication → Email
 * Templates). Do NOT duplicate them here.
 */
export function welcomeEmail({ name, appUrl }: WelcomeTemplateInput): {
  subject: string;
  html: string;
  text: string;
} {
  return {
    subject: `Welcome to ${siteConfig.name}`,
    html: `<!doctype html>
<html><body style="font-family:system-ui,sans-serif;line-height:1.5;color:#111;max-width:560px;margin:24px auto;">
  <h1 style="font-size:20px;">Welcome, ${escapeHtml(name)}.</h1>
  <p>Thanks for signing up to ${escapeHtml(siteConfig.name)}.</p>
  <p><a href="${appUrl}/dashboard" style="display:inline-block;background:#000;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;">Open dashboard</a></p>
  <p style="color:#666;font-size:12px;margin-top:32px;">If you didn't sign up, ignore this email.</p>
</body></html>`,
    text: `Welcome, ${name}.\n\nThanks for signing up to ${siteConfig.name}.\n\nOpen dashboard: ${appUrl}/dashboard\n\nIf you didn't sign up, ignore this email.`,
  };
}

interface SubscriptionConfirmedInput {
  name: string;
  planName: string;
  renewalDate: string;
  portalUrl: string;
}

/** Sent after checkout.session.completed — confirms the plan the user is now on. */
export function subscriptionConfirmedEmail({
  name,
  planName,
  renewalDate,
  portalUrl,
}: SubscriptionConfirmedInput): { subject: string; html: string; text: string } {
  return {
    subject: `You're now on the ${planName} plan — ${siteConfig.name}`,
    html: `<!doctype html>
<html><body style="font-family:system-ui,sans-serif;line-height:1.5;color:#111;max-width:560px;margin:24px auto;">
  <h1 style="font-size:20px;">Subscription confirmed, ${escapeHtml(name)}.</h1>
  <p>You&rsquo;re now on the <strong>${escapeHtml(planName)}</strong> plan. Your next renewal is on ${escapeHtml(renewalDate)}.</p>
  <p><a href="${portalUrl}" style="display:inline-block;background:#000;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;">Manage subscription</a></p>
  <p style="color:#666;font-size:12px;margin-top:32px;">Questions? Reply to this email — we&rsquo;re happy to help.</p>
</body></html>`,
    text: `Subscription confirmed, ${name}.\n\nYou're now on the ${planName} plan. Your next renewal is on ${renewalDate}.\n\nManage subscription: ${portalUrl}`,
  };
}

interface PaymentFailedInput {
  name: string;
  portalUrl: string;
}

/** Sent when invoice.payment_failed — prompts user to update payment method. */
export function paymentFailedEmail({ name, portalUrl }: PaymentFailedInput): {
  subject: string;
  html: string;
  text: string;
} {
  return {
    subject: `Action required: payment failed — ${siteConfig.name}`,
    html: `<!doctype html>
<html><body style="font-family:system-ui,sans-serif;line-height:1.5;color:#111;max-width:560px;margin:24px auto;">
  <h1 style="font-size:20px;">Payment failed, ${escapeHtml(name)}.</h1>
  <p>We couldn&rsquo;t charge your payment method. Please update it to keep your subscription active.</p>
  <p><a href="${portalUrl}" style="display:inline-block;background:#dc2626;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;">Update payment method</a></p>
  <p style="color:#666;font-size:12px;margin-top:32px;">If you need help, reply to this email.</p>
</body></html>`,
    text: `Payment failed, ${name}.\n\nWe couldn't charge your payment method. Please update it to keep your subscription active.\n\nUpdate payment method: ${portalUrl}`,
  };
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => {
    if (c === "&") return "&amp;";
    if (c === "<") return "&lt;";
    if (c === ">") return "&gt;";
    if (c === '"') return "&quot;";
    return "&#39;";
  });
}
