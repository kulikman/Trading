import { Suspense } from "react";

import { CopyButton } from "@/components/copy-button";
import { Empty, Grid } from "@/components/grid";
import { toneClass } from "@/components/num";
import { SubTabs } from "@/components/sub-tabs";
import { apiGet } from "@/lib/api";
import type { Errors } from "@/lib/types";

const ERRORS_LIMIT = 100;

export default function SettingsPage({ searchParams }: PageProps<"/settings">): React.ReactElement {
  return (
    <Suspense fallback={<p className="muted">загрузка…</p>}>
      <SettingsContent searchParams={searchParams} />
    </Suspense>
  );
}

async function SettingsContent({
  searchParams,
}: Pick<PageProps<"/settings">, "searchParams">): Promise<React.ReactElement> {
  await searchParams;
  return (
    <>
      <SubTabs tabs={[{ href: "/settings", label: "Логи", isActive: true }]} />
      <ErrorLog />
    </>
  );
}

/** Журнал задач: что упало, когда и почему, и когда снова заработало — для быстрого поиска проблемы. */
async function ErrorLog(): Promise<React.ReactElement> {
  const errors = await apiGet<Errors>(`/api/system/errors?limit=${ERRORS_LIMIT}`);
  if (errors.rows.length === 0) {
    return <Empty text={errors.message} />;
  }
  return (
    <Grid head={["", "Время", "Статус", "Задача", "Тикер", "Стадия", "Тип", "Текст"]}>
      {errors.rows.map((row) => (
        <tr key={`${row.time}-${row.source}-${row.ticker}-${row.message}`}>
          <td>
            {row.report ? (
              <CopyButton text={row.report} label="Скопировать ошибку для отправки на исправление" />
            ) : null}
          </td>
          <td className="num">{row.time}</td>
          <td className={toneClass(row.tone)}>{row.level}</td>
          <td>{row.source}</td>
          <td>{row.ticker}</td>
          <td>{row.stage}</td>
          <td className={toneClass(row.tone)}>{row.error_type}</td>
          <td className="max-w-[480px] break-words font-mono text-xs">{row.message}</td>
        </tr>
      ))}
    </Grid>
  );
}
