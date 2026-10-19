import Link from "next/link";
import { Suspense } from "react";

import { Grid } from "@/components/grid";
import { apiGet } from "@/lib/api";
import type { SectorRow } from "@/lib/types";

export default function SectorsPage({ searchParams }: PageProps<"/companies">): React.ReactElement {
  return (
    <Suspense fallback={<p className="muted">загрузка…</p>}>
      <SectorsContent searchParams={searchParams} />
    </Suspense>
  );
}

async function SectorsContent({
  searchParams,
}: Pick<PageProps<"/companies">, "searchParams">): Promise<React.ReactElement> {
  await searchParams;
  const sectors = await apiGet<SectorRow[]>("/api/sectors");
  return (
    <>
      <h2>Сектора</h2>
      <Grid head={["Сектор", "Тренд", "Коротко", "Компаний", "Ближайший отчёт"]}>
        {sectors.map((row) => (
          <tr key={row.id}>
            <td>
              <Link href={`/companies/sector/${row.id}`}>{row.name}</Link>
            </td>
            <td>{row.trend}</td>
            <td>{row.summary}</td>
            <td className="num">{row.companies}</td>
            <td>{row.next_report}</td>
          </tr>
        ))}
      </Grid>
    </>
  );
}
