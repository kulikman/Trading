from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.edgar.documents import FilingDocument
from adapters.edgar.models import Filing
from adapters.errors import DataError
from adapters.finnhub.models import FinnhubEarning
from adapters.massive.models import NewsArticle
from agents.dossier.agent import DossierAgentPlugin
from agents.dossier.extraction import (
    DisclosureEvent,
    DisclosureExtraction,
    GuidanceExtraction,
    GuidanceRange,
    OutcomeExtraction,
)
from core.config import load_config
from core.db import models as orm
from core.db.store import save_reported_earnings, sync_universe, update_earnings
from core.domain.earnings import ReportedEarnings
from core.domain.schedule import EventJob
from core.registry.agent_jobs import agent_handlers
from core.registry.protocols import EventContext

CONFIG = load_config()
SETTINGS = CONFIG.thresholds.agents.dossier
ARCHIVES = CONFIG.sources.edgar.archives_base_url
RUN_AT = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)  # T−10 07:00 ET
REPORT = date(2026, 10, 20)


def filing(accession: str, filed: date, items: str) -> Filing:
    return Filing.model_validate(
        {
            "cik": 1065280,
            "form": "8-K",
            "accession_number": accession,
            "filing_date": filed,
            "primary_document": f"{accession}.htm",
            "items": items,
        }
    )


PREVIOUS = filing("0001-26-000211", date(2026, 7, 16), "2.02,9.01")
DEBT = filing("0001-26-000214", date(2026, 7, 22), "8.01,9.01")
OLD = filing("0001-26-000100", date(2026, 4, 16), "2.02,9.01")  # позапрошлый отчёт
CURRENT = filing("0001-26-000300", date(2026, 10, 20), "2.02,9.01")


class Edgar:
    def __init__(self, filings: list[Filing]) -> None:
        self._filings = filings
        self.read: list[str] = []

    def ticker_ciks(self) -> dict[str, int]:
        return {"NFLX": 1065280}

    def filings(self, cik: int, forms: Any = None, since: date | None = None) -> list[Filing]:
        return [f for f in self._filings if since is None or f.filing_date >= since]

    def documents(self, f: Filing) -> list[FilingDocument]:
        self.read.append(f.accession_number)
        return [
            FilingDocument("8-K", "cover.htm", "cover page"),
            FilingDocument("EX-99.1", "ex991.htm", f"press release {f.accession_number}"),
        ]


class News:
    def __init__(self, articles: list[NewsArticle]) -> None:
        self.articles = articles

    def news(self, ticker: str, published_gte: date | None = None) -> list[NewsArticle]:
        return self.articles


class Finnhub:
    def __init__(self, revenue: float | None, eps: float | None) -> None:
        self.row = FinnhubEarning.model_validate(
            {"symbol": "NFLX", "date": REPORT, "revenueEstimate": revenue, "epsEstimate": eps}
        )

    def earnings_calendar(
        self, start: date, end: date, symbol: str | None = None
    ) -> list[FinnhubEarning]:
        return [self.row]


class Llm:
    def __init__(self, *answers: BaseModel) -> None:
        self.answers = {type(a): a for a in answers}
        self.calls: list[tuple[str, str]] = []

    def extract[M: BaseModel](self, *, instructions: str, text: str, schema: type[M]) -> M:
        self.calls.append((schema.__name__, text))
        answer = self.answers[schema]
        assert isinstance(answer, schema)
        return answer


GUIDANCE = GuidanceExtraction(
    found=True,
    period="Q3'26",
    revenue_usd=GuidanceRange(low=12.8e9, high=13.0e9),
    eps_usd=GuidanceRange(low=0.80, high=0.84),
    eps_basis="non_gaap",
    quote="Q3 revenue $12.8-13.0 billion",
)


def event(kind: str, direction: int, material: bool) -> DisclosureEvent:
    return DisclosureEvent.model_validate(
        {
            "date": "2026-08-01",
            "source": "8-K",
            "kind": kind,
            "direction": direction,
            "material": material,
            "summary": "событие",
        }
    )


DISCLOSURE = DisclosureExtraction(
    events=[
        event("guidance_change", 1, True),
        event("mna", 1, True),
        event("legal_regulatory", -1, True),
        event("other", -1, False),  # несущественное — не считается
    ],
    summary="Компания подняла прогноз.",
)


def agent(edgar: Edgar, llm: Llm, finnhub: Finnhub, news: News | None = None) -> DossierAgentPlugin:
    return DossierAgentPlugin(edgar, news or News([]), finnhub, llm, SETTINGS, ARCHIVES)


@pytest.fixture
def nflx(session: Session) -> orm.Event:
    sync_universe(session, CONFIG.universe)
    row = orm.Event(
        ticker="NFLX",
        report_date=REPORT,
        report_time="AMC",
        date_status="confirmed",
        fiscal_period="2026Q3",
    )
    session.add(row)
    session.flush()
    return row


def ctx(session: Session, event_id: int) -> EventContext:
    return EventContext(
        event_id=event_id,
        ticker="NFLX",
        report_date=REPORT,
        report_time="AMC",
        stage="T-10",
        as_of=RUN_AT,
        session=session,
    )


def test_t10_features_by_hand_and_audit_saved(session: Session, nflx: orm.Event) -> None:
    edgar = Edgar([PREVIOUS, DEBT, OLD])
    llm = Llm(GUIDANCE, DISCLOSURE)
    features = agent(edgar, llm, Finnhub(revenue=13.26e9, eps=0.78)).run(ctx(session, nflx.id))
    # консенсус 13,26 млрд против середины прогноза 12,9 млрд: +2,79%
    assert features.guidance_gap_revenue == pytest.approx(13.26 / 12.9 - 1)
    assert features.guidance_gap_eps == pytest.approx((0.78 - 0.82) / 0.82)
    assert features.guidance_risk == features.guidance_gap_revenue  # выручка важнее EPS
    assert (features.disclosure, features.disclosure_events) == (1, 3)  # +1 +1 −1 → +1
    # прогноз — из прошлого релиза; раскрытия — только подачи после него, без самого релиза
    assert edgar.read == [PREVIOUS.accession_number, DEBT.accession_number]
    assert [name for name, _ in llm.calls] == ["GuidanceExtraction", "DisclosureExtraction"]
    audit = session.scalars(select(orm.ReportAudit)).one()
    assert (audit.ticker, audit.fiscal_period, audit.report_date) == ("NFLX", "2026Q3", REPORT)
    assert audit.guidance is not None
    assert audit.guidance["expected"]["period"] == "Q3'26"
    assert audit.summary == "Компания подняла прогноз."
    assert audit.source_urls == [PREVIOUS.url(ARCHIVES), DEBT.url(ARCHIVES)]


def test_nothing_disclosed_skips_llm_and_gaap_eps_is_not_compared(
    session: Session, nflx: orm.Event
) -> None:
    gaap = GUIDANCE.model_copy(update={"revenue_usd": None, "eps_basis": "gaap"})
    llm = Llm(gaap)
    features = agent(Edgar([PREVIOUS]), llm, Finnhub(revenue=13e9, eps=0.78)).run(
        ctx(session, nflx.id)
    )
    assert (features.disclosure, features.disclosure_events) == (0, 0)
    assert features.guidance_risk is None  # EPS Finnhub — non-GAAP, с GAAP-прогнозом не сравниваем
    assert [name for name, _ in llm.calls] == ["GuidanceExtraction"]


def test_revenue_unit_error_is_not_a_feature(session: Session, nflx: orm.Event) -> None:
    millions = GUIDANCE.model_copy(update={"revenue_usd": GuidanceRange(low=12800, high=13000)})
    features = agent(Edgar([PREVIOUS]), Llm(millions), Finnhub(revenue=13.26e9, eps=None)).run(
        ctx(session, nflx.id)
    )
    assert (features.guidance_gap_revenue, features.guidance_risk) == (None, None)


def test_no_previous_release_uses_news_only(session: Session, nflx: orm.Event) -> None:
    article = NewsArticle.model_validate(
        {
            "id": "1",
            "title": "Netflix raises outlook",
            "article_url": "https://example.com/1",
            "published_utc": "2026-09-01T12:00:00Z",
            "tickers": ["NFLX"],
            "description": "Company comments at a conference",
        }
    )
    llm = Llm(DISCLOSURE)
    features = agent(Edgar([]), llm, Finnhub(None, None), News([article])).run(
        ctx(session, nflx.id)
    )
    assert features.disclosure == 1
    assert features.guidance_risk is None
    name, text = llm.calls[0]
    assert name == "DisclosureExtraction"
    assert "2026-09-01 Netflix raises outlook — Company comments at a conference" in text


OUTCOME = OutcomeExtraction(
    reaction_cause="Прогноз ниже ожиданий.",
    guidance_change=-1,
    named_risks=["конкуренция"],
    summary="Квартал в рамках прогноза.",
)


def archive_report(session: Session) -> None:
    save_reported_earnings(
        session,
        [
            ReportedEarnings(
                ticker="NFLX",
                report_date=REPORT,
                report_time="AMC",
                fiscal_period_end=date(2026, 9, 30),
                eps_surprise_pct=4.0,
            )
        ],
    )
    update_earnings(session, "NFLX", REPORT, {"actual_move": -0.07})


def test_t1_outcome_writes_cause_and_audit_via_job_handler(
    session: Session, nflx: orm.Event
) -> None:
    archive_report(session)
    llm = Llm(OUTCOME)
    dossier = agent(Edgar([CURRENT, PREVIOUS]), llm, Finnhub(None, None))
    handlers = agent_handlers(CONFIG.schedule, {"dossier": dossier})
    assert {"dossier", "dossier_outcome"} <= set(handlers)
    job = EventJob(
        event_id=nflx.id,
        stage="T+1",
        job="dossier_outcome",
        kind="analysis",
        run_at=datetime(2026, 10, 22, 12, 5, tzinfo=UTC),
    )
    handlers["dossier_outcome"](session, job)
    track = session.scalars(
        select(orm.EarningsTrack).where(orm.EarningsTrack.ticker == "NFLX")
    ).one()
    assert (track.reaction_cause, track.guidance_change) == ("Прогноз ниже ожиданий.", -1)
    _, text = llm.calls[0]
    assert "EPS surprise vs consensus, %: 4" in text
    assert "Actual stock move on reaction day, share of price: -0.07" in text
    assert f"press release {CURRENT.accession_number}" in text  # новый релиз, не прошлый
    audit = session.scalars(select(orm.ReportAudit)).one()
    assert (audit.summary, audit.named_risks) == ("Квартал в рамках прогноза.", ["конкуренция"])


def test_t1_needs_archive_row_and_release(session: Session, nflx: orm.Event) -> None:
    dossier = agent(Edgar([PREVIOUS]), Llm(OUTCOME), Finnhub(None, None))
    with pytest.raises(DataError, match="no earnings_track row"):
        dossier.outcome(session, nflx.id, RUN_AT)
    archive_report(session)
    with pytest.raises(DataError, match="no earnings release 8-K"):
        dossier.outcome(session, nflx.id, datetime(2026, 10, 22, 12, tzinfo=UTC))


def test_outcome_job_without_outcome_step_fails_at_startup() -> None:
    class FeaturesOnly:
        id = "dossier"

    with pytest.raises(ValueError, match="has no outcome step"):
        agent_handlers(CONFIG.schedule, {"dossier": FeaturesOnly()})  # type: ignore[dict-item]
