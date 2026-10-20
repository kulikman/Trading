"""«Компании»: сектора, компании сектора, пять вкладок профиля (DASHBOARD.md §4.5).

Без признаков модели и вероятностей — только факты о бизнесе и отчётах.
"""

from datetime import date, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.format import Num, day, empty, money, percent, price
from core.db import models as orm
from core.session_guard import to_et

TABS = ("overview", "news", "reports", "financials", "track")
TREND_ARROWS = {1: "↑", 0: "→", -1: "↓"}
QUEUE_LABELS = {
    "planned": "в очереди",
    "profiling": "сбор данных",
    "signals": "сигналы",
    "decided": "решение принято",
    "done": "завершено",
}
# Показатели вкладки «Финансы» и их порядок (метрики SEC XBRL, config/sources.yaml).
FINANCIAL_METRICS = {
    "revenue": "Выручка",
    "gross_profit": "Валовая прибыль",
    "operating_income": "Операционная прибыль",
    "net_income": "Чистая прибыль",
    "eps_diluted": "EPS (разводнённая)",
    "operating_cash_flow": "Операционный денежный поток",
    "capex": "Капзатраты",
}
QUARTERS = 8
OPTIONS_WORDS = {
    True: "ликвидные: объём ATM накануне отчёта выше порога, есть недельные экспирации",
    False: "малоликвидные: объём ATM ниже порога или нет недельных экспираций",
    None: "нет данных архива",
}
REPORTS_SHOWN = 12
# 8-K компании в SEC до даты (EDGAR принимает тикер вместо CIK).
EDGAR_8K = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}"
    "&type=8-K&dateb={before}&owner=include&count=10"
)
# Маржа — доля выручки (DASHBOARD §4.5 «выручка, маржа, EPS»): строка после своей прибыли.
MARGINS = {
    "gross_profit": "Валовая маржа",
    "operating_income": "Операционная маржа",
    "net_income": "Чистая маржа",
}


class SectorRow(BaseModel):
    id: str
    name: str
    trend: str
    summary: str
    companies: int
    next_report: str


class CompanyRow(BaseModel):
    ticker: str
    name: str
    next_report: str
    queue_status: str


class CompanyListRow(BaseModel):
    ticker: str
    name: str
    sector_id: str
    sector_name: str
    next_report: str
    queue_status: str


class SectorDetail(BaseModel):
    id: str
    name: str
    companies: list[CompanyRow]


class Overview(BaseModel):
    ticker: str
    name: str
    sector: str
    sector_id: str
    about: str
    segments: list[str]
    next_report: str
    options: str  # ликвидность опционов по архиву (E6)


class NewsRow(BaseModel):
    date: str
    tags: str
    title: str
    url: str


class News(BaseModel):
    rows: list[NewsRow]
    message: str | None


class ReportLink(BaseModel):
    date: str
    urls: list[str]


class Reports(BaseModel):
    reports: list[ReportLink]
    audit_date: str | None
    guidance: str | None
    summary: str | None
    risks: list[str]
    message: str | None


class FinancialRow(BaseModel):
    metric: str
    values: list[Num]


class Financials(BaseModel):
    quarters: list[str]
    rows: list[FinancialRow]
    message: str | None


class TrackRow(BaseModel):
    date: str
    eps_consensus: Num
    eps_actual: Num
    surprise: Num
    implied_move: Num
    actual_move: Num
    reaction_cause: str
    decision: str


class Track(BaseModel):
    rows: list[TrackRow]
    message: str | None


def sectors_view(session: Session, now: datetime) -> list[SectorRow]:
    today = to_et(now).date()
    rows = []
    for sector in session.scalars(select(orm.Sector).order_by(orm.Sector.name)).all():
        tickers = session.scalars(
            select(orm.Company.ticker).where(orm.Company.sector_id == sector.id)
        ).all()
        summary = session.scalars(
            select(orm.SectorSummary)
            .where(orm.SectorSummary.sector_id == sector.id)
            .order_by(orm.SectorSummary.as_of.desc(), orm.SectorSummary.id.desc())
            .limit(1)
        ).first()
        nearest = session.scalars(
            select(orm.Event)
            .where(orm.Event.ticker.in_(tickers), orm.Event.report_date >= today)
            .order_by(orm.Event.report_date, orm.Event.ticker)
            .limit(1)
        ).first()
        rows.append(
            SectorRow(
                id=sector.id,
                name=sector.name,
                trend=_trend(summary),
                summary=_sector_text(summary),
                companies=len(tickers),
                next_report=(
                    f"{nearest.ticker} {day(nearest.report_date)}" if nearest else "нет событий"
                ),
            )
        )
    return rows


def sector_view(session: Session, sector_id: str, now: datetime) -> SectorDetail | None:
    sector = session.get(orm.Sector, sector_id)
    if sector is None:
        return None
    companies = session.scalars(
        select(orm.Company).where(orm.Company.sector_id == sector_id).order_by(orm.Company.ticker)
    ).all()
    rows = []
    for company in companies:
        event = _next_event(session, company.ticker, to_et(now).date())
        rows.append(
            CompanyRow(
                ticker=company.ticker,
                name=company.name,
                next_report=_event_text(event),
                queue_status=QUEUE_LABELS.get(event.queue_status, event.queue_status)
                if event
                else "—",
            )
        )
    return SectorDetail(id=sector.id, name=sector.name, companies=rows)


def all_companies_view(
    session: Session, now: datetime, sector_id: str | None = None
) -> list[CompanyListRow]:
    query = select(orm.Company, orm.Sector).join(orm.Sector, orm.Company.sector_id == orm.Sector.id)
    if sector_id is not None:
        query = query.where(orm.Company.sector_id == sector_id)
    query = query.order_by(orm.Sector.name, orm.Company.ticker)
    rows = []
    today = to_et(now).date()
    for company, sector in session.execute(query):
        event = _next_event(session, company.ticker, today)
        rows.append(
            CompanyListRow(
                ticker=company.ticker,
                name=company.name,
                sector_id=sector.id,
                sector_name=sector.name,
                next_report=_event_text(event),
                queue_status=QUEUE_LABELS.get(event.queue_status, event.queue_status)
                if event
                else "—",
            )
        )
    return rows


def company_tab(
    session: Session, ticker: str, tab: str, now: datetime
) -> Overview | News | Reports | Financials | Track | None:
    company = session.get(orm.Company, ticker)
    if company is None:
        return None
    today = to_et(now).date()
    if tab == "overview":
        sector = session.get(orm.Sector, company.sector_id)
        return Overview(
            ticker=company.ticker,
            name=company.name,
            sector=sector.name if sector else company.sector_id,
            sector_id=company.sector_id,
            about=company.overview or "нет данных: профиль компании собирает «Досье» (отложено)",
            segments=[str(s) for s in company.segments or []],
            next_report=_event_text(_next_event(session, ticker, today)),
            options=OPTIONS_WORDS[company.options_liquid],
        )
    if tab == "news":
        return _news(session, ticker, today)
    if tab == "reports":
        return _reports(session, ticker, today)
    if tab == "financials":
        return _financials(session, ticker)
    return _track(session, ticker)


def _news(session: Session, ticker: str, today: date) -> News:
    last_report = session.scalar(
        select(func.max(orm.EarningsTrack.report_date)).where(
            orm.EarningsTrack.ticker == ticker, orm.EarningsTrack.report_date <= today
        )
    )
    query = select(orm.NewsArticle).where(orm.NewsArticle.tickers.contains([ticker]))
    if last_report is not None:
        query = query.where(func.date(orm.NewsArticle.published_at) >= last_report)
    articles = session.scalars(query.order_by(orm.NewsArticle.published_at.desc())).all()
    rows = [
        NewsRow(
            date=day(to_et(a.published_at).date()),
            tags=", ".join(a.tags or []) or "—",
            title=a.title,
            url=a.url,
        )
        for a in articles
    ]
    return News(rows=rows, message=None if rows else "нет новостей с прошлого отчёта")


def _reports(session: Session, ticker: str, today: date) -> Reports:
    audits = session.scalars(
        select(orm.ReportAudit)
        .where(orm.ReportAudit.ticker == ticker)
        .order_by(orm.ReportAudit.report_date.desc(), orm.ReportAudit.id.desc())
    ).all()
    by_date: dict[date, list[str]] = {}
    for audit in audits:
        urls = by_date.setdefault(audit.report_date, [])
        urls += [u for u in audit.source_urls or [] if u not in urls]
    # Прошлые отчёты архива со ссылкой на 8-K в SEC (аудит дашборда 14.10.2026, DASHBOARD §4.5).
    past = session.scalars(
        select(orm.EarningsTrack)
        .where(orm.EarningsTrack.ticker == ticker, orm.EarningsTrack.report_date <= today)
        .order_by(orm.EarningsTrack.report_date.desc())
        .limit(REPORTS_SHOWN)
    ).all()
    for track in past:
        filed = track.sec_filing_date or track.report_date
        urls = by_date.setdefault(track.report_date, [])
        link = EDGAR_8K.format(ticker=ticker, before=(filed + timedelta(days=1)).strftime("%Y%m%d"))
        if link not in urls:
            urls.insert(0, link)
    latest = audits[0] if audits else None
    return Reports(
        reports=[ReportLink(date=day(d), urls=u) for d, u in sorted(by_date.items(), reverse=True)],
        audit_date=day(latest.report_date) if latest else None,
        guidance=_guidance_text(latest.guidance) if latest else None,
        summary=latest.summary if latest else None,
        risks=[str(r) for r in (latest.named_risks or [])] if latest else [],
        message=None if by_date else "отчётов в архиве нет",
    )


def _financials(session: Session, ticker: str) -> Financials:
    rows = session.scalars(
        select(orm.FinancialQuarter).where(orm.FinancialQuarter.ticker == ticker)
    ).all()
    ends = sorted(
        {r.period_end for r in rows if r.metric == "revenue"} or {r.period_end for r in rows}
    )
    quarters = ends[-QUARTERS:]
    values = {(r.metric, r.period_end): r for r in rows}
    # EPS за Q4 XBRL не даёт (неаддитивен): берётся факт отчёта из истории (Alpha Vantage).
    reported = {
        t.fiscal_period_end: t.eps_actual
        for t in session.scalars(
            select(orm.EarningsTrack).where(
                orm.EarningsTrack.ticker == ticker, orm.EarningsTrack.eps_actual.is_not(None)
            )
        )
        if t.fiscal_period_end is not None
    }
    table = []
    for metric, label in FINANCIAL_METRICS.items():
        cells = [values.get((metric, q)) for q in quarters]
        from_reports = metric == "eps_diluted" and any(reported.get(q) for q in quarters)
        if not any(cells) and not from_reports:
            continue
        table.append(
            FinancialRow(
                metric=label,
                values=[
                    _eps_from_report(reported.get(q))
                    if c is None and metric == "eps_diluted"
                    else _financial_value(c.value if c else None, c.unit if c else "")
                    for c, q in zip(cells, quarters, strict=True)
                ],
            )
        )
        if metric in MARGINS:
            revenue = [values.get(("revenue", q)) for q in quarters]
            table.append(
                FinancialRow(
                    metric=MARGINS[metric],
                    values=[_margin(c, r) for c, r in zip(cells, revenue, strict=True)],
                )
            )
    return Financials(
        quarters=[day(q) for q in quarters],
        rows=table,
        message=None if table else "нет финансов в архиве",
    )


def _track(session: Session, ticker: str) -> Track:
    rows = session.execute(
        select(orm.EarningsTrack, orm.Decision.status)
        .outerjoin(
            orm.Event,
            (orm.Event.ticker == orm.EarningsTrack.ticker)
            & (orm.Event.report_date == orm.EarningsTrack.report_date),
        )
        .outerjoin(orm.Decision, orm.Decision.event_id == orm.Event.id)
        .where(orm.EarningsTrack.ticker == ticker)
        .order_by(orm.EarningsTrack.report_date.desc())
    ).all()
    unique: dict[int, tuple[orm.EarningsTrack, str | None]] = {}
    for t, status in rows:
        unique.setdefault(t.id, (t, status))  # входов у события бывает несколько — строка одна
    out = [
        TrackRow(
            date=day(t.report_date),
            eps_consensus=_eps(t.eps_consensus),
            eps_actual=_eps(t.eps_actual),
            surprise=percent(
                None if t.eps_surprise_pct is None else t.eps_surprise_pct / 100, signed=True
            ),
            implied_move=percent(t.implied_move),
            actual_move=percent(t.actual_move, signed=True),
            reaction_cause=t.reaction_cause or "—",
            decision=status or "—",
        )
        for t, status in unique.values()
    ]
    return Track(rows=out, message=None if out else "нет отчётов в архиве")


def _trend(summary: orm.SectorSummary | None) -> str:
    if summary is None or summary.trend is None:
        return "нет данных"
    return TREND_ARROWS[summary.trend]


def _sector_text(summary: orm.SectorSummary | None) -> str:
    if summary is None:
        return "нет данных"
    if summary.text_summary:
        return summary.text_summary
    if summary.peer_surprise_mean is None:
        return f"на {day(summary.as_of)}: пиры ещё не отчитались"
    surprise = percent(summary.peer_surprise_mean, signed=True).display
    return f"на {day(summary.as_of)}: средний сюрприз EPS пиров {surprise}"


def _next_event(session: Session, ticker: str, today: date) -> orm.Event | None:
    return session.scalars(
        select(orm.Event)
        .where(orm.Event.ticker == ticker, orm.Event.report_date >= today)
        .order_by(orm.Event.report_date)
        .limit(1)
    ).first()


def _event_text(event: orm.Event | None) -> str:
    if event is None:
        return "нет в календаре"
    return f"{day(event.report_date)} {event.report_time or ''}".strip()


def _guidance_text(guidance: object) -> str | None:
    """Прогноз компании из разбора «Досье» T−10 (цитата) или изменение прогноза на T+1."""
    if not isinstance(guidance, dict):
        return None
    expected = guidance.get("expected")
    if isinstance(expected, dict) and expected.get("found") and expected.get("quote"):
        return str(expected["quote"])
    change = guidance.get("guidance_change")
    return {1: "прогноз повышен", -1: "прогноз снижен", 0: "прогноз подтверждён"}.get(
        change if isinstance(change, int) else 99
    )


def _eps_from_report(value: float | None) -> Num:
    """EPS из истории отчётов (Alpha Vantage, база non-GAAP не документирована) — с пометкой."""
    if value is None:
        return empty("—")
    shown = _eps(value)
    return shown.model_copy(update={"display": f"{shown.display} (отчёт)"})


def _margin(profit: orm.FinancialQuarter | None, revenue: orm.FinancialQuarter | None) -> Num:
    if profit is None or revenue is None or not revenue.value:
        return empty("—")
    return percent(profit.value / revenue.value)


def _financial_value(value: float | None, unit: str) -> Num:
    if value is None:
        return empty("—")
    if unit == "USD/shares":
        return _eps(value)
    return _short_money(value)


def _short_money(value: float) -> Num:
    """$12,6 млрд / $850 млн — для отчётности."""
    for scale, word in ((1e9, "млрд"), (1e6, "млн")):
        if abs(value) >= scale:
            shown = f"{abs(value) / scale:.1f}".replace(".", ",")
            return Num(value=value, display=f"{'−' if value < 0 else ''}${shown} {word}")
    return money(value)


def _eps(value: float | None) -> Num:
    if value is None:
        return empty("—")
    shown = price(abs(value)).display.replace(".", ",")
    return Num(value=value, display=f"{'−' if value < 0 else ''}${shown}")
