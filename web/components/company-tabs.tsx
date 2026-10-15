import { Empty, Grid } from "@/components/grid";
import { N } from "@/components/num";
import { apiGet } from "@/lib/api";
import type { Financials, News, Overview, Reports, Track } from "@/lib/types";

export const TABS = [
  { key: "overview", label: "Коротко" },
  { key: "news", label: "Новости" },
  { key: "reports", label: "Отчёты" },
  { key: "financials", label: "Финансы" },
  { key: "track", label: "История отчётов" },
] as const;

export type TabKey = (typeof TABS)[number]["key"];

interface CompanyTabProps {
  ticker: string;
  tab: TabKey;
  overview: Overview;
}

/** Вкладка профиля компании (§4.5): без признаков модели и вероятностей. */
export async function CompanyTab({
  ticker,
  tab,
  overview,
}: CompanyTabProps): Promise<React.ReactElement> {
  const path = `/api/companies/${encodeURIComponent(ticker)}/${tab}`;
  if (tab === "news") {
    const news = await apiGet<News>(path);
    return news.rows.length > 0 ? (
      <Grid head={["Дата", "Тег", "Заголовок"]}>
        {news.rows.map((row) => (
          <tr key={row.url}>
            <td>{row.date}</td>
            <td>{row.tags}</td>
            <td>
              <a href={row.url} target="_blank" rel="noreferrer">
                {row.title}
              </a>
            </td>
          </tr>
        ))}
      </Grid>
    ) : (
      <Empty text={news.message} />
    );
  }
  if (tab === "reports") {
    return <ReportsTab reports={await apiGet<Reports>(path)} />;
  }
  if (tab === "financials") {
    return <FinancialsTab financials={await apiGet<Financials>(path)} />;
  }
  if (tab === "track") {
    return <TrackTab track={await apiGet<Track>(path)} />;
  }
  return (
    <>
      <p>{overview.about}</p>
      <p>Сектор: {overview.sector}</p>
      {overview.segments.length > 0 ? <p>Сегменты: {overview.segments.join(", ")}</p> : null}
      <p>Следующий отчёт: {overview.next_report}</p>
    </>
  );
}

function ReportsTab({ reports }: { reports: Reports }): React.ReactElement {
  return (
    <>
      {reports.audit_date !== null ? (
        <>
          <h3>Разбор отчёта {reports.audit_date}</h3>
          {reports.guidance !== null ? <p>Прогноз компании: {reports.guidance}</p> : null}
          {reports.summary !== null ? <p>{reports.summary}</p> : null}
          {reports.risks.length > 0 ? (
            <ul>
              {reports.risks.map((risk) => (
                <li key={risk}>{risk}</li>
              ))}
            </ul>
          ) : null}
        </>
      ) : null}
      {reports.reports.length > 0 ? (
        <Grid head={["Дата отчёта", "Источники"]}>
          {reports.reports.map((row) => (
            <tr key={row.date}>
              <td>{row.date}</td>
              <td>
                {row.urls.map((url) => (
                  <div key={url}>
                    <a href={url} target="_blank" rel="noreferrer">
                      {url.includes("browse-edgar") ? "8-K в SEC" : url.split("/").pop()}
                    </a>
                  </div>
                ))}
              </td>
            </tr>
          ))}
        </Grid>
      ) : (
        <Empty text={reports.message} />
      )}
    </>
  );
}

function FinancialsTab({ financials }: { financials: Financials }): React.ReactElement {
  if (financials.rows.length === 0) {
    return <Empty text={financials.message} />;
  }
  return (
    <Grid head={["Показатель", ...financials.quarters]}>
      {financials.rows.map((row) => (
        <tr key={row.metric}>
          <td>{row.metric}</td>
          {row.values.map((value, index) => (
            <td key={financials.quarters[index]}>
              <N value={value} />
            </td>
          ))}
        </tr>
      ))}
    </Grid>
  );
}

function TrackTab({ track }: { track: Track }): React.ReactElement {
  if (track.rows.length === 0) {
    return <Empty text={track.message} />;
  }
  return (
    <Grid
      head={[
        "Дата",
        "Ожидание EPS",
        "Факт",
        "Сюрприз",
        "Ожид. движение",
        "Факт. движение",
        "Причина реакции",
        "Решение",
      ]}
    >
      {track.rows.map((row) => (
        <tr key={row.date}>
          <td>{row.date}</td>
          <td>
            <N value={row.eps_consensus} />
          </td>
          <td>
            <N value={row.eps_actual} />
          </td>
          <td>
            <N value={row.surprise} />
          </td>
          <td>
            <N value={row.implied_move} />
          </td>
          <td>
            <N value={row.actual_move} />
          </td>
          <td>{row.reaction_cause}</td>
          <td>{row.decision}</td>
        </tr>
      ))}
    </Grid>
  );
}
