import type { NextConfig } from "next";

import { routes } from "./src/config/routes";

const nextConfig: NextConfig = {
  // Type-safe <Link href={...}> — opts you into Next's typed routes.
  typedRoutes: true,

  // Remote images must be explicitly allowed. Add your CDN / Supabase storage host here.
  images: {
    remotePatterns: [
      // Example: Supabase public storage
      // {
      //   protocol: "https",
      //   hostname: "<project-id>.supabase.co",
      //   pathname: "/storage/v1/object/public/**",
      // },
    ],
  },

  // Security headers as a safety net — the proxy.ts also sets them, but
  // next.config.ts ensures they apply even for static assets served by Vercel.
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // For dynamic requests the full CSP + HSTS come from src/lib/security-headers.ts
          // via proxy.ts. This covers static assets served directly by the Vercel CDN.
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), bluetooth=()",
          },
        ],
      },
    ];
  },

  async redirects() {
    return [
      {
        source: "/settings/org",
        destination: routes.settings.children.organization.href,
        statusCode: 301,
      },
    ];
  },
};

export default nextConfig;
