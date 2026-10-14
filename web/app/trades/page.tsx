import Link from "next/link";
import { Suspense } from "react";

import { AccountBar, modeOf } from "@/components/account-bar";
import { Empty, Grid } from "@/components/grid";
import { N, toneClass } from "@/components/num";
import { SubTabs } from "@/components/sub-tabs";
import { apiGet } from "@/lib/api";
import type { Trades } from "@/lib/types";

export default function TradesPage({ searchParams }: PageProps<"/trades">): React.ReactElement {
  return (
    <Suspense fallback={<p className="muted">загрузка…</p>}>
      <TradesContent searchParams={searchParams} />
    </Suspense>
  );
}

async function TradesContent({
  searchParams,
}: Pick<PageProps<"/trades">, "searchParams">): Promise<React.ReactElement> {
  const params = await searchParams;
  const mode = modeOf(params.mode);
  const state = params.state === "closed" ? "closed" : "open";
  const trades = await apiGet<Trades>(`/api/trades?state=${state}&mode=${mode}`);
  return (
    <>
      <AccountBar mode={mode} />
      <p className={toneClass(trades.trust_tone)}>{trades.trust_line}</p>
      <SubTabs
        tabs={[
          { href: `/trades?mode=${mode}`, label: "Открытые", isActive: state === "open" },
          {
            href: `/trades?state=closed&mode=${mode}`,
            label: "Закрытые",
            isActive: state === "closed",
          },
        ]}
      />
      {state === "open" && trades.open.length > 0 ? (
        <Grid head={["Тикер", "Режим", "Состояние", "Вход", "Цена", "P&L", "Стоп", "Дальше"]}>
          {trades.open.map((row) => (
            <tr key={row.card_id}>
              <td>
                <Link href={`/trades/${row.card_id}`}>{row.ticker}</Link>
              </td>
              <td>{row.mode}</td>
              <td>{row.state}</td>
              <td>
                <N value={row.entry} />
              </td>
              <td>
                <N value={row.price} />
              </td>
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
      ) : null}
      {state === "closed" && trades.closed.length > 0 ? (
        <>
          <Grid head={["Тикер", "Даты", "Режим", "Итог %", "Итог $", "Причина выхода"]}>
            {trades.closed.map((row) => (
              <tr key={row.card_id}>
                <td>
                  <Link href={`/trades/${row.card_id}`}>{row.ticker}</Link>
                </td>
                <td>{row.dates}</td>
                <td>{row.mode}</td>
                <td>
                  <N value={row.result_share} />
                </td>
                <td>
                  <N value={row.result} />
                </td>
                <td>{row.exit_reason}</td>
              </tr>
            ))}
          </Grid>
          <p>
            <b>{trades.total}</b>
          </p>
        </>
      ) : null}
      <Empty text={trades.message} />
    </>
  );
}
