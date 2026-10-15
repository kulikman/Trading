import { ApiError, apiGet } from "@/lib/api";

// Публичная проверка для сторожа (SPEC §12): 200 — всё ушло вовремя, 503 — просрочки или нет API.
type Heartbeat = { ok: boolean; problems: string[]; checked_at: string };

export async function GET(request: Request): Promise<Response> {
  const watchdog = new URL(request.url).searchParams.get("watchdog") === "1";
  try {
    const beat = await apiGet<Heartbeat>(
      `/api/system/heartbeat${watchdog ? "?watchdog=true" : ""}`,
    );
    return Response.json(beat, { status: beat.ok ? 200 : 503 });
  } catch (error) {
    const reason = error instanceof ApiError ? `API ${error.status}` : "API не отвечает";
    return Response.json({ ok: false, problems: [reason], checked_at: "" }, { status: 503 });
  }
}
