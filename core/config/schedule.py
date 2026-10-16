"""Модель config/schedule.yaml: расписание агента «Календарь» и задач события (SPEC §8)."""

from datetime import time
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from core.config.base import PositiveInt, StrictModel
from core.domain.types import JobKind

Shift = Literal["previous", "next"]
# SPEC §8: анализ — на предыдущий торговый день, исполнение — на следующий.
DEFAULT_SHIFT: dict[str, Shift] = {
    "analysis": "previous",
    "execution": "next",
    "notify": "previous",
}


def _parse_time(value: object) -> object:
    if isinstance(value, str):
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    return value


class SchedulerSettings(StrictModel):
    dispatch_interval_seconds: PositiveInt
    misfire_grace_seconds: PositiveInt


class CalendarSettings(StrictModel):
    run_time_et: time
    lookahead_days: PositiveInt
    date_match_window_days: PositiveInt
    same_event_window_days: PositiveInt

    _time = field_validator("run_time_et", mode="before")(_parse_time)


class ArchiveSettings(StrictModel):
    """Ежедневное пополнение архива прошлых отчётов (T12c)."""

    run_time_et: time
    lookback_trading_days: PositiveInt

    _time = field_validator("run_time_et", mode="before")(_parse_time)


class ConsensusSnapshotSettings(StrictModel):
    """Ежедневный снимок консенсуса (T06); окно — sources.finnhub.consensus_lookahead_days."""

    run_time_et: time

    _time = field_validator("run_time_et", mode="before")(_parse_time)


class TrailingSettings(StrictModel):
    """Пересчёт трейлинг-стопа открытых сделок режима C после закрытия (SPEC §10, T17)."""

    run_time_et: time

    _time = field_validator("run_time_et", mode="before")(_parse_time)


class DigestSettings(StrictModel):
    """Дайджесты в Telegram (SPEC §12): утро и вечер ET; еженедельный — пн UTC (09:00 МСК)."""

    morning_et: time
    evening_et: time
    weekly_monday_utc: time

    _times = field_validator("morning_et", "evening_et", "weekly_monday_utc", mode="before")(
        _parse_time
    )


class MarketSettings(StrictModel):
    """Уровень Black Swan на закрытии каждого торгового дня (E2d)."""

    run_time_et: time

    _time = field_validator("run_time_et", mode="before")(_parse_time)


class NewsSettings(StrictModel):
    """Ежедневный сбор новостей компаний и тегов (E6)."""

    run_time_et: time

    _time = field_validator("run_time_et", mode="before")(_parse_time)


class EventJobSpec(StrictModel):
    stage: str = Field(pattern=r"^T([+-]\d+|0)$")
    job: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    offset_days: int
    time_et: time
    kind: JobKind
    shift: Shift | None = None
    agent: str | None = None  # плагин-агент из registry.yaml, который запускает задача (T14)
    strategies: list[str] | None = None  # стратегии, которые решают на этой задаче (T16)

    _time = field_validator("time_et", mode="before")(_parse_time)

    @property
    def effective_shift(self) -> Shift:
        return self.shift or DEFAULT_SHIFT[self.kind]


class ScheduleConfig(StrictModel):
    scheduler: SchedulerSettings
    calendar: CalendarSettings
    archive: ArchiveSettings
    consensus: ConsensusSnapshotSettings
    trailing: TrailingSettings
    digest: DigestSettings
    news: NewsSettings
    market: MarketSettings
    event_jobs: list[EventJobSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_keys(self) -> Self:
        keys = [(j.stage, j.job) for j in self.event_jobs]
        duplicates = {k for k in keys if keys.count(k) > 1}
        if duplicates:
            raise ValueError(f"duplicate event jobs: {sorted(duplicates)}")
        return self
