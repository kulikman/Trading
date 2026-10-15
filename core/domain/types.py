"""Перечисления домена. Единый источник значений для pydantic-моделей, CHECK в БД и конфигов."""

from typing import Literal

ReportTime = Literal["BMO", "AMC", "DURING"]
DateStatus = Literal["projected", "confirmed"]
QueueStatus = Literal["planned", "profiling", "signals", "decided", "done"]
FeatureStage = Literal["T-14", "T-10", "T-7", "T-3", "T-1", "T0"]
CalibrationStatus = Literal["active", "quarantine"]
MarketLevel = Literal["green", "yellow", "orange", "red"]  # уровень Black Swan
Direction = Literal[-1, 0, 1]

DecisionStatus = Literal["ENTERED", "SKIPPED", "CANCELLED", "DATA_FAIL"]

# SPEC §10. Новый код — сюда; миграция БД не нужна.
SkipReason = Literal[
    "EDGE_LOW",
    "CONF_LOW",
    "PRE_RUN",
    "PEER_CONFLICT",
    "IV_EXPENSIVE",
    "LIQUIDITY",
    "CLUSTER_LIMIT",
    "CALIBRATION",
    "MACRO_BLOCK",
    "C_NOT_CONFIRMED",
    "DATA_MASSIVE",
    "DATA_FINNHUB",
    "DATA_ALPHAVANTAGE",
    "DATA_BROKER",
    "DATA_CALENDAR",
    "DATA_MISMATCH",
]

# SPEC §11.
CardState = Literal[
    "PLANNED", "ARMED", "OPEN", "C_MODE", "CLOSING", "CLOSED", "CANCELLED", "STOPPED"
]

PluginKind = Literal["agent", "strategy"]
PluginStage = Literal["shadow", "paper", "live_small", "live"]
# event — конвейер события (агенты T14, стратегии T16); schedule — своя задача планировщика
PluginRuns = Literal["event", "schedule"]
PromotionMetric = Literal["brier", "sharpe"]

JobKind = Literal["analysis", "execution", "notify"]
# no_handler — исполнитель задачи ещё не реализован (агенты T14, решения T16 и т. д.).
EventJobStatus = Literal["planned", "done", "failed", "missed", "no_handler"]
# Шаг решения (T16): предложение прошло ворота и размер / отказ с кодами.
StepOutcome = Literal["proposal", "skip"]
# Теневая сделка (T16): closed — посчитана; open — позиция ещё не закрылась бы; no_data — нет цен;
# scored — без P&L, только Brier прогноза направления (режим B, решение заказчика 15.10.2026).
ShadowStatus = Literal["closed", "open", "no_data", "scored"]
# Ордер ManualBroker (T17): ждёт исполнения / исполнен / отменён.
OrderStatus = Literal["pending", "filled", "cancelled"]
# Три модели SPEC §9.
ModelName = Literal["p_beat", "p_up", "move_ratio"]
# Журнал «Настройки → Логи»: ошибка задачи или её восстановление после ошибки.
ErrorLevel = Literal["error", "ok"]

OptionType = Literal["call", "put"]

# Сверка даты отчёта с 8-K о результатах (T11): 0–1 день — ok, дальше — mismatch, нет — no_8k
DateCheckStatus = Literal["ok", "mismatch", "no_8k"]
