import Link from "next/link";
import { Suspense } from "react";

import { Grid } from "@/components/grid";
import { apiGet } from "@/lib/api";
import type { CompanyListRow, SectorRow } from "@/lib/types";

export default function CompaniesPage({ searchParams }: PageProps<"/companies">): React.ReactElement {
  return (
    <Suspense fallback={<p className="muted">загрузка…</p>}>
      <CompaniesContent searchParams={searchParams} />
    </Suspense>
  );
}

async function CompaniesContent({
  searchParams,
}: Pick<PageProps<"/companies">, "searchParams">): Promise<React.ReactElement> {
  const query = await searchParams;
  const sector = typeof query.sector === "string" ? query.sector : null;

  const [sectors, companies] = await Promise.all([
    apiGet<SectorRow[]>("/api/sectors"),
    apiGet<CompanyListRow[]>(`/api/companies${sector ? `?sector=${encodeURIComponent(sector)}` : ""}`),
  ]);

  return (
    <>
      <h2>Компании</h2>
      <div className="filter-bar">
        <Link
          href="/companies"
          className={sector === null ? "filter-btn active" : "filter-btn"}
        >
          Все ({sectors.reduce((s, r) => s + r.companies, 0)})
        </Link>
        {sectors.map((s) => (
          <Link
            key={s.id}
            href={`/companies?sector=${encodeURIComponent(s.id)}`}
            className={sector === s.id ? "filter-btn active" : "filter-btn"}
          >
            {s.name} ({s.companies})
          </Link>
        ))}
      </div>
      <Grid head={["Тикер", "Название", "Сектор", "Ближайший отчёт", "Статус"]}>
        {companies.map((row) => (
          <tr key={row.ticker}>
            <td>
              <Link href={`/companies/${row.ticker}`}>{row.ticker}</Link>
            </td>
            <td>{row.name}</td>
            <td>
              <Link href={`/companies?sector=${encodeURIComponent(row.sector_id)}`}>
                {row.sector_name}
              </Link>
            </td>
            <td>{row.next_report}</td>
            <td>{row.queue_status}</td>
          </tr>
        ))}
      </Grid>
    </>
  );
}
