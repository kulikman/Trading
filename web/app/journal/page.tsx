import { Suspense } from "react";

import { Empty, Grid } from "@/components/grid";
import { N } from "@/components/num";
import { SubTabs } from "@/components/sub-tabs";
import { apiGet } from "@/lib/api";
import type { Journal } from "@/lib/types";

const FILTERS = [
  { key: "all", label: "Все" },
  { key: "entered", label: "Вошли" },
  { key: "skipped", label: "Пропуски" },
] as const;

export default function JournalPage({ searchParams }: PageProps<"/journal">): React.ReactElement {
  return (
    <Suspense fallback={<p className="muted">загрузка…</p>}>
      <JournalContent searchParams={searchParams} />
    </Suspense>
  );
}

async function JournalContent({
  searchParams,
}: Pick<PageProps<"/journal">, "searchParams">): Promise<React.ReactElement> {
  const params = await searchParams;
  const filter = FILTERS.find((f) => f.key === params.filter)?.key ?? "all";
  const journal = await apiGet<Journal>(`/api/journal?filter=${filter}`);
  return (
    <>
      <p>
        <b>{journal.summary}</b>
      </p>
      {journal.reasons.length > 0 ? (
        <Grid head={["Код", "Раз", "Сэкономлено", "Упущено"]}>
          {journal.reasons.map((row) => (
            <tr key={row.code}>
              <td>{row.code}</td>
              <td>
                <N value={row.times} />
              </td>
              <td>
                <N value={row.saved} />
              </td>
              <td>
                <N value={row.missed} />
              </td>
            </tr>
          ))}
        </Grid>
      ) : null}
      <SubTabs
        tabs={FILTERS.map((f) => ({
          href: f.key === "all" ? "/journal" : `/journal?filter=${f.key}`,
          label: f.label,
          isActive: f.key === filter,
        }))}
      />
      {journal.rows.length > 0 ? (
        <Grid head={["Дата", "Тикер", "Решение", "Коды причин", "Теневая сделка"]}>
          {journal.rows.map((row) => (
            <tr key={`${row.date}-${row.ticker}`}>
              <td>{row.date}</td>
              <td>{row.ticker}</td>
              <td>{row.status}</td>
              <td>{row.reasons}</td>
              <td>
                <N value={row.shadow_result} />
              </td>
            </tr>
          ))}
        </Grid>
      ) : (
        <Empty text={journal.message} />
      )}
    </>
  );
}
