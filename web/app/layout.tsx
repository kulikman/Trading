import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Suspense } from "react";

import { Header } from "@/components/header";
import { Menu } from "@/components/menu";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "cyrillic"],
});

export const metadata: Metadata = {
  title: "Earnings Engine",
  description: "Дашборд Earnings Engine — только чтение",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={inter.variable}>
      <body>
        <div className="z-10 border-b border-[var(--color-line)] bg-[var(--color-header)] backdrop-blur md:sticky md:top-0">
          <div className="page !pb-0">
            <Suspense fallback={<div className="py-3 muted">загрузка статуса…</div>}>
              <Header />
            </Suspense>
            <Suspense fallback={<nav className="tabs" />}>
              <Menu />
            </Suspense>
          </div>
        </div>
        <main className="page">{children}</main>
      </body>
    </html>
  );
}
