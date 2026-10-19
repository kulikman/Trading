import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { Grid } from "@/components/grid";
import { apiGetOrNull } from "@/lib/api";
import type { SectorDetail } from "@/lib/types";

export default function SectorPage({
  params,
  searchParams,
}: PageProps<"/companies/sector/[id]">): React.ReactElement {
  return (
    <Suspense fallback={<p className="muted">загрузка…</p>}>
      <SectorContent params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function SectorContent({
  params,
  searchParams,
}: PageProps<"/companies/sector/[id]">): Promise<React.ReactElement> {
  const { id } = await params;
  await searchParams;
  const sector = await apiGetOrNull<SectorDetail>(`/api/sectors/${encodeURIComponent(id)}`);
  if (sector === null) {
    notFound();
  }
  return (
    <>
      <p>
        <Link href="/companies">Сектора</Link> → <b>{sector.name}</b>
      </p>
      <h2>{sector.name}</h2>
      <Grid head={["Тикер", "Название", "Дата отчёта", "Статус в очереди"]}>
        {sector.companies.map((row) => (
          <tr key={row.ticker}>
            <td>
              <Link href={`/companies/${row.ticker}`}>{row.ticker}</Link>
            </td>
            <td>{row.name}</td>
            <td>{row.next_report}</td>
            <td>{row.queue_status}</td>
          </tr>
        ))}
      </Grid>
    </>
  );
}
