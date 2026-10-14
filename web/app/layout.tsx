import type { Metadata } from "next";
import { Press_Start_2P, Silkscreen } from "next/font/google";
import { Suspense } from "react";

import { Header } from "@/components/header";
import { Menu } from "@/components/menu";
import "./globals.css";

// Silkscreen (DASHBOARD.md §2) без кириллицы — им только надпись EARNINGS ENGINE.
// Русские заголовки и вкладки — пиксельным Press Start 2P (полная кириллица; шире, поэтому мельче).
const silkscreen = Silkscreen({
  variable: "--font-silkscreen",
  weight: "400",
  subsets: ["latin"],
});

const pressStart = Press_Start_2P({
  variable: "--font-press-start",
  weight: "400",
  subsets: ["latin", "cyrillic"],
});

export const metadata: Metadata = {
  title: "Earnings Engine",
  description: "Дашборд Earnings Engine — только чтение",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={`${silkscreen.variable} ${pressStart.variable}`}>
      <body>
        <div className="page">
          <Suspense fallback={<p className="muted">загрузка статуса…</p>}>
            <Header />
          </Suspense>
          <Suspense fallback={<nav className="tabs" />}>
            <Menu />
          </Suspense>
          {children}
        </div>
      </body>
    </html>
  );
}
