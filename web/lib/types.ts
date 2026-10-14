// Ответы API дашборда (api/*.py, DASHBOARD.md §5). Фронт показывает только `display`.

export type Tone = "positive" | "negative" | "action" | "neutral";

export interface Num {
  value: number | null;
  display: string;
  tone: Tone;
}

export interface Market {
  level: string;
  vix: Num;
  tone: Tone;
  as_of: string | null;
}

export interface Status {
  is_ok: boolean;
  headline: string;
  tone: Tone;
  date: string;
  time: string;
  market: Market;
  sources: { source: string; status: string; last_success: string }[];
  messages: string[];
  messages_note: string;
}

export interface AccountBar {
  mode: string;
  is_available: boolean;
  message: string | null;
  balance: Num | null;
  free: Num | null;
  in_trades: Num | null;
  in_trades_share: Num | null;
  pnl_today: Num | null;
  pnl_today_share: Num | null;
  pnl_month: Num | null;
  pnl_month_share: Num | null;
  risk: Num | null;
  worst_drawdown: Num | null;
  drawdown_threshold: Num | null;
  refresh_ms: number;
}

export interface AccountSummary {
  mode: string;
  is_available: boolean;
  message: string | null;
  periods: { period: string; pnl: Num; pnl_share: Num; trades: Num; win_rate: Num }[];
  metrics: { metric: string; season: Num; all_time: Num }[];
  curve: { day: string; balance: Num }[];
  curve_path: string | null;
  curve_message: string | null;
  path_to_real: { criterion: string; display: string; is_met: boolean; tone: Tone }[];
}

export interface Changes {
  rows: { time: string; text: string }[];
}

export interface Today {
  now: {
    is_action: boolean;
    rows: { time: string; ticker: string; action: string; card_id: number | null }[];
    message: string | null;
  };
  reports: { ticker: string; time: string; decision: string; mode: string; reason: string }[];
  reports_message: string | null;
  positions: { card_id: number; ticker: string; mode: string; pnl: Num; stop: Num; next_step: string }[];
  positions_message: string | null;
}

export interface Week {
  top: Record<string, string>[];
  top_message: string | null;
  events: { ticker: string; date: string; status: string; reason: string }[];
  events_message: string | null;
}

export interface Terminal {
  rows: { day: string; time: string; ticker: string; action: string }[];
  message: string | null;
}

export interface Trades {
  trust_line: string;
  trust_tone: Tone;
  open: {
    card_id: number;
    ticker: string;
    mode: string;
    state: string;
    entry: Num;
    price: Num;
    pnl: Num;
    stop: Num;
    next_step: string;
  }[];
  closed: {
    card_id: number;
    ticker: string;
    dates: string;
    mode: string;
    result_share: Num;
    result: Num;
    exit_reason: string;
  }[];
  total: string | null;
  message: string | null;
}

export interface Card {
  card_id: number;
  ticker: string;
  mode: string;
  state: string;
  is_paper: boolean;
  legs: string;
  transitions: { time: string; change: string; reason: string }[];
}

export interface Journal {
  summary: string;
  reasons: { code: string; times: Num; saved: Num; missed: Num }[];
  rows: { date: string; ticker: string; status: string; reasons: string; shadow_result: Num }[];
  message: string | null;
}

export interface SectorRow {
  id: string;
  name: string;
  trend: string;
  summary: string;
  companies: number;
  next_report: string;
}

export interface SectorDetail {
  id: string;
  name: string;
  companies: { ticker: string; name: string; next_report: string; queue_status: string }[];
}

export interface Overview {
  ticker: string;
  name: string;
  sector: string;
  about: string;
  segments: string[];
  next_report: string;
}

export interface News {
  rows: { date: string; tags: string; title: string; url: string }[];
  message: string | null;
}

export interface Reports {
  reports: { date: string; urls: string[] }[];
  audit_date: string | null;
  guidance: string | null;
  summary: string | null;
  risks: string[];
  message: string | null;
}

export interface Financials {
  quarters: string[];
  rows: { metric: string; values: Num[] }[];
  message: string | null;
}

export interface Track {
  rows: {
    date: string;
    eps_consensus: Num;
    eps_actual: Num;
    surprise: Num;
    implied_move: Num;
    actual_move: Num;
    reaction_cause: string;
    decision: string;
  }[];
  message: string | null;
}

export interface Models {
  rows: { model: string; version: string; trained: string; brier: Num; accepted: string }[];
  message: string | null;
}

export interface PluginRow {
  name: string;
  kind: string;
  version: string;
  stage: string;
  enabled: string;
  contribution: Num;
  flagged: string;
}

export interface Errors {
  rows: {
    time: string;
    source: string;
    ticker: string;
    stage: string;
    error_type: string;
    message: string;
  }[];
  message: string | null;
}
