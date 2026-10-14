"""Агент «Досье» (SPEC §8; решения заказчика 14.10.2026): T−10 — признаки, T+1 — итог отчёта.

T−10:
- disclosure — существенные раскрытия компании с прошлого отчёта (8-K выбранных пунктов и новости
  Massive): LLM перечисляет события с направлением (−1 / 0 / 1) и существенностью, код берёт знак
  суммы направлений существенных событий. Нечего читать — 0 без запроса к LLM;
- guidance_risk — (консенсус − середина прогноза компании) / |середина|: консенсус выше
  собственного прогноза компании — выше риск разочарования. Прогноз на квартал отчёта LLM
  извлекает из прошлого пресс-релиза, консенсус — календарь Finnhub (EPS у Finnhub — non-GAAP).
  По выручке, если прогноз выручки есть; иначе по EPS non-GAAP; иначе признака нет.
T+1: reaction_cause и guidance_change в earnings_track — по новому пресс-релизу и фактам архива.
Каждый разбор — новая строка report_audit (версии не перезаписываются).
"""

import logging
from collections.abc import Collection, Sequence
from datetime import date, datetime, timedelta
from typing import Protocol

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.edgar.documents import FilingDocument
from adapters.edgar.models import Filing
from adapters.errors import DataError
from adapters.finnhub.models import FinnhubEarning
from adapters.massive.models import NewsArticle
from agents.dossier.extraction import (
    DISCLOSURE_INSTRUCTIONS,
    GUIDANCE_INSTRUCTIONS,
    OUTCOME_INSTRUCTIONS,
    DisclosureExtraction,
    GuidanceExtraction,
    GuidanceRange,
    OutcomeExtraction,
)
from core.config.thresholds import DossierAgent
from core.db import models as orm
from core.db.store import save_report_audit, set_report_outcome
from core.domain.earnings import ReportAudit
from core.registry.protocols import EventContext, Trigger
from core.session_guard import to_et

logger = logging.getLogger(__name__)

STAGES = ("T-10",)
EARNINGS_RELEASE_ITEM = "2.02"
CONSENSUS_WINDOW_DAYS = 3  # строка календаря Finnhub — в пределах ±3 дней от даты отчёта


class EdgarSource(Protocol):
    def ticker_ciks(self) -> dict[str, int]:
        """Тикер → CIK."""

    def filings(
        self, cik: int, forms: Collection[str] = ..., since: date | None = None
    ) -> list[Filing]:
        """Подачи компании, от новых к старым."""

    def documents(self, filing: Filing) -> list[FilingDocument]:
        """Текстовые документы подачи."""


class NewsSource(Protocol):
    def news(self, ticker: str, published_gte: date | None = None) -> list[NewsArticle]:
        """Новости по тикеру, от новых к старым."""


class ConsensusSource(Protocol):
    def earnings_calendar(
        self, start: date, end: date, symbol: str | None = None
    ) -> list[FinnhubEarning]:
        """Предстоящие отчёты с консенсусом."""


class Extractor(Protocol):
    def extract[M: BaseModel](self, *, instructions: str, text: str, schema: type[M]) -> M:
        """Объект схемы из текста."""


class DossierFeatures(BaseModel):
    disclosure: int = 0  # −1 / 0 / 1
    disclosure_events: int = 0  # существенных событий
    guidance_risk: float | None = None
    guidance_gap_revenue: float | None = None
    guidance_gap_eps: float | None = None


class DossierAgentPlugin:
    id = "dossier"
    version = "0.1.0"
    triggers: Sequence[Trigger] = (Trigger("stage", "T-10"), Trigger("stage", "T+1"))
    reads: Sequence[str] = ("edgar:8-K", "massive:news", "finnhub:calendar", "llm")
    output_schema: type[BaseModel] = DossierFeatures

    def __init__(
        self,
        edgar: EdgarSource,
        news: NewsSource,
        consensus: ConsensusSource,
        llm: Extractor,
        settings: DossierAgent,
        archives_base_url: str,
        predecessor_ciks: dict[str, list[int]] | None = None,
    ) -> None:
        self._edgar = edgar
        self._news = news
        self._consensus = consensus
        self._llm = llm
        self._settings = settings
        self._archives = archives_base_url
        self._predecessors = predecessor_ciks or {}
        self._ciks: dict[str, int] | None = None

    # --- T−10: признаки ---

    def run(self, ctx: EventContext) -> DossierFeatures:
        if ctx.session is None:
            raise DataError("archive", "dossier agent needs the archive session")
        day = to_et(ctx.as_of).date()
        since = day - timedelta(days=self._settings.release_lookback_days)
        filings = [f for f in self._filings(ctx.ticker, since) if f.filing_date < day]
        releases = [f for f in filings if EARNINGS_RELEASE_ITEM in f.items]
        previous = releases[0] if releases else None
        urls: list[str] = []

        guidance = self._guidance(previous, urls)
        features = DossierFeatures()
        self._apply_guidance(features, guidance, self._estimate(ctx.ticker, ctx.report_date))
        start = previous.filing_date if previous is not None else since
        disclosure = self._disclosure(ctx.ticker, filings, previous, start, urls)
        if disclosure is not None:
            material = [e for e in disclosure.events if e.material]
            total = sum(e.direction for e in material)
            features.disclosure = (total > 0) - (total < 0)
            features.disclosure_events = len(material)

        save_report_audit(
            ctx.session,
            ReportAudit(
                ticker=ctx.ticker,
                fiscal_period=_fiscal_period(ctx.session, ctx.event_id),
                report_date=ctx.report_date,
                guidance={
                    "stage": "T-10",
                    "expected": None if guidance is None else guidance.model_dump(),
                    "disclosure_events": (
                        [] if disclosure is None else [e.model_dump() for e in disclosure.events]
                    ),
                },
                summary=None if disclosure is None else disclosure.summary,
                source_urls=urls,
            ),
        )
        return features

    def _guidance(self, release: Filing | None, urls: list[str]) -> GuidanceExtraction | None:
        if release is None:
            return None
        text = self._release_text(release, urls)
        if not text:
            return None
        return self._llm.extract(
            instructions=GUIDANCE_INSTRUCTIONS, text=text, schema=GuidanceExtraction
        )

    def _apply_guidance(
        self,
        features: DossierFeatures,
        guidance: GuidanceExtraction | None,
        estimate: FinnhubEarning | None,
    ) -> None:
        if guidance is None or not guidance.found or estimate is None:
            return
        revenue_mid = _mid(guidance.revenue_usd)
        if revenue_mid is not None and estimate.revenue_estimate is not None:
            ratio = estimate.revenue_estimate / revenue_mid if revenue_mid else float("inf")
            limit = self._settings.revenue_sanity_ratio
            if 1 / limit < ratio < limit:
                features.guidance_gap_revenue = ratio - 1
            else:  # почти наверняка ошибка единиц (миллионы вместо долларов) — не признак
                logger.warning("revenue guidance far from consensus", extra={"ratio": ratio})
        eps_mid = _mid(guidance.eps_usd)
        if eps_mid and guidance.eps_basis == "non_gaap" and estimate.eps_estimate is not None:
            features.guidance_gap_eps = (estimate.eps_estimate - eps_mid) / abs(eps_mid)
        features.guidance_risk = (
            features.guidance_gap_revenue
            if features.guidance_gap_revenue is not None
            else features.guidance_gap_eps
        )

    def _estimate(self, ticker: str, report_date: date) -> FinnhubEarning | None:
        window = timedelta(days=CONSENSUS_WINDOW_DAYS)
        rows = [
            r
            for r in self._consensus.earnings_calendar(
                report_date - window, report_date + window, ticker
            )
            if r.symbol == ticker
        ]
        return min(rows, key=lambda r: abs((r.date - report_date).days)) if rows else None

    def _disclosure(
        self,
        ticker: str,
        filings: Sequence[Filing],
        previous: Filing | None,
        start: date,
        urls: list[str],
    ) -> DisclosureExtraction | None:
        s = self._settings
        items = set(s.disclosure_items)
        recent = [
            f
            for f in filings
            if f.filing_date >= start
            and (previous is None or f.accession_number != previous.accession_number)
            and items & set(f.items)
        ][: s.max_filings]
        news = self._news.news(ticker, published_gte=start)[: s.max_news]
        if not recent and not news:
            return None
        parts = []
        for filing in recent:
            text = _exhibits_or_primary(self._edgar.documents(filing), s.max_chars_per_document)
            urls.append(filing.url(self._archives))
            parts.append(
                f"## 8-K filed {filing.filing_date}, items {', '.join(filing.items)}\n{text}"
            )
        lines = [
            f"- {a.published_utc.date()} {a.title}"
            + (f" — {a.description}" if a.description else "")
            for a in news
        ]
        if lines:
            parts.append("## News headlines\n" + "\n".join(lines))
        return self._llm.extract(
            instructions=DISCLOSURE_INSTRUCTIONS,
            text=_cap("\n\n".join(parts), s.max_chars_per_request),
            schema=DisclosureExtraction,
        )

    # --- T+1: итог отчёта ---

    def outcome(self, session: Session, event_id: int, as_of: datetime) -> None:
        """reaction_cause и guidance_change в earnings_track по пресс-релизу и фактам архива."""
        event = session.get(orm.Event, event_id)
        if event is None:
            raise ValueError(f"event {event_id} not found")
        track = session.scalars(
            select(orm.EarningsTrack).where(
                orm.EarningsTrack.ticker == event.ticker,
                orm.EarningsTrack.report_date == event.report_date,
            )
        ).first()
        if track is None:
            raise DataError("archive", f"{event.ticker} {event.report_date}: no earnings_track row")
        first = event.report_date - timedelta(days=1)
        last = min(
            event.report_date + timedelta(days=self._settings.release_window_days),
            to_et(as_of).date(),
        )
        releases = [
            f
            for f in self._filings(event.ticker, first)
            if EARNINGS_RELEASE_ITEM in f.items and first <= f.filing_date <= last
        ]
        if not releases:
            raise DataError(
                "edgar", f"{event.ticker}: no earnings release 8-K between {first} and {last}"
            )
        urls: list[str] = []
        text = self._release_text(releases[-1], urls)  # ближайший к дате отчёта
        facts = "\n".join(
            [
                "## Measured facts",
                f"EPS surprise vs consensus, %: {_number(track.eps_surprise_pct)}",
                f"Revenue surprise vs consensus, %: {_number(track.rev_surprise_pct)}",
                f"Options-implied move, share of price: {_number(track.implied_move)}",
                f"Actual stock move on reaction day, share of price: {_number(track.actual_move)}",
            ]
        )
        result = self._llm.extract(
            instructions=OUTCOME_INSTRUCTIONS,
            text=_cap(
                f"{facts}\n\n## Earnings press release\n{text}",
                self._settings.max_chars_per_request,
            ),
            schema=OutcomeExtraction,
        )
        set_report_outcome(
            session, event.ticker, event.report_date, result.reaction_cause, result.guidance_change
        )
        save_report_audit(
            session,
            ReportAudit(
                ticker=event.ticker,
                fiscal_period=event.fiscal_period or "unknown",
                report_date=event.report_date,
                guidance={"stage": "T+1", "guidance_change": result.guidance_change},
                named_risks=result.named_risks,
                summary=result.summary,
                source_urls=urls,
            ),
        )

    # --- общее ---

    def _filings(self, ticker: str, since: date) -> list[Filing]:
        """8-K компании (и прежних регистрантов) с since, от новых к старым."""
        if self._ciks is None:
            self._ciks = self._edgar.ticker_ciks()
        cik = self._ciks.get(ticker)
        if cik is None:
            raise DataError("edgar", f"{ticker}: no CIK")
        ciks = [cik, *self._predecessors.get(ticker, [])]
        filings = [f for each in ciks for f in self._edgar.filings(each, {"8-K"}, since)]
        return sorted(filings, key=lambda f: (f.filing_date, f.accession_number), reverse=True)

    def _release_text(self, release: Filing, urls: list[str]) -> str:
        urls.append(release.url(self._archives))
        documents = self._edgar.documents(release)
        return _cap(
            _exhibits_or_primary(documents, self._settings.max_chars_per_document),
            self._settings.max_chars_per_request,
        )


def _exhibits_or_primary(documents: Sequence[FilingDocument], limit: int) -> str:
    """Приложения EX-99 (пресс-релизы); их нет — основной документ 8-K."""
    chosen = [d for d in documents if d.type.startswith("EX-99")] or [
        d for d in documents if d.type.startswith("8-K")
    ]
    return "\n\n".join(f"### {d.type} {d.filename}\n{_cap(d.text, limit)}" for d in chosen)


def _cap(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n[… обрезано по лимиту]"


def _mid(value: GuidanceRange | None) -> float | None:
    if value is None:
        return None
    bounds = [b for b in (value.low, value.high) if b is not None]
    return sum(bounds) / len(bounds) if bounds else None


def _number(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.4g}"


def _fiscal_period(session: Session, event_id: int) -> str:
    event = session.get(orm.Event, event_id)
    return "unknown" if event is None or event.fiscal_period is None else event.fiscal_period
