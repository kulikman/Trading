import { Suspense } from "react";

import { AccountBar, modeOf } from "@/components/account-bar";
import { Empty, Grid } from "@/components/grid";
import { N, toneClass } from "@/components/num";
import { SubTabs } from "@/components/sub-tabs";
import { apiGet } from "@/lib/api";
import type { AccountSummary } from "@/lib/types";

// Размер SVG кривой баланса — тот же, что у пути с бэкенда (api/account.py CURVE_WIDTH × CURVE_HEIGHT).
const CURVE_VIEWBOX = "0 0 600 160";

const TABS = [
  { key: "summary", label: "Итоги" },
  { key: "metrics", label: "Показатели" },
  { key: "path", label: "Путь к Real" },
] as const;

export default function AccountPage({ searchParams }: PageProps<"/account">): React.ReactElement {
  return (
    <Suspense fallback={<p className="muted">загрузка…</p>}>
      <AccountContent searchParams={searchParams} />
    </Suspense>
  );
}

async function AccountContent({
  searchParams,
}: Pick<PageProps<"/account">, "searchParams">): Promise<React.ReactElement> {
  const params = await searchParams;
  const mode = modeOf(params.mode);
  const tab = TABS.find((t) => t.key === params.tab)?.key ?? "summary";
  const summary = await apiGet<AccountSummary>(`/api/account/summary?mode=${mode}`);
  return (
    <>
      <AccountBar mode={mode} />
      <SubTabs
        tabs={TABS.map((t) => ({
          href: `/account?tab=${t.key}&mode=${mode}`,
          label: t.label,
          isActive: t.key === tab,
        }))}
      />
      {!summary.is_available ? <Empty text={summary.message} /> : null}
      {summary.is_available && tab === "summary" ? <Summary summary={summary} /> : null}
      {summary.is_available && tab === "metrics" ? (
        <Grid head={["Показатель", "Сезон", "Всё время"]}>
          {summary.metrics.map((row) => (
            <tr key={row.metric}>
              <td>{row.metric}</td>
              <td>
                <N value={row.season} />
              </td>
              <td>
                <N value={row.all_time} />
              </td>
            </tr>
          ))}
        </Grid>
      ) : null}
      {summary.is_available && tab === "path" ? (
        <p className="num">
          {summary.path_to_real.map((item, index) => (
            <span key={item.criterion}>
              {index > 0 ? " · " : ""}
              <span className={toneClass(item.tone)}>{item.display}</span>
            </span>
          ))}
        </p>
      ) : null}
    </>
  );
}

function Summary({ summary }: { summary: AccountSummary }): React.ReactElement {
  return (
    <>
      <Grid head={["Период", "P&L $", "P&L %", "Сделок", "Прибыльных"]}>
        {summary.periods.map((row) => (
          <tr key={row.period}>
            <td>{row.period}</td>
            <td>
              <N value={row.pnl} />
            </td>
            <td>
              <N value={row.pnl_share} />
            </td>
            <td>
              <N value={row.trades} />
            </td>
            <td>
              <N value={row.win_rate} />
            </td>
          </tr>
        ))}
      </Grid>
      <h3>Кривая баланса</h3>
      {summary.curve_path !== null ? (
        <svg
          viewBox={CURVE_VIEWBOX}
          width="100%"
          role="img"
          aria-label="Кривая баланса по дням"
          className="border border-[#999999]"
          shapeRendering="crispEdges"
        >
          <path d={summary.curve_path} fill="none" stroke="#000000" strokeWidth="1" />
        </svg>
      ) : (
        <Empty text={summary.curve_message} />
      )}
    </>
  );
}
