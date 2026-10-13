import { ImageResponse } from "next/og";

export const runtime = "nodejs";
export const size = { width: 32, height: 32 };
export const contentType = "image/png";

/**
 * Dynamic favicon. Replace with a real `favicon.ico` in `public/` if you
 * have a brand asset; this stub keeps the template self-contained so a
 * fresh clone never shows the default Next-logo favicon in dev tools.
 */
export default function Icon(): Promise<ImageResponse> {
  return Promise.resolve(
    new ImageResponse(
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0a0a0a",
          color: "white",
          fontSize: 20,
          fontWeight: 700,
          fontFamily: "system-ui, sans-serif",
          borderRadius: 6,
        }}
      >
        T
      </div>,
      { ...size }
    )
  );
}
