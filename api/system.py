"""Шапка (статус, РЫНОК) и раздел «Система» (DASHBOARD.md §2, §3, §4.7).

РЫНОК — последний снимок агента «Макро» (VIX, regime = уровень Black Swan, T14a).
Сбой — задача события с ошибкой за последние system_failure_window_hours.
Журнала состояния источников и сообщений «СИСТЕМА» пока нет (сторож и Telegram — T18):
источники показываются как «нет данных», а не «ОК».
"""

from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import select
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
SOURCES = ("Massive", "Finnhub", "Alpha Vantage", "брокер", "Telegram", "сторож")


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


class PluginRow(BaseModel):
    name: str
    kind: str
    version: str
    stage: str
    enabled: str
    contribution: Num
    flagged: str


def status_view(session: Session, now: datetime, thresholds: Thresholds) -> Status:
    window = timedelta(hours=thresholds.dashboard.system_failure_window_hours)
    failed = session.scalars(
        select(orm.EventJob.job)
        .where(orm.EventJob.status == "failed", orm.EventJob.updated_at >= now - window)
        .order_by(orm.EventJob.updated_at.desc())
    ).all()
    is_ok = not failed
    headline = "СИСТЕМА ОК" if is_ok else f"СИСТЕМА: СБОЙ {', '.join(dict.fromkeys(failed))}"
    return Status(
        is_ok=is_ok,
        headline=headline,
        tone="neutral" if is_ok else "action",
        date=day(to_et(now).date()),
        time=et_msk(now),
        market=_market(session),
        sources=[SourceRow(source=s, status="нет данных", last_success="—") for s in SOURCES],
        messages=[],
        messages_note="журнал сообщений «СИСТЕМА» появится с Telegram и сторожем (T18)",
    )


def models_view() -> Models:
    return Models(rows=[], message="Модели появятся с обучением (T15)")


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
