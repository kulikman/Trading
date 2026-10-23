import Link from "next/link";
import { Suspense } from "react";

import { AccountBar, modeOf } from "@/components/account-bar";
import { Empty, Grid } from "@/components/grid";
import { N } from "@/components/num";
import { apiGet } from "@/lib/api";
import type { Today } from "@/lib/types";

export default function TodayPage({ searchParams }: PageProps<"/">): React.ReactElement {
  return (
    <Suspense fallback={<p className="muted">загрузка…</p>}>
      <TodayContent searchParams={searchParams} />
    </Suspense>
  );
}

async function TodayContent({
  searchParams,
}: Pick<PageProps<"/">, "searchParams">): Promise<React.ReactElement> {
  const query = await searchParams;
  const mode = modeOf(query.mode);
  const today = await apiGet<Today>("/api/today");
  return (
    <>
      <AccountBar mode={mode} query={query} />
      <h2>Сейчас</h2>
      {today.now.is_action ? (
        <div className="box-action">
          {today.now.rows.map((row) => (
            <div key={`${row.time}-${row.ticker}-${row.action}`}>
              <span className="num">{row.time}</span> · <b>{row.ticker}</b> ·{" "}
              <span className="tone-action">{row.action}</span>
              {row.card_id !== null ? (
                <>
                  {" "}
                  · <Link href={`/trades/${row.card_id}`}>карточка</Link>
                </>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="card">{today.now.message}</div>
      )}

      <h2>Отчёты сегодня</h2>
      {today.reports.length > 0 ? (
        <Grid head={["ID", "Тикер", "Время", "EPS ожид.", "EPS факт", "Решение", "Режим", "Причина"]}>
          {today.reports.map((row) => (
            <tr key={row.ticker}>
              <td className="num">
                {row.card_id !== null ? (
                  <Link href={`/trades/${row.card_id}`}>#{row.card_id}</Link>
                ) : (
                  "—"
                )}
              </td>
              <td>
                <Link href={`/companies/${row.ticker}`}>{row.ticker}</Link>
              </td>
              <td>{row.time}</td>
              <td>
                <N value={row.eps_consensus} />
              </td>
              <td>
                <N value={row.eps_actual} />
              </td>
              <td>{row.decision}</td>
              <td>{row.mode}</td>
              <td>{row.reason}</td>
            </tr>
          ))}
        </Grid>
      ) : (
        <Empty text={today.reports_message} />
      )}

      <h2>Открытые позиции</h2>
      {today.positions.length > 0 ? (
        <Grid head={["ID", "Тикер", "Режим", "P&L", "Стоп", "Дальше"]}>
          {today.positions.map((row) => (
            <tr key={row.card_id}>
              <td className="num">
                <Link href={`/trades/${row.card_id}`}>#{row.card_id}</Link>
              </td>
              <td>{row.ticker}</td>
              <td>{row.mode}</td>
              <td>
                <N value={row.pnl} />
              </td>
              <td>
                <N value={row.stop} />
              </td>
              <td>{row.next_step}</td>
            </tr>
          ))}
        </Grid>
      ) : (
        <Empty text={today.positions_message} />
      )}
    </>
  );
}
