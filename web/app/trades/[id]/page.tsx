import { notFound } from "next/navigation";
import { Suspense } from "react";

import { AccountBar, modeOf } from "@/components/account-bar";
import { Grid } from "@/components/grid";
import { apiGetOrNull } from "@/lib/api";
import type { Card } from "@/lib/types";

export default function CardPage({
  params,
  searchParams,
}: PageProps<"/trades/[id]">): React.ReactElement {
  return (
    <Suspense fallback={<p className="muted">загрузка…</p>}>
      <CardContent params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function CardContent({
  params,
  searchParams,
}: PageProps<"/trades/[id]">): Promise<React.ReactElement> {
  const { id } = await params;
  const query = await searchParams;
  const mode = modeOf(query.mode);
  if (!/^\d+$/.test(id)) {
    notFound();
  }
  const card = await apiGetOrNull<Card>(`/api/trades/${id}`);
  if (card === null) {
    notFound();
  }
  return (
    <>
      <AccountBar mode={mode} query={query} />
      <h1>
        Карточка {card.ticker} · режим {card.mode} · {card.state} ·{" "}
        {card.is_paper ? "PAPER" : "REAL"}
      </h1>
      <div className="card num">{card.legs}</div>
      <h2>История переходов</h2>
      <Grid head={["Время", "Из → в", "Причина"]}>
        {card.transitions.map((row) => (
          <tr key={`${row.time}-${row.change}`}>
            <td className="num">{row.time}</td>
            <td>{row.change}</td>
            <td>{row.reason}</td>
          </tr>
        ))}
      </Grid>
    </>
  );
}
