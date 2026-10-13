import { ImageResponse } from "next/og";

import { siteConfig } from "@/config/site";

export const runtime = "nodejs";
export const alt = siteConfig.name;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * Dynamic Open Graph image. Next 16 picks this up automatically and
 * serves it at `/opengraph-image`. Replaces the static `/og-image.jpg`
 * fallback that used to live in `public/` (and that nobody ever made).
 *
 * Override per-route by adding `app/<route>/opengraph-image.tsx`.
 */
export default function OpengraphImage(): Promise<ImageResponse> {
  return Promise.resolve(
    new ImageResponse(
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "flex-start",
          padding: "80px",
          background: "linear-gradient(135deg, #0a0a0a 0%, #1f1f1f 100%)",
          color: "white",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <div
          style={{
            fontSize: 28,
            fontWeight: 600,
            opacity: 0.6,
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            marginBottom: 24,
          }}
        >
          {siteConfig.name}
        </div>
        <div
          style={{
            fontSize: 72,
            fontWeight: 700,
            lineHeight: 1.1,
            maxWidth: 1000,
            letterSpacing: "-0.02em",
          }}
        >
          {siteConfig.description}
        </div>
      </div>,
      { ...size }
    )
  );
}
