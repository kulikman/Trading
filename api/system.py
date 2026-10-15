"""Шапка (статус, РЫНОК) и раздел «Система» (DASHBOARD.md §2, §3, §4.7).

РЫНОК — последний снимок агента «Макро» (VIX, regime = уровень Black Swan, T14a).
Сбой — нерешённая ошибка задачи в журнале error_log за system_failure_window_hours. Когда та же
задача отработала (у задачи события — тот же тикер и стадия), ошибка «решена», шапка — «ОК».
Журнала состояния источников и сообщений «СИСТЕМА» пока нет (сторож и Telegram — T18):
источники показываются как «нет данных», а не «ОК».
"""

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from api.format import Num, Tone, day, empty, et_msk, ratio
from core.config.thresholds import Thresholds
from core.db import models as orm
from core.risk.black_swan import ORDER
from core.session_guard import to_et

LEVEL_LABELS = {"green": "ЗЕЛЁНЫЙ", "yellow": "ЖЁЛТЫЙ", "orange": "ОРАНЖЕВЫЙ", "red": "КРАСНЫЙ"}
LEVEL_TONES: dict[str, Tone] = {
    "green": "positive",
    "yellow": "neutral",
    "orange": "action",
    "red": "action",
}
REPOSITORY = "/Users/DEV/Trading"
RUNS_ON = "сервер Hetzner, docker (deploy/compose.yml)"
SCHEDULER_LOG = "docker logs trading-scheduler (на сервере)"
# DASHBOARD §4.7: имя на экране → источник в source_status (FRED и SEC — тоже данные системы).
SOURCES = {
    "Massive": "massive",
    "Finnhub": "finnhub",
    "Alpha Vantage": "alphavantage",
    "FRED": "fred",
    "SEC EDGAR": "edgar",
    "брокер": "broker",
    "Telegram": "telegram",
    "сторож": "watchdog",
}
NO_CONNECTION = {
    "broker": "ручной брокер — без подключения",
    "watchdog": "внешний (GitHub Actions)",
}
SYSTEM_MESSAGES_SHOWN = 20


class Market(BaseModel):
    level: str
    vix: Num
    tone: Tone
    as_of: str | None


class SourceRow(BaseModel):
    source: str
    status: str
    last_success: str


class Status(BaseModel):
    is_ok: bool
    headline: str  # «СИСТЕМА ОК» / «СИСТЕМА: СБОЙ …»
    tone: Tone
    date: str
    time: str
    market: Market
    sources: list[SourceRow]
    messages: list[str]
    messages_note: str


class ModelRow(BaseModel):
    model: str
    version: str
    trained: str
    brier: Num
    accepted: str


class Models(BaseModel):
    rows: list[ModelRow]
    message: str | None


class ErrorRow(BaseModel):
    time: str
    level: str  # «ошибка» / «решено <когда>»
    tone: Tone
    source: str
    ticker: str
    stage: str
    error_type: str
    message: str
    report: (
        str | None
    )  # текст для кнопки «копировать» (только у нерешённых) — отправить на исправление


class Errors(BaseModel):
    rows: list[ErrorRow]
    message: str | None


class PluginRow(BaseModel):
    name: str
    kind: str
    version: str
    stage: str
    enabled: str
    contribution: Num
    flagged: str


def status_view(session: Session, now: datetime, thresholds: Thresholds) -> Status:
    failed = _failing_sources(
        session, now - timedelta(hours=thresholds.dashboard.system_failure_window_hours)
    )
    is_ok = not failed
    headline = "СИСТЕМА ОК" if is_ok else f"СИСТЕМА: СБОЙ {', '.join(failed)}"
    return Status(
        is_ok=is_ok,
        headline=headline,
        tone="neutral" if is_ok else "action",
        date=day(to_et(now).date()),
        time=et_msk(now),
        market=_market(session),
        sources=_sources(session),
        messages=_system_messages(session),
        messages_note=f"последние {SYSTEM_MESSAGES_SHOWN} сообщений «СИСТЕМА»",
    )


def _sources(session: Session) -> list[SourceRow]:
    """ОК / СБОЙ по последней отметке источника и время последнего успеха (DASHBOARD §4.7)."""
    rows = {r.source: r for r in session.scalars(select(orm.SourceStatus))}
    out = []
    for name, key in SOURCES.items():
        row = rows.get(key)
        if row is None:
            status = NO_CONNECTION.get(key, "нет данных")
            out.append(SourceRow(source=name, status=status, last_success="—"))
            continue
        failing = row.last_error_at is not None and (
            row.last_ok_at is None or row.last_error_at > row.last_ok_at
        )
        last = row.last_ok_at
        out.append(
            SourceRow(
                source=name,
                status="СБОЙ" if failing else "ОК",
                last_success="—" if last is None else f"{day(to_et(last).date())} {et_msk(last)}",
            )
        )
    return out


def _system_messages(session: Session) -> list[str]:
    rows = session.scalars(
        select(orm.SystemMessage).order_by(orm.SystemMessage.at.desc()).limit(SYSTEM_MESSAGES_SHOWN)
    ).all()
    return [f"{day(to_et(r.at).date())} {et_msk(r.at)} — {r.text}" for r in rows]


def _failing_sources(session: Session, since: datetime) -> list[str]:
    """Задачи с нерешёнными ошибками за окно (решённая ошибка — уже не сбой)."""
    sources = session.scalars(
        select(orm.ErrorLog.source)
        .where(
            orm.ErrorLog.level == "error",
            orm.ErrorLog.resolved_at.is_(None),
            orm.ErrorLog.at >= since,
        )
        .order_by(orm.ErrorLog.at.desc())
    ).all()
    return list(dict.fromkeys(sources))


def models_view(session: Session) -> Models:
    """Версии моделей: модель · версия · дата обучения · Brier на отложенной выборке · принята."""
    rows = session.scalars(
        select(orm.ModelVersion).order_by(
            orm.ModelVersion.trained_at.desc(), orm.ModelVersion.model
        )
    ).all()
    labels = {
        "p_beat": "p_beat — EPS ≥ консенсуса",
        "p_up": "p_up — рост цены",
        "move_ratio": "move_ratio — движение > ожидаемого",
    }
    return Models(
        rows=[
            ModelRow(
                model=labels.get(r.model, r.model),
                version=r.version,
                trained=day(to_et(r.trained_at).date()),
                brier=_brier(r.metrics),
                accepted=("да" if r.accepted else "нет") + f" — {r.reason}",
            )
            for r in rows
        ],
        message=None if rows else "моделей нет: make models-init",
    )


def _brier(metrics: object) -> Num:
    """Brier на отложенной выборке появится с первым learn season (T20)."""
    if isinstance(metrics, dict) and isinstance(metrics.get("brier_holdout"), int | float):
        return ratio(float(metrics["brier_holdout"]), 3)
    return empty("нет — стартовая версия, без обучения")


def plugins_view(session: Session) -> list[PluginRow]:
    plugins = session.scalars(select(orm.Plugin).order_by(orm.Plugin.kind, orm.Plugin.id)).all()
    return [
        PluginRow(
            name=p.id,
            kind="агент" if p.kind == "agent" else "стратегия",
            version=p.version,
            stage=p.stage,
            enabled="да" if p.enabled else "нет",
            contribution=empty("нет данных до отчёта сезона (T20)"),
            flagged="нет",
        )
        for p in plugins
    ]


def _market(session: Session) -> Market:
    snapshot = session.scalars(
        select(orm.FeatureSnapshot)
        .where(orm.FeatureSnapshot.agent_id == "macro")
        .order_by(orm.FeatureSnapshot.created_at.desc())
        .limit(1)
    ).first()
    if snapshot is None:
        return Market(level="нет данных", vix=empty(), tone="neutral", as_of=None)
    regime = snapshot.features.get("regime")
    vix = snapshot.features.get("vix")
    level = ORDER[int(regime)] if regime is not None else None
    return Market(
        level=LEVEL_LABELS[level] if level else "нет данных",
        vix=ratio(vix, 1) if vix is not None else empty(),
        tone=LEVEL_TONES[level] if level else "neutral",
        as_of=et_msk(snapshot.created_at),
    )


def errors_view(session: Session, limit: int) -> Errors:
    """Последние ошибки задач, от новых к старым (журнал error_log, секреты вычищены при записи)."""
    entries = session.scalars(
        select(orm.ErrorLog).order_by(orm.ErrorLog.at.desc(), orm.ErrorLog.id.desc()).limit(limit)
    ).all()
    rows = []
    for e in entries:
        time = f"{day(to_et(e.at).date())} {et_msk(e.at)}"
        is_open = e.level == "error" and e.resolved_at is None
        rows.append(
            ErrorRow(
                time=time,
                level=_level(e),
                tone="negative" if is_open else "positive",
                source=e.source,
                ticker=e.ticker or "—",
                stage=e.stage or "—",
                error_type=e.error_type,
                message=e.message,
                report=_error_report(e, time) if is_open else None,
            )
        )
    return Errors(rows=rows, message=None if rows else "ошибок нет")


def _level(entry: orm.ErrorLog) -> str:
    if entry.level == "ok":
        return "решено"
    if entry.resolved_at is None:
        return "ошибка"
    return f"решено {day(to_et(entry.resolved_at).date())} {et_msk(entry.resolved_at)}"


def _error_report(entry: orm.ErrorLog, time: str) -> str:
    """Текст для вставки в чат: что упало, где искать подробности."""
    return "\n".join(
        [
            f"Ошибка в Earnings Engine (код: {REPOSITORY}, работает: {RUNS_ON})",
            f"Время: {time}",
            f"Задача: {entry.source}",
            f"Тикер: {entry.ticker or '—'} · стадия: {entry.stage or '—'}"
            + (f" · event_id: {entry.event_id}" if entry.event_id is not None else ""),
            f"Тип: {entry.error_type}",
            f"Текст: {entry.message}",
            f"Полный traceback: {SCHEDULER_LOG}",
            "Найди причину и предложи исправление.",
        ]
    )


class Heartbeat(BaseModel):
    """Проверка для сторожа (SPEC §12): всё ли ожидаемое ушло вовремя."""

    ok: bool
    problems: list[str]
    checked_at: str


def heartbeat_view(
    session: Session, now: datetime, thresholds: Thresholds, *, watchdog: bool = False
) -> Heartbeat:
    """Просрочки дольше watchdog_grace_minutes: задачи планировщика и неотправленные сообщения.

    watchdog=True — проверку сделал сторож (GitHub Actions): отметка «сторож ОК» для «Системы».
    """
    late = now - timedelta(minutes=thresholds.notify.watchdog_grace_minutes)
    problems = [
        f"задача {job_id} не запускалась с {et_msk(datetime.fromtimestamp(run, tz=UTC))}"
        for job_id, run in session.execute(
            text("SELECT id, next_run_time FROM apscheduler_jobs WHERE next_run_time < :late"),
            {"late": late.timestamp()},
        ).all()
    ]
    checks = (
        (
            "сообщения «СИСТЕМА» не отправлены",
            select(func.count(orm.SystemMessage.id)).where(
                orm.SystemMessage.sent_at.is_(None), orm.SystemMessage.at < late
            ),
        ),
        (
            "карточки сделок без сообщения",
            select(func.count(orm.TradeCard.id)).where(
                orm.TradeCard.tg_message_id.is_(None),
                orm.TradeCard.state.in_(("PLANNED", "ARMED", "OPEN")),
                orm.TradeCard.created_at < late,
            ),
        ),
        (
            "пропуски без сообщения",
            select(func.count(orm.Decision.id)).where(
                orm.Decision.status == "SKIPPED",
                orm.Decision.tg_message_id.is_(None),
                orm.Decision.decided_at < late,
            ),
        ),
    )
    for label, query in checks:
        count = session.scalar(query) or 0
        if count:
            problems.append(f"{label}: {count}")
    if watchdog:
        row = session.get(orm.SourceStatus, "watchdog") or orm.SourceStatus(source="watchdog")
        row.last_ok_at = now
        session.add(row)
        session.commit()
    return Heartbeat(ok=not problems, problems=problems, checked_at=et_msk(now))
