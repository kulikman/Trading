"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const SECTIONS = [
  { href: "/", label: "Сегодня" },
  { href: "/week", label: "Неделя" },
  { href: "/trades", label: "Сделки" },
  { href: "/journal", label: "Журнал" },
  { href: "/companies", label: "Компании" },
  { href: "/account", label: "Счёт" },
  { href: "/system", label: "Система" },
  { href: "/settings", label: "Настройки" },
] as const;

/** Основное меню — полоса серых вкладок под шапкой (§3). */
export function Menu(): React.ReactElement {
  const pathname = usePathname();
  return (
    <nav className="tabs max-sm:flex-nowrap max-sm:overflow-x-auto max-sm:whitespace-nowrap">
      {SECTIONS.map((section) => {
        const isActive =
          section.href === "/" ? pathname === "/" : pathname.startsWith(section.href);
        return (
          <Link
            key={section.href}
            href={section.href}
            className={isActive ? "tab tab-active" : "tab"}
          >
            {section.label}
          </Link>
        );
      })}
    </nav>
  );
}
