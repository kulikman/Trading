import { Suspense } from "react";

import { Empty, Grid } from "@/components/grid";
import { SubTabs } from "@/components/sub-tabs";
import { apiGet } from "@/lib/api";
import type { Errors } from "@/lib/types";

const ERRORS_LIMIT = 100;

export default function SettingsPage(): React.ReactElement {
  return (
    <>
      <SubTabs tabs={[{ href: "/settings", label: "Логи ошибок", isActive: true }]} />
      <Suspense fallback={<p className="muted">загрузка…</p>}>
        <ErrorLog />
      </Suspense>
    </>
  );
}

/** Последние ошибки задач: что упало, когда и почему — для быстрого поиска проблемы. */
async function ErrorLog(): Promise<React.ReactElement> {
  const errors = await apiGet<Errors>(`/api/system/errors?limit=${ERRORS_LIMIT}`);
  if (errors.rows.length === 0) {
    return <Empty text={errors.message} />;
  }
  return (
    <Grid head={["Время", "Задача", "Тикер", "Стадия", "Тип", "Текст ошибки"]}>
      {errors.rows.map((row) => (
        <tr key={`${row.time}-${row.source}-${row.ticker}-${row.message}`}>
          <td className="num">{row.time}</td>
          <td>{row.source}</td>
          <td>{row.ticker}</td>
          <td>{row.stage}</td>
          <td className="tone-negative">{row.error_type}</td>
          <td className="max-w-[480px] break-words font-mono text-xs">{row.message}</td>
        </tr>
      ))}
    </Grid>
  );
}
