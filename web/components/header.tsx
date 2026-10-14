import { toneClass } from "@/components/num";
import { apiGet } from "@/lib/api";
import type { Status } from "@/lib/types";

/** Шапка: название, плашка РЫНОК (Black Swan + VIX), статус системы и время ET / МСК (§2, §3). */
export async function Header(): Promise<React.ReactElement> {
  const status = await apiGet<Status>("/api/status");
  const { market } = status;
  return (
    <header className="flex flex-wrap items-baseline justify-between gap-2 py-1">
      <span className="font-[family-name:var(--font-logo)] text-base">EARNINGS ENGINE</span>
      <span>
        РЫНОК: <b className={toneClass(market.tone)}>{market.level}</b>
        {market.vix.value !== null ? ` · VIX ${market.vix.display}` : ""}
      </span>
      <span className={toneClass(status.tone)}>
        {status.headline}
        {status.is_ok ? <span className="cursor">_</span> : null} · {status.date} · {status.time}
      </span>
    </header>
  );
}
