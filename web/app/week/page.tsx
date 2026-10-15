import Link from "next/link";
import { Suspense } from "react";

import { AccountBar, modeOf } from "@/components/account-bar";
import { Empty, Grid } from "@/components/grid";
import { SubTabs } from "@/components/sub-tabs";
import { apiGet } from "@/lib/api";
import type { Terminal, Week } from "@/lib/types";

export default function WeekPage({ searchParams }: PageProps<"/week">): React.ReactElement {
  return (
    <Suspense fallback={<p className="muted">загрузка…</p>}>
      <WeekContent searchParams={searchParams} />
    </Suspense>
  );
}

async function WeekContent({
  searchParams,
}: Pick<PageProps<"/week">, "searchParams">): Promise<React.ReactElement> {
  const params = await searchParams;
  const mode = modeOf(params.mode);
  const tab = params.tab === "all" ? "all" : "top";
  const [week, terminal] = await Promise.all([
    apiGet<Week>("/api/week"),
    apiGet<Terminal>("/api/week/terminal"),
  ]);
  return (
    <>
      <AccountBar mode={mode} query={params} />
      <SubTabs
        tabs={[
          { href: "/week", label: "Топ", isActive: tab === "top" },
          { href: "/week?tab=all", label: "Все события", isActive: tab === "all" },
        ]}
      />
      {tab === "top" ? (
        <>
          <h2>Топ недели</h2>
          {week.top.length > 0 ? (
            <Grid head={Object.keys(week.top[0])}>
              {week.top.map((row) => (
                <tr key={Object.values(row).join("|")}>
                  {Object.values(row).map((cell) => (
                    <td key={cell}>{cell}</td>
                  ))}
                </tr>
              ))}
            </Grid>
          ) : (
            <Empty text={week.top_message} />
          )}
          <h2>Терминал</h2>
          {terminal.rows.length > 0 ? (
            <Grid head={["День", "Время", "Тикер", "Что делать"]}>
              {terminal.rows.map((row) => (
                <tr key={`${row.time}-${row.ticker}-${row.action}`}>
                  <td>{row.day}</td>
                  <td className="num">{row.time}</td>
                  <td>{row.ticker}</td>
                  <td>{row.action}</td>
                </tr>
              ))}
            </Grid>
          ) : (
            <Empty text={terminal.message} />
          )}
        </>
      ) : (
        <>
          <h2>Все события недели</h2>
          {week.events.length > 0 ? (
            <Grid head={["Тикер", "Дата", "Статус", "Причина пропуска"]}>
              {week.events.map((row) => (
                <tr key={`${row.ticker}-${row.date}`}>
                  <td>
                    <Link href={`/companies/${row.ticker}`}>{row.ticker}</Link>
                  </td>
                  <td>{row.date}</td>
                  <td>{row.status}</td>
                  <td>{row.reason}</td>
                </tr>
              ))}
            </Grid>
          ) : (
            <Empty text={week.events_message} />
          )}
        </>
      )}
    </>
  );
}
