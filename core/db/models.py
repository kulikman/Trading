"""Таблицы Postgres (SPEC §5). Допустимые значения статусов берутся из core.domain.types."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, get_args

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Double,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    SmallInteger,
    Table,
    Text,
    Unicode,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.domain.types import (
    CalibrationStatus,
    CardState,
    DateCheckStatus,
    DateStatus,
    DecisionStatus,
    Direction,
    ErrorLevel,
    EventJobStatus,
    FeatureStage,
    JobKind,
    MarketLevel,
    ModelName,
    OptionType,
    OrderStatus,
    PluginKind,
    PluginStage,
    PromotionMetric,
    QueueStatus,
    ReportTime,
    ShadowStatus,
    StepOutcome,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Деньги — NUMERIC: REAL держит ~7 значащих цифр и теряет центы на P&L.
Money = Numeric(18, 4)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012 — SQLAlchemy reads this class attribute
        str: Text(),
        float: Double(),
        int: Integer(),
        bool: Boolean(),
        datetime: DateTime(timezone=True),
        date: Date(),
        Decimal: Money,
    }


def _one_of(column: str, literal: Any) -> str:
    values = ", ".join(repr(v) for v in get_args(literal))
    return f"{column} IN ({values})"


def _between(column: str, low: float, high: float) -> str:
    return f"{column} BETWEEN {low} AND {high}"


def _pk_id() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(), primary_key=True)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


# --- сектора и компании ---


class Sector(Timestamps, Base):
    __tablename__ = "sector"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    key_metrics: Mapped[list[str]] = mapped_column(JSONB)
    macro_sensitivity: Mapped[list[str] | None] = mapped_column(JSONB)
    data_sources: Mapped[Any | None] = mapped_column(JSONB)


class SectorSummary(Timestamps, Base):
    __tablename__ = "sector_summary"
    __table_args__ = (
        CheckConstraint(_one_of("trend", Direction), name="trend"),
        CheckConstraint(_between("confidence", 0, 1), name="confidence"),
    )

    id: Mapped[int] = _pk_id()
    sector_id: Mapped[str] = mapped_column(ForeignKey("sector.id"), index=True)
    as_of: Mapped[date]
    trend: Mapped[int | None] = mapped_column(SmallInteger)
    confidence: Mapped[float | None]
    peer_surprise_mean: Mapped[float | None]
    sector_momentum_30d: Mapped[float | None]
    facts: Mapped[Any | None] = mapped_column(JSONB)
    risks: Mapped[Any | None] = mapped_column(JSONB)
    text_summary: Mapped[str | None]


class Company(Timestamps, Base):
    __tablename__ = "company"
    __table_args__ = (
        CheckConstraint(
            _one_of("calibration_status", CalibrationStatus), name="calibration_status"
        ),
    )

    ticker: Mapped[str] = mapped_column(primary_key=True)
    sector_id: Mapped[str] = mapped_column(ForeignKey("sector.id"), index=True)
    name: Mapped[str]
    overview: Mapped[str | None]
    segments: Mapped[Any | None] = mapped_column(JSONB)
    risks: Mapped[Any | None] = mapped_column(JSONB)
    options_liquid: Mapped[bool | None]
    calibration_status: Mapped[str] = mapped_column(server_default="active")
    market_cap_usd_m: Mapped[float | None]


class PeerEdge(Timestamps, Base):
    __tablename__ = "peer_edge"
    __table_args__ = (
        CheckConstraint("from_ticker <> to_ticker", name="not_self"),
        CheckConstraint(_between("strength", -1, 1), name="strength"),
        CheckConstraint("lag_days >= 0", name="lag_days"),
    )

    from_ticker: Mapped[str] = mapped_column(ForeignKey("company.ticker"), primary_key=True)
    to_ticker: Mapped[str] = mapped_column(ForeignKey("company.ticker"), primary_key=True)
    strength: Mapped[float | None]
    lag_days: Mapped[int | None]


# --- отчёты ---


class ReportAudit(Timestamps, Base):
    __tablename__ = "report_audit"

    id: Mapped[int] = _pk_id()
    ticker: Mapped[str] = mapped_column(ForeignKey("company.ticker"), index=True)
    fiscal_period: Mapped[str]
    report_date: Mapped[date]
    segments_expected: Mapped[Any | None] = mapped_column(JSONB)
    segments_actual: Mapped[Any | None] = mapped_column(JSONB)
    guidance: Mapped[Any | None] = mapped_column(JSONB)
    management_tone: Mapped[float | None]
    named_risks: Mapped[Any | None] = mapped_column(JSONB)
    summary: Mapped[str | None]
    source_urls: Mapped[Any | None] = mapped_column(JSONB)


class EarningsTrack(Timestamps, Base):
    __tablename__ = "earnings_track"
    __table_args__ = (
        UniqueConstraint("ticker", "report_date"),
        CheckConstraint(_one_of("report_time", ReportTime), name="report_time"),
        CheckConstraint(_one_of("date_check", DateCheckStatus), name="date_check"),
        CheckConstraint(_one_of("guidance_change", Direction), name="guidance_change"),
        CheckConstraint(_one_of("decision", DecisionStatus), name="decision"),
    )

    id: Mapped[int] = _pk_id()
    ticker: Mapped[str] = mapped_column(ForeignKey("company.ticker"))
    report_date: Mapped[date]
    report_time: Mapped[str | None]
    fiscal_period_end: Mapped[date | None]
    sec_filing_date: Mapped[date | None]
    date_check: Mapped[str | None]
    eps_consensus: Mapped[float | None]
    eps_actual: Mapped[float | None]
    eps_surprise_pct: Mapped[float | None]
    rev_consensus: Mapped[float | None]
    rev_actual: Mapped[float | None]
    rev_surprise_pct: Mapped[float | None]
    guidance_change: Mapped[int | None] = mapped_column(SmallInteger)
    implied_move: Mapped[float | None]
    actual_move: Mapped[float | None]
    move_ratio: Mapped[float | None]
    reaction_cause: Mapped[str | None]
    model_p_beat: Mapped[float | None]
    model_p_up: Mapped[float | None]
    model_move_ratio: Mapped[float | None]
    decision: Mapped[str | None]
    skip_reasons: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    shadow_pnl: Mapped[Decimal | None]


class ConsensusSnapshot(Timestamps, Base):
    __tablename__ = "consensus_snapshot"

    ticker: Mapped[str] = mapped_column(ForeignKey("company.ticker"), primary_key=True)
    fiscal_period: Mapped[str] = mapped_column(primary_key=True)
    as_of: Mapped[date] = mapped_column(primary_key=True)
    eps_estimate: Mapped[float | None]
    rev_estimate: Mapped[float | None]


# --- событие, признаки, прогноз ---


class Event(Timestamps, Base):
    __tablename__ = "event"
    __table_args__ = (
        UniqueConstraint("ticker", "report_date"),
        CheckConstraint(_one_of("report_time", ReportTime), name="report_time"),
        CheckConstraint(_one_of("date_status", DateStatus), name="date_status"),
        CheckConstraint(_one_of("queue_status", QueueStatus), name="queue_status"),
    )

    id: Mapped[int] = _pk_id()
    ticker: Mapped[str] = mapped_column(ForeignKey("company.ticker"))
    report_date: Mapped[date]
    report_time: Mapped[str | None]
    fiscal_period: Mapped[str | None]
    date_status: Mapped[str]
    date_sources: Mapped[Any] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    queue_status: Mapped[str] = mapped_column(server_default="planned")


class FeatureSnapshot(Timestamps, Base):
    """Версии не перезаписываются: версия агента — часть ключа."""

    __tablename__ = "feature_snapshot"
    __table_args__ = (CheckConstraint(_one_of("stage", FeatureStage), name="stage"),)

    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), primary_key=True)
    stage: Mapped[str] = mapped_column(primary_key=True)
    agent_id: Mapped[str] = mapped_column(primary_key=True)
    agent_version: Mapped[str] = mapped_column(primary_key=True)
    features: Mapped[dict[str, float]] = mapped_column(JSONB)


class Forecast(Timestamps, Base):
    """Версии не перезаписываются: версия модели — часть ключа."""

    __tablename__ = "forecast"
    __table_args__ = (
        CheckConstraint(_one_of("stage", FeatureStage), name="stage"),
        CheckConstraint(_between("p_beat", 0, 1), name="p_beat"),
        CheckConstraint(_between("p_up", 0, 1), name="p_up"),
        CheckConstraint(_between("move_ratio", 0, 1), name="move_ratio"),
        CheckConstraint(_between("market_p_beat", 0, 1), name="market_p_beat"),
        CheckConstraint(_between("market_p_up", 0, 1), name="market_p_up"),
    )

    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), primary_key=True)
    stage: Mapped[str] = mapped_column(primary_key=True)
    model_version: Mapped[str] = mapped_column(primary_key=True)
    p_beat: Mapped[float | None]
    p_up: Mapped[float | None]
    move_ratio: Mapped[float | None]
    market_p_beat: Mapped[float | None]
    market_p_up: Mapped[float | None]
    implied_move: Mapped[float | None]
    edge_beat: Mapped[float | None]
    edge_up: Mapped[float | None]
    edge_move: Mapped[float | None]
    exploration: Mapped[bool] = mapped_column(server_default=text("false"))


# --- решение и сделка ---


class ModelVersion(Timestamps, Base):
    """Версия модели (SPEC §9): параметры и метрики; на неё ссылается forecast.model_version."""

    __tablename__ = "model_version"
    __table_args__ = (
        UniqueConstraint("model", "version"),
        CheckConstraint(_one_of("model", ModelName), name="model"),
    )

    id: Mapped[int] = _pk_id()
    model: Mapped[str]
    version: Mapped[str]
    params: Mapped[Any] = mapped_column(JSONB)
    metrics: Mapped[Any | None] = mapped_column(JSONB)
    trained_at: Mapped[datetime]
    accepted: Mapped[bool]
    reason: Mapped[str]


class Decision(Timestamps, Base):
    __tablename__ = "decision"
    # Входов у события может быть несколько — по одному на стратегию (сбор данных, решение
    # заказчика 15.10.2026); итог без входа (SKIPPED, strategy_id пуст) — один.
    __table_args__ = (
        CheckConstraint(_one_of("status", DecisionStatus), name="status"),
        UniqueConstraint("event_id", "strategy_id", postgresql_nulls_not_distinct=True),
    )

    id: Mapped[int] = _pk_id()
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)
    status: Mapped[str]
    # Коды пропуска проверяет core.domain (SkipReason): новый код не требует миграции.
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    mode: Mapped[str | None]
    strategy_id: Mapped[str | None]
    construction: Mapped[str | None]
    shadow: Mapped[Any | None] = mapped_column(JSONB)
    decided_at: Mapped[datetime]
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger)  # «ПРОПУСК»; −1 — до T18


class DecisionStep(Timestamps, Base):
    """Шаг решения (T16): предложение или отказ одной стратегии на одной задаче события.

    Из шагов собираются коды пропуска итогового Decision и лучшая отклонённая конструкция для
    теневой сделки. Шаги shadow-стратегий пишутся, но в решение не идут (SPEC §7).
    """

    __tablename__ = "decision_step"
    __table_args__ = (
        UniqueConstraint("event_id", "stage", "job", "strategy_id"),
        CheckConstraint(_one_of("outcome", StepOutcome), name="outcome"),
    )

    id: Mapped[int] = _pk_id()
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)
    stage: Mapped[str]
    job: Mapped[str]
    strategy_id: Mapped[str]
    is_shadow: Mapped[bool]
    outcome: Mapped[str]
    mode: Mapped[str | None]
    construction: Mapped[str | None]
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    edge: Mapped[float | None]
    confidence: Mapped[float | None]
    probability: Mapped[float | None]
    cost_fraction: Mapped[float | None]
    risk_fraction: Mapped[float | None]
    at: Mapped[datetime]


class BrokerOrder(Timestamps, Base):
    """Ордер ManualBroker (T17): инструкция человеку и подтверждённое исполнение.

    client_order_id — ключ идемпотентности: повтор события не создаёт второй ордер (SPEC §11).
    """

    __tablename__ = "broker_order"
    __table_args__ = (CheckConstraint(_one_of("status", OrderStatus), name="status"),)

    order_id: Mapped[str] = mapped_column(primary_key=True)
    client_order_id: Mapped[str] = mapped_column(unique=True)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("trade_card.id"))
    payload: Mapped[Any] = mapped_column(JSONB)
    instruction: Mapped[str]
    status: Mapped[str]
    fill: Mapped[Any | None] = mapped_column(JSONB)


class CashMovement(Timestamps, Base):
    """Пополнение (+) или вывод (−) счёта Real (T17, DASHBOARD §3); у Paper — капитал из конфига."""

    __tablename__ = "cash_movement"
    __table_args__ = (
        CheckConstraint("account IN ('real')", name="account"),
        CheckConstraint("amount <> 0", name="nonzero"),
    )

    id: Mapped[int] = _pk_id()
    account: Mapped[str]
    at: Mapped[datetime]
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    note: Mapped[str | None]


class MarketLevelDay(Timestamps, Base):
    """Уровень Black Swan на закрытии торгового дня (E2d): ежедневная задача market-daily."""

    __tablename__ = "market_level"
    __table_args__ = (CheckConstraint(_one_of("level", MarketLevel), name="level"),)

    day: Mapped[date] = mapped_column(primary_key=True)  # день закрытия, по которому посчитан
    level: Mapped[str]
    vix: Mapped[float | None]
    spy: Mapped[float | None]


class SourceStatus(Timestamps, Base):
    """Источник данных (T18, DASHBOARD §4.7): последний успех и последний сбой."""

    __tablename__ = "source_status"

    source: Mapped[str] = mapped_column(primary_key=True)
    last_ok_at: Mapped[datetime | None]
    last_error_at: Mapped[datetime | None]
    last_error: Mapped[str | None]


class SystemMessage(Timestamps, Base):
    """Сообщение «СИСТЕМА» (SPEC §12): журнал для раздела «Система» и отправка в Telegram."""

    __tablename__ = "system_message"

    id: Mapped[int] = _pk_id()
    at: Mapped[datetime] = mapped_column(index=True)
    code: Mapped[str | None]
    text: Mapped[str]
    sent_at: Mapped[datetime | None]
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger)


class ShadowTrade(Timestamps, Base):
    """Теневая сделка (T16, SPEC §10): результат предложения, которое не стало входом.

    По одной на событие и стратегию — последнее предложение стратегии по событию. pnl — в $
    при риске sizing.data_collection_risk капитала, чтобы стратегии были сравнимы.
    """

    __tablename__ = "shadow_trade"
    __table_args__ = (
        UniqueConstraint("event_id", "strategy_id"),
        CheckConstraint(_one_of("status", ShadowStatus), name="status"),
    )

    id: Mapped[int] = _pk_id()
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)
    strategy_id: Mapped[str]
    step_id: Mapped[int] = mapped_column(ForeignKey("decision_step.id"))
    construction: Mapped[str]
    status: Mapped[str]
    note: Mapped[str | None]  # причина no_data / open
    entry_on: Mapped[date | None]
    exit_at: Mapped[datetime | None]
    exit_reason: Mapped[str | None]
    return_on_risk: Mapped[float | None]
    pnl: Mapped[float | None]
    brier: Mapped[float | None]


class TradeCard(Timestamps, Base):
    __tablename__ = "trade_card"
    __table_args__ = (CheckConstraint(_one_of("state", CardState), name="state"),)

    id: Mapped[int] = _pk_id()
    decision_id: Mapped[int] = mapped_column(ForeignKey("decision.id"), index=True)
    state: Mapped[str]
    paper: Mapped[bool] = mapped_column(server_default=text("true"))
    legs: Mapped[Any] = mapped_column(JSONB)
    stop: Mapped[Any | None] = mapped_column(JSONB)
    trailing: Mapped[Any | None] = mapped_column(JSONB)
    fills: Mapped[Any | None] = mapped_column(JSONB)
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger)
    tg_state: Mapped[str | None]  # состояние, показанное в сообщении (правка при смене, T18)
    reminded_at: Mapped[datetime | None]  # напоминание: Real-вход не подтверждён 15 минут
    fill_prompt_id: Mapped[int | None] = mapped_column(BigInteger)  # «цена исполнения?» (E10-3)
    pnl_total: Mapped[Decimal | None]
    pnl_direction: Mapped[Decimal | None]
    pnl_vol: Mapped[Decimal | None]
    pnl_ivcrush: Mapped[Decimal | None]
    costs: Mapped[Decimal | None]  # издержки входа и выхода, $ (T17)
    risk_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))  # Real: риск сделки, $ (E10)
    cash_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))  # Real: деньги под позицией, $


class TradeCardTransition(Timestamps, Base):
    __tablename__ = "trade_card_transition"
    __table_args__ = (
        CheckConstraint(_one_of("from_state", CardState), name="from_state"),
        CheckConstraint(_one_of("to_state", CardState), name="to_state"),
    )

    id: Mapped[int] = _pk_id()
    card_id: Mapped[int] = mapped_column(ForeignKey("trade_card.id"), index=True)
    at: Mapped[datetime]
    from_state: Mapped[str | None]
    to_state: Mapped[str]
    reason: Mapped[str | None]
    payload: Mapped[Any | None] = mapped_column(JSONB)


# --- плагины ---


class Plugin(Timestamps, Base):
    __tablename__ = "plugin"
    __table_args__ = (
        CheckConstraint(_one_of("kind", PluginKind), name="kind"),
        CheckConstraint(_one_of("stage", PluginStage), name="stage"),
        CheckConstraint(_between("weight", 0, 1), name="weight"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str]
    stage: Mapped[str]
    weight: Mapped[float | None]
    enabled: Mapped[bool]


# --- новости ---


class NewsArticle(Timestamps, Base):
    """Новости по тикерам; одна запись на статью источника, без перезаписи."""

    __tablename__ = "news_article"
    __table_args__ = (Index("ix_news_article_tickers", "tickers", postgresql_using="gin"),)

    id: Mapped[str] = mapped_column(primary_key=True)
    source: Mapped[str]
    published_at: Mapped[datetime] = mapped_column(index=True)
    title: Mapped[str]
    url: Mapped[str]
    tickers: Mapped[list[str]] = mapped_column(ARRAY(Text))
    publisher: Mapped[str | None]
    author: Mapped[str | None]
    description: Mapped[str | None]
    keywords: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    insights: Mapped[Any | None] = mapped_column(JSONB)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))


# --- финансы ---


class FinancialQuarter(Timestamps, Base):
    """Квартальные показатели из SEC XBRL; пересчёт прошлых периодов обновляет строку."""

    __tablename__ = "financial_quarter"

    ticker: Mapped[str] = mapped_column(ForeignKey("company.ticker"), primary_key=True)
    metric: Mapped[str] = mapped_column(primary_key=True)
    period_end: Mapped[date] = mapped_column(primary_key=True)
    period_start: Mapped[date]
    value: Mapped[float]
    unit: Mapped[str]
    derived: Mapped[bool]
    concept: Mapped[str]
    form: Mapped[str]
    accession: Mapped[str]
    filed: Mapped[date]


# --- расписание и журнал события (T09) ---


class EventJob(Timestamps, Base):
    """Задача события по SPEC §8. Ключ идемпотентности — (event_id, stage, job)."""

    __tablename__ = "event_job"
    __table_args__ = (
        CheckConstraint(_one_of("kind", JobKind), name="kind"),
        CheckConstraint(_one_of("status", EventJobStatus), name="status"),
    )

    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), primary_key=True)
    stage: Mapped[str] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str]
    run_at: Mapped[datetime] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(server_default="planned")
    outside_session: Mapped[bool] = mapped_column(server_default=text("false"))


class EventChange(Timestamps, Base):
    """Журнал изменений события: дата, время, статусы (блок «Изменилось», DASHBOARD.md §4.1)."""

    __tablename__ = "event_change"

    id: Mapped[int] = _pk_id()
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)
    at: Mapped[datetime]
    field: Mapped[str]
    old_value: Mapped[str | None]
    new_value: Mapped[str | None]
    reason: Mapped[str | None]


class PluginStageChange(Timestamps, Base):
    """Журнал promote (T13): переходы стадий и отказы с причиной."""

    __tablename__ = "plugin_stage_change"
    __table_args__ = (
        CheckConstraint(_one_of("from_stage", PluginStage), name="from_stage"),
        CheckConstraint(_one_of("to_stage", PluginStage), name="to_stage"),
        CheckConstraint(_one_of("metric", PromotionMetric), name="metric"),
    )

    id: Mapped[int] = _pk_id()
    plugin_id: Mapped[str] = mapped_column(index=True)
    version: Mapped[str]
    from_stage: Mapped[str]
    to_stage: Mapped[str | None]
    accepted: Mapped[bool]
    reason: Mapped[str]
    metric: Mapped[str]
    observations: Mapped[int]
    baseline: Mapped[float | None]
    candidate: Mapped[float | None]
    at: Mapped[datetime]


class ErrorLog(Timestamps, Base):
    """Журнал ошибок задач и их восстановления («Настройки → Логи»); секреты вычищены при записи."""

    __tablename__ = "error_log"
    __table_args__ = (CheckConstraint(_one_of("level", ErrorLevel), name="level"),)

    id: Mapped[int] = _pk_id()
    at: Mapped[datetime] = mapped_column(index=True)
    level: Mapped[str] = mapped_column(server_default="error")  # error / ok — снова работает
    source: Mapped[str]  # задача: options, calendar-daily, archive-daily …
    event_id: Mapped[int | None] = mapped_column(ForeignKey("event.id"))
    ticker: Mapped[str | None]
    stage: Mapped[str | None]
    error_type: Mapped[str]
    message: Mapped[str]
    resolved_at: Mapped[datetime | None]  # та же задача потом отработала — ошибка решена
    notified_at: Mapped[datetime | None]  # разобрана для сообщений «СИСТЕМА» (T18)


# --- архив опционов (T10) ---


class OptionDailyBar(Timestamps, Base):
    """Дневная цена контракта. Источник хранит историю скользящим окном — архив копится здесь."""

    __tablename__ = "option_daily_bar"
    __table_args__ = (
        CheckConstraint(_one_of("option_type", OptionType), name="option_type"),
        Index("ix_option_daily_bar_underlying_day", "underlying", "day"),
    )

    option_ticker: Mapped[str] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    underlying: Mapped[str]
    expiration: Mapped[date]
    strike: Mapped[float]
    option_type: Mapped[str]
    open: Mapped[float]
    high: Mapped[float]
    low: Mapped[float]
    close: Mapped[float]
    volume: Mapped[float]
    vwap: Mapped[float | None]
    transactions: Mapped[int | None]


class OptionMinuteBar(Timestamps, Base):
    """Минутная цена контракта в день реакции (выход до 11:00 ET); архив — как и дневные цены."""

    __tablename__ = "option_minute_bar"

    option_ticker: Mapped[str] = mapped_column(primary_key=True)
    minute: Mapped[datetime] = mapped_column(primary_key=True)
    open: Mapped[float]
    high: Mapped[float]
    low: Mapped[float]
    close: Mapped[float]
    volume: Mapped[float]
    vwap: Mapped[float | None]
    transactions: Mapped[int | None]


# Хранилище задач APScheduler 3.11 (SQLAlchemyJobStore). Таблица создаётся миграцией (CLAUDE.md:
# схема только через Alembic); колонки повторяют apscheduler.jobstores.sqlalchemy один в один.
apscheduler_jobs = Table(
    "apscheduler_jobs",
    Base.metadata,
    Column("id", Unicode(191), primary_key=True),
    Column("next_run_time", Float(25), index=True),
    Column("job_state", LargeBinary, nullable=False),
)
