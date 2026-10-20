import Link from "next/link";
import { Suspense } from "react";

import { Grid } from "@/components/grid";
import { apiGet } from "@/lib/api";
import type { CompanyListRow, SectorRow } from "@/lib/types";

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

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
  const letter = typeof query.letter === "string" ? query.letter.toUpperCase() : null;

  const params = new URLSearchParams();
  if (sector) params.set("sector", sector);
  if (letter) params.set("letter", letter);
  const qs = params.toString();

  const [sectors, companies] = await Promise.all([
    apiGet<SectorRow[]>("/api/sectors"),
    apiGet<CompanyListRow[]>(`/api/companies${qs ? `?${qs}` : ""}`),
  ]);

  const totalCount = sectors.reduce((s, r) => s + r.companies, 0);

  function sectorHref(id: string | null): string {
    const p = new URLSearchParams();
    if (id) p.set("sector", id);
    if (letter) p.set("letter", letter);
    return `/companies${p.toString() ? `?${p}` : ""}`;
  }

  function letterHref(l: string | null): string {
    const p = new URLSearchParams();
    if (sector) p.set("sector", sector);
    if (l) p.set("letter", l);
    return `/companies${p.toString() ? `?${p}` : ""}`;
  }

  return (
    <>
      <h2>Компании</h2>

      {/* Фильтр по секторам */}
      <div className="filter-bar">
        <Link href={sectorHref(null)} className={sector === null ? "filter-btn active" : "filter-btn"}>
          Все ({totalCount})
        </Link>
        {sectors.map((s) => (
          <Link
            key={s.id}
            href={sectorHref(s.id)}
            className={sector === s.id ? "filter-btn active" : "filter-btn"}
          >
            {s.name} ({s.companies})
          </Link>
        ))}
      </div>

      {/* Алфавитный фильтр */}
      <div className="filter-bar" style={{ marginBottom: 12 }}>
        <Link href={letterHref(null)} className={letter === null ? "filter-btn active" : "filter-btn"}>
          A–Z
        </Link>
        {ALPHABET.map((l) => (
          <Link
            key={l}
            href={letterHref(l)}
            className={letter === l ? "filter-btn active" : "filter-btn"}
            style={{ padding: "4px 7px", minWidth: 28, textAlign: "center" }}
          >
            {l}
          </Link>
        ))}
      </div>

      <Grid head={["#", "Тикер", "Название", "Сектор", "Капит.", "Ближ. отчёт", "Статус"]}>
        {companies.map((row, idx) => (
          <tr key={row.ticker}>
            <td className="num muted" style={{ width: 36 }}>{idx + 1}</td>
            <td>
              <Link href={`/companies/${row.ticker}`}>{row.ticker}</Link>
            </td>
            <td>{row.name}</td>
            <td>
              <Link href={sectorHref(row.sector_id)}>
                {row.sector_name}
              </Link>
            </td>
            <td className="num">{row.market_cap}</td>
            <td>{row.next_report}</td>
            <td>{row.queue_status}</td>
          </tr>
        ))}
      </Grid>
    </>
  );
}
