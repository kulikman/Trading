import Link from "next/link";

import { toneClass } from "@/components/num";
import { apiGet } from "@/lib/api";
import type { Status } from "@/lib/types";

/** Шапка: название, плашка РЫНОК (Black Swan + VIX), статус системы и время ET / МСК (§2, §3). */
export async function Header(): Promise<React.ReactElement> {
  const status = await apiGet<Status>("/api/status");
  const { market } = status;
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 pt-3 pb-1">
      <span className="text-base font-semibold tracking-tight">Earnings Engine</span>
      <div className="flex flex-wrap items-center gap-2">
        <span className="badge">
          Рынок: <b className={toneClass(market.tone)}>{market.level}</b>
          {market.vix.value !== null ? <span className="muted">VIX {market.vix.display}</span> : null}
        </span>
        {status.is_ok ? (
          <span className="badge">
            <span className="dot" />
            {status.headline}
          </span>
        ) : (
          <Link href="/settings" className={`badge ${toneClass(status.tone)}`}>
            <span className="dot dot-action" />
            {status.headline} → логи
          </Link>
        )}
        <span className="muted text-xs">
          {status.date} · {status.time}
        </span>
      </div>
    </header>
  );
}
