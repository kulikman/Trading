import Link from "next/link";
import { cookies } from "next/headers";
import { Suspense } from "react";

import { AccountBar, modeOf } from "@/components/account-bar";
import { Empty, Grid } from "@/components/grid";
import { N } from "@/components/num";
import { SEEN_COOKIE, SeenButton } from "@/components/seen-button";
import { apiGet } from "@/lib/api";
import type { Changes, Today } from "@/lib/types";

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
  const seen = (await cookies()).get(SEEN_COOKIE)?.value;
  const [today, changes] = await Promise.all([
    apiGet<Today>("/api/today"),
    apiGet<Changes>(seen ? `/api/changes?since=${encodeURIComponent(seen)}` : "/api/changes"),
  ]);
  return (
    <>
      <AccountBar mode={mode} query={query} />
      {changes.rows.length > 0 ? (
        <section>
          <h2>Изменилось</h2>
          <div className="card">
          <ul className="mb-2 space-y-1">
            {changes.rows.map((row) => (
              <li key={`${row.time}-${row.text}`}>
                <span className="num muted">{row.time}</span> {row.text}
              </li>
            ))}
          </ul>
          <SeenButton />
          </div>
        </section>
      ) : null}

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
        <Grid head={["Тикер", "Время", "Решение", "Режим", "Причина"]}>
          {today.reports.map((row) => (
            <tr key={row.ticker}>
              <td>
                <Link href={`/companies/${row.ticker}`}>{row.ticker}</Link>
              </td>
              <td>{row.time}</td>
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
        <Grid head={["Тикер", "Режим", "P&L", "Стоп", "Дальше"]}>
          {today.positions.map((row) => (
            <tr key={row.card_id}>
              <td>
                <Link href={`/trades/${row.card_id}`}>{row.ticker}</Link>
              </td>
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
