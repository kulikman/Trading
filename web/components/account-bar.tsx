import Link from "next/link";

import { AutoRefresh } from "@/components/auto-refresh";
import { N } from "@/components/num";
import { apiGet } from "@/lib/api";
import type { AccountBar as AccountBarData } from "@/lib/types";

interface AccountBarProps {
  mode: "paper" | "real";
}

/** Полоса счёта под меню на каждом экране (§3); Paper и Real не смешиваются. */
export async function AccountBar({ mode }: AccountBarProps): Promise<React.ReactElement> {
  const bar = await apiGet<AccountBarData>(`/api/account?mode=${mode}`);
  const other = mode === "paper" ? "real" : "paper";
  const label = `[${mode.toUpperCase()}]`;
  return (
    <div className="bar">
      <AutoRefresh intervalMs={bar.refresh_ms} />
      <b>{label}</b>{" "}
      <Link href={`?mode=${other}`}>{other === "real" ? "Real" : "Paper"}</Link>{" "}
      {bar.is_available ? (
        <>
          · БАЛАНС <N value={bar.balance} /> · СВОБОДНО <N value={bar.free} /> · В СДЕЛКАХ{" "}
          <N value={bar.in_trades} /> (<N value={bar.in_trades_share} />)
          <br />
          P&amp;L СЕГОДНЯ <N value={bar.pnl_today} /> (<N value={bar.pnl_today_share} />) · МЕСЯЦ{" "}
          <N value={bar.pnl_month} /> (<N value={bar.pnl_month_share} />)
          <br />
          РИСК <N value={bar.risk} /> · ПРИ ВСЕХ СТОПАХ ПРОСАДКА <N value={bar.worst_drawdown} /> /{" "}
          <N value={bar.drawdown_threshold} />
        </>
      ) : (
        <span className="muted">· {bar.message}</span>
      )}
    </div>
  );
}

/** Режим счёта из адреса страницы: ?mode=real, по умолчанию Paper. */
export function modeOf(value: string | string[] | undefined): "paper" | "real" {
  return value === "real" ? "real" : "paper";
}
