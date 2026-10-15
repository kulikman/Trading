import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { AccountBar, modeOf } from "@/components/account-bar";
import { CompanyTab, TABS, type TabKey } from "@/components/company-tabs";
import { SubTabs } from "@/components/sub-tabs";
import { apiGetOrNull } from "@/lib/api";
import type { Overview } from "@/lib/types";

export default function CompanyPage({
  params,
  searchParams,
}: PageProps<"/companies/[ticker]">): React.ReactElement {
  return (
    <Suspense fallback={<p className="muted">загрузка…</p>}>
      <CompanyContent params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function CompanyContent({
  params,
  searchParams,
}: PageProps<"/companies/[ticker]">): Promise<React.ReactElement> {
  const { ticker } = await params;
  const query = await searchParams;
  const mode = modeOf(query.mode);
  const requested = query.tab;
  const tab: TabKey = TABS.find((t) => t.key === requested)?.key ?? "overview";
  const symbol = encodeURIComponent(ticker.toUpperCase());
  const overview = await apiGetOrNull<Overview>(`/api/companies/${symbol}/overview`);
  if (overview === null) {
    notFound();
  }
  return (
    <>
      <AccountBar mode={mode} query={query} />
      <p>
        <Link href="/companies">Сектора</Link> →{" "}
        <Link href={`/companies/sector/${overview.sector_id}`}>{overview.sector}</Link> →{" "}
        <b>{overview.ticker}</b>
      </p>
      <h2>
        {overview.ticker} · {overview.name}
      </h2>
      <SubTabs
        tabs={TABS.map((t) => ({
          href: `/companies/${overview.ticker}?tab=${t.key}`,
          label: t.label,
          isActive: t.key === tab,
        }))}
      />
      <CompanyTab ticker={overview.ticker} tab={tab} overview={overview} />
    </>
  );
}
