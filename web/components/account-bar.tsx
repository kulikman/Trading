import Link from "next/link";

import { AutoRefresh } from "@/components/auto-refresh";
import { N } from "@/components/num";
import { apiGet } from "@/lib/api";
import type { AccountBar as AccountBarData, Num } from "@/lib/types";

interface AccountBarProps {
  mode: "paper" | "real";
}

/** Полоса счёта на каждом экране (§3): плитки с числами с бэкенда; Paper и Real не смешиваются. */
export async function AccountBar({ mode }: AccountBarProps): Promise<React.ReactElement> {
  const bar = await apiGet<AccountBarData>(`/api/account?mode=${mode}`);
  return (
    <section>
      <AutoRefresh intervalMs={bar.refresh_ms} />
      <div className="mt-4 flex items-center gap-2">
        <div className="tabs-small !m-0">
          <Link href="?mode=paper" className={mode === "paper" ? "tab tab-active" : "tab"}>
            Paper
          </Link>
          <Link href="?mode=real" className={mode === "real" ? "tab tab-active" : "tab"}>
            Real
          </Link>
        </div>
        {!bar.is_available ? <span className="muted">{bar.message}</span> : null}
      </div>
      {bar.is_available ? (
        <div className="stats">
          <Stat label="Баланс" value={bar.balance} />
          <Stat label="Свободно" value={bar.free} />
          <Stat label="В сделках" value={bar.in_trades} note={bar.in_trades_share} />
          <Stat label="P&L сегодня" value={bar.pnl_today} note={bar.pnl_today_share} />
          <Stat label="P&L месяц" value={bar.pnl_month} note={bar.pnl_month_share} />
          <Stat label="Риск" value={bar.risk} />
          <Stat
            label="Просадка при всех стопах"
            value={bar.worst_drawdown}
            limit={bar.drawdown_threshold}
          />
        </div>
      ) : null}
    </section>
  );
}

interface StatProps {
  label: string;
  value: Num | null;
  note?: Num | null;
  limit?: Num | null;
}

function Stat({ label, value, note, limit }: StatProps): React.ReactElement {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">
        <N value={value} />
        {limit ? (
          <span className="stat-note muted">
            {" "}
            / <N value={limit} />
          </span>
        ) : null}
      </div>
      {note ? (
        <div className="stat-note">
          <N value={note} />
        </div>
      ) : null}
    </div>
  );
}

/** Режим счёта из адреса страницы: ?mode=real, по умолчанию Paper. */
export function modeOf(value: string | string[] | undefined): "paper" | "real" {
  return value === "real" ? "real" : "paper";
}
