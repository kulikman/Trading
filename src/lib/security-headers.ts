/**
 * Centralized security headers. Called from src/proxy.ts for every request.
 *
 * CSP notes:
 *   - 'unsafe-inline' for styles is required by Tailwind CSS v4 (it injects
 *     inline styles for JIT). Removing it breaks styling.
 *   - 'unsafe-eval' is NOT included — Next 16 with Turbopack does not need it
 *     in production. If you see CSP violations for eval in a 3rd-party lib,
 *     narrow the violation with a nonce instead of loosening the policy.
 *   - Supabase domains are whitelisted in connect-src. If you add another
 *     Supabase project, add its host here.
 *   - Vercel Analytics and Speed Insights are whitelisted by default. Remove
 *     those lines if you don't use them.
 *
 * Adjust per project: if you integrate Stripe, PostHog, GA4, Intercom, etc.,
 * add their origins to the relevant directives.
 */

interface SecurityHeaderOptions {
  /** Relax CSP in development so HMR / eval work. */
  isDev: boolean;
}

/**
 * Build the CSP string. Kept as a function so per-env tweaks are obvious.
 */
function buildCsp(options: SecurityHeaderOptions): string {
  const supabaseHost = new URL(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://placeholder.supabase.co"
  ).host;

  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": [
      "'self'",
      "'unsafe-inline'",
      ...(options.isDev ? ["'unsafe-eval'"] : []),
      "https://*.vercel-analytics.com",
      "https://*.vercel-insights.com",
    ],
    "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
    "font-src": ["'self'", "data:", "https://fonts.gstatic.com"],
    "img-src": ["'self'", "data:", "blob:", "https:"],
    "connect-src": [
      "'self'",
      `https://${supabaseHost}`,
      `wss://${supabaseHost}`,
      "https://*.vercel-analytics.com",
      "https://*.vercel-insights.com",
      "https://*.posthog.com",
      "https://*.i.posthog.com",
      ...(options.isDev ? ["ws://localhost:*", "http://localhost:*"] : []),
    ],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "object-src": ["'none'"],
    "upgrade-insecure-requests": [],
  };

  return Object.entries(directives)
    .map(([key, values]) => (values.length ? `${key} ${values.join(" ")}` : key))
    .join("; ");
}

/**
 * Returns a map of header-name → header-value to be applied to every response.
 */
export function buildSecurityHeaders(options: SecurityHeaderOptions): Record<string, string> {
  return {
    "Content-Security-Policy": buildCsp(options),
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy":
      "camera=(), microphone=(), geolocation=(), payment=(), usb=(), bluetooth=()",
    "X-DNS-Prefetch-Control": "off",
  };
}
