import { Suspense } from "react";

import { AccountBar, modeOf } from "@/components/account-bar";
import { Empty, Grid } from "@/components/grid";
import { N } from "@/components/num";
import { SubTabs } from "@/components/sub-tabs";
import { apiGet } from "@/lib/api";
import type { Models, PluginRow, Status } from "@/lib/types";

const TABS = [
  { key: "status", label: "Статус" },
  { key: "models", label: "Модели" },
  { key: "plugins", label: "Плагины" },
] as const;

export default function SystemPage({ searchParams }: PageProps<"/system">): React.ReactElement {
  return (
    <Suspense fallback={<p className="muted">загрузка…</p>}>
      <SystemContent searchParams={searchParams} />
    </Suspense>
  );
}

async function SystemContent({
  searchParams,
}: Pick<PageProps<"/system">, "searchParams">): Promise<React.ReactElement> {
  const params = await searchParams;
  const mode = modeOf(params.mode);
  const tab = TABS.find((t) => t.key === params.tab)?.key ?? "status";
  return (
    <>
      <AccountBar mode={mode} />
      <SubTabs
        tabs={TABS.map((t) => ({
          href: `/system?tab=${t.key}`,
          label: t.label,
          isActive: t.key === tab,
        }))}
      />
      {tab === "status" ? <StatusTab /> : null}
      {tab === "models" ? <ModelsTab /> : null}
      {tab === "plugins" ? <PluginsTab /> : null}
    </>
  );
}

async function StatusTab(): Promise<React.ReactElement> {
  const status = await apiGet<Status>("/api/status");
  return (
    <>
      <Grid head={["Источник", "Статус", "Последнее обновление"]}>
        {status.sources.map((row) => (
          <tr key={row.source}>
            <td>{row.source}</td>
            <td>{row.status}</td>
            <td>{row.last_success}</td>
          </tr>
        ))}
      </Grid>
      <h3>Сообщения «Система»</h3>
      {status.messages.length > 0 ? (
        <ul>
          {status.messages.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      ) : (
        <Empty text={status.messages_note} />
      )}
    </>
  );
}

async function ModelsTab(): Promise<React.ReactElement> {
  const models = await apiGet<Models>("/api/system/models");
  if (models.rows.length === 0) {
    return <Empty text={models.message} />;
  }
  return (
    <Grid head={["Модель", "Версия", "Обучена", "Brier", "Принята"]}>
      {models.rows.map((row) => (
        <tr key={`${row.model}-${row.version}`}>
          <td>{row.model}</td>
          <td>{row.version}</td>
          <td>{row.trained}</td>
          <td>
            <N value={row.brier} />
          </td>
          <td>{row.accepted}</td>
        </tr>
      ))}
    </Grid>
  );
}

async function PluginsTab(): Promise<React.ReactElement> {
  const plugins = await apiGet<PluginRow[]>("/api/system/plugins");
  return (
    <Grid head={["Плагин", "Тип", "Версия", "Стадия", "Включён", "Вклад за сезон", "К отключению"]}>
      {plugins.map((row) => (
        <tr key={`${row.name}-${row.version}`}>
          <td>{row.name}</td>
          <td>{row.kind}</td>
          <td>{row.version}</td>
          <td>{row.stage}</td>
          <td>{row.enabled}</td>
          <td>
            <N value={row.contribution} />
          </td>
          <td>{row.flagged}</td>
        </tr>
      ))}
    </Grid>
  );
}
