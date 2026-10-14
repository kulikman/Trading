import Link from "next/link";

interface SubTabsProps {
  tabs: { href: string; label: string; isActive: boolean }[];
}

/** Вторичные вкладки раздела (меньше основных, §3). */
export function SubTabs({ tabs }: SubTabsProps): React.ReactElement {
  return (
    <nav className="tabs tabs-small">
      {tabs.map((tab) => (
        <Link key={tab.href} href={tab.href} className={tab.isActive ? "tab tab-active" : "tab"}>
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}
