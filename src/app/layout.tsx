import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";
import { SpeedInsights } from "@vercel/speed-insights/next";
import "./globals.css";

import { siteConfig } from "@/config/site";
import { getPublicMetadataEnv } from "@/lib/env";
import { flags } from "@/lib/flags";
import { Header } from "@/components/layout/header";
import { Providers } from "@/components/providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// metadataBase must be the canonical production origin — otherwise OG image
// URLs and absolute links resolve to localhost on Vercel. Read from validated
// env (NEXT_PUBLIC_APP_URL); siteConfig.url is just a build-time fallback.
//
// Use `getPublicMetadataEnv()` so `next build` doesn't require Supabase keys.
const baseUrl = getPublicMetadataEnv().NEXT_PUBLIC_APP_URL;

export const metadata: Metadata = {
  title: {
    default: siteConfig.name,
    template: `%s — ${siteConfig.name}`,
  },
  description: siteConfig.description,
  metadataBase: new URL(baseUrl),
  openGraph: {
    type: "website",
    locale: "en_US",
    url: baseUrl,
    title: siteConfig.name,
    description: siteConfig.description,
    siteName: siteConfig.name,
    // Images are auto-injected from src/app/opengraph-image.tsx by Next 16.
  },
  twitter: {
    card: "summary_large_image",
    title: siteConfig.name,
    description: siteConfig.description,
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>): React.ReactElement {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="bg-background text-foreground flex min-h-full flex-col">
        <Providers>
          <Header />
          <main className="flex flex-1 flex-col">{children}</main>
        </Providers>
        {/* Vercel Analytics + Speed Insights — enabled via FF_ANALYTICS env flag.
            Both are no-ops when the flag is off, safe to ship unconditionally. */}
        {flags.analytics && <Analytics />}
        {flags.analytics && <SpeedInsights />}
      </body>
    </html>
  );
}
